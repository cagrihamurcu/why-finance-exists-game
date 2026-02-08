import streamlit as st
import numpy as np
import pandas as pd

st.set_page_config(page_title="Borsa Uygulamaları - 1. Hafta Oyunu", layout="wide")

# =========================
# SABİT (ÖĞRENCİ DEĞİŞTİREMEZ)
# =========================
DEFAULT_MONTHLY_INCOME = 60000
START_FIXED_COST = 30000  # 1. ay sabit gider

# =========================
# OYUN PARAMETRELERİ
# =========================
CFG = {
    "MONTHS": 12,
    "INFL_START": 0.20,
    "INFL_STEP": 0.05,

    "LOAN_ACTIVE_FROM_MONTH": 4,
    "LOAN_RATE": 0.025,  # borç aylık faiz

    # Nakit hırsızlığı
    "CASH_THEFT_PROB_STAGE1": 0.12,
    "CASH_THEFT_PROB_STAGE2": 0.05,
    "CASH_THEFT_SEV_MIN": 0.10,
    "CASH_THEFT_SEV_MAX": 0.35,

    # Banka olayı
    "BANK_INCIDENT_PROB": 0.02,

    # Vadeli faiz aralığı (aylık)
    "TD_RATE_MIN": 0.0070,
    "TD_RATE_MAX": 0.0140,

    # Güvence aralığı
    "GUAR_MIN": 0.70,
    "GUAR_MAX": 0.99,

    # Vadeli bozma cezası
    "EARLY_BREAK_PENALTY": 0.01,

    # İşlem komisyonu (tüm finansal kurum işlemleri)
    "TX_FEE": 0.005,

    # Spread (toplam)
    "SPREAD": {
        "fx": 0.010,
        "pm": 0.012,
        "eq": 0.020,
        "cr": 0.050,
    },

    # Riskli varlık getirileri (aylık)
    "EQ_MU": 0.015, "EQ_SIG": 0.060,
    "CR_MU": 0.020, "CR_SIG": 0.120,
    "PM_MU": 0.008, "PM_SIG": 0.030,
    "FX_MU": 0.010, "FX_SIG": 0.040,

    # Kriz ayı
    "CRISIS_MONTH": 6,
    "CRISIS_EQ": -0.12,
    "CRISIS_CR": -0.20,
    "CRISIS_PM": +0.04,
    "CRISIS_FX": +0.07,
}

ASSETS = {
    "cash": "Nakit",
    "dd": "Vadesiz Mevduat (Faiz Yok)",
    "td": "Vadeli Mevduat (Faiz Var)",
    "fx": "Döviz",
    "pm": "Kıymetli Metal",
    "eq": "Hisse Senedi",
    "cr": "Kripto",
}

RISK_ASSETS = ["fx", "pm", "eq", "cr"]
DEPOSIT_ASSETS = ["dd", "td"]


# =========================
# YARDIMCI FONKSİYONLAR
# =========================
def fmt_tl(x: float) -> str:
    return f"{x:,.0f} TL".replace(",", ".")

def fmt_pct(x: float) -> str:
    return f"{x*100:.1f}%"

def inflation_rate(month: int) -> float:
    return float(CFG["INFL_START"] + CFG["INFL_STEP"] * (month - 1))

def can_borrow(month: int) -> bool:
    return month >= int(CFG["LOAN_ACTIVE_FROM_MONTH"])

def open_assets_by_month(month: int):
    if month <= 3:
        return ["cash"]
    if month <= 5:
        return ["cash", "dd", "td"]
    if month <= 7:
        return ["cash", "dd", "td", "fx", "pm"]
    return ["cash", "dd", "td", "fx", "pm", "eq", "cr"]

def stage_label(month: int):
    if month <= 3: return "1-KurumYok"
    if month <= 5: return "2-Banka"
    if month <= 7: return "3-Korunma"
    return "4-Piyasa"

def rng_for_global(month: int):
    return np.random.default_rng(st.session_state.seed + month * 999)

def rng_for_player(name: str, month: int):
    return np.random.default_rng((hash(name) % 10000) + month * 1000 + st.session_state.seed)

def bank_count_for_month(month: int) -> int:
    if month < 4:
        return 0
    return min(2 + (month - 4), 8)

def banks_for_month(month: int):
    n = bank_count_for_month(month)
    if n == 0:
        return []
    r = rng_for_global(month)
    td_rates = r.uniform(CFG["TD_RATE_MIN"], CFG["TD_RATE_MAX"], size=n)

    # Trade-off: yüksek faiz -> daha düşük güvence
    order = np.argsort(td_rates)  # düşük->yüksek faiz
    banks = [None] * n
    for rank, idx in enumerate(order):
        td = float(td_rates[idx])
        x = rank / max(n - 1, 1)
        base_guar = CFG["GUAR_MAX"] - x * (CFG["GUAR_MAX"] - CFG["GUAR_MIN"])
        noise = float(r.normal(0, 0.015))
        guarantee = float(np.clip(base_guar + noise, CFG["GUAR_MIN"], CFG["GUAR_MAX"]))
        banks[idx] = {"Bank": f"Banka {idx + 1}", "TD_Rate": td, "Guarantee": guarantee}
    return banks

def banks_df(month: int) -> pd.DataFrame:
    b = banks_for_month(month)
    if not b:
        return pd.DataFrame()
    df = pd.DataFrame(b)
    df["Vadeli Faiz (Aylık)"] = df["TD_Rate"].map(lambda x: f"{x*100:.2f}%")
    df["Güvence Oranı"] = df["Guarantee"].map(lambda x: f"{x*100:.0f}%")
    return df.sort_values("TD_Rate", ascending=False)[["Bank", "Vadeli Faiz (Aylık)", "Güvence Oranı"]]

def buy_cost_rate(asset_key: str) -> float:
    fee = float(CFG["TX_FEE"])
    spr = float(CFG["SPREAD"].get(asset_key, 0.0))
    return fee + spr / 2.0

def sell_cost_rate(asset_key: str) -> float:
    fee = float(CFG["TX_FEE"])
    spr = float(CFG["SPREAD"].get(asset_key, 0.0))
    return fee + spr / 2.0

def dd_total(p: dict) -> float:
    return float(sum(p.get("dd_accounts", {}).values()))

def td_total(p: dict) -> float:
    return float(sum(p.get("td_accounts", {}).values()))

def other_investments_total(p: dict) -> float:
    return float(sum(p["holdings"].get(k, 0.0) for k in RISK_ASSETS))

def total_investments(p: dict) -> float:
    return float(dd_total(p) + td_total(p) + other_investments_total(p))

def net_wealth(p: dict) -> float:
    return float(p["holdings"]["cash"] + total_investments(p) - float(p.get("debt", 0.0)))

def dd_breakdown_df(p: dict) -> pd.DataFrame:
    rows = []
    for bank, bal in p.get("dd_accounts", {}).items():
        bal = float(bal)
        if bal > 0:
            rows.append({"Banka": bank, "Vadesiz Bakiye (TL)": round(bal, 0)})
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("Vadesiz Bakiye (TL)", ascending=False)

def td_breakdown_df(p: dict) -> pd.DataFrame:
    rows = []
    for bank, bal in p.get("td_accounts", {}).items():
        bal = float(bal)
        if bal > 0:
            rows.append({"Banka": bank, "Vadeli Bakiye (TL)": round(bal, 0)})
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("Vadeli Bakiye (TL)", ascending=False)

def safe_number_input(label: str, key: str, maxv: float, step: float = 1000.0) -> float:
    maxv = float(max(0.0, maxv))
    if maxv <= 0.0:
        st.caption("Bu kalemde işlem yapılamaz (limit 0).")
        if key in st.session_state:
            st.session_state[key] = 0.0
        return 0.0
    prev = float(st.session_state.get(key, 0.0))
    val = min(max(prev, 0.0), maxv)  # clamp
    return st.number_input(label, min_value=0.0, max_value=maxv, value=val, step=step, key=key)


# =========================
# SESSION STATE
# =========================
if "seed" not in st.session_state:
    st.session_state.seed = 20260209

if "players" not in st.session_state:
    st.session_state.players = {}

if "theft_banner" not in st.session_state:
    st.session_state.theft_banner = None

def get_player(name: str) -> dict:
    if name not in st.session_state.players:
        st.session_state.players[name] = {
            "month": 1,
            "finished": False,
            "defaulted": False,
            "debt": 0.0,
            "holdings": {"cash": 0.0, "fx": 0.0, "pm": 0.0, "eq": 0.0, "cr": 0.0},
            "dd_accounts": {},
            "td_accounts": {},
            "income_fixed": float(DEFAULT_MONTHLY_INCOME),
            "fixed_current": float(START_FIXED_COST),
            "last_dd_bank": None,
            "last_td_bank": None,
            "log": [],
        }
    return st.session_state.players[name]


# =========================
# UI - BAŞLIK + RESET
# =========================
st.title("🎮 1. Hafta Oyunu: Neden Finansal Piyasalar ve Kurumlarla İlgileniyoruz?")

# Hırsızlık banner'ı
if st.session_state.theft_banner:
    loss = st.session_state.theft_banner["loss"]
    remain = st.session_state.theft_banner["remain"]
    st.error("🚨🚨🚨 NAKİT HIRSIZLIĞI — ACİL UYARI 🚨🚨🚨")
    st.markdown(
        f"""
        <div style="padding:18px;border-radius:16px;border:4px solid #8b0000;
                    background:linear-gradient(90deg,#ffe6e6,#fff1f1);
                    font-size:22px;line-height:1.5">
          <b>NAKİT ÇALINDI!</b><br>
          <b>Kayıp:</b> {fmt_tl(loss)}<br>
          <b>Kalan Nakit:</b> {fmt_tl(remain)}<br>
          <span style="font-size:16px;">(Bu risk yalnızca <b>nakitte</b> geçerlidir. Bankadaki mevduat bu riskten etkilenmez.)</span>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.toast(f"🚨 Nakit hırsızlığı! Kayıp: {fmt_tl(loss)}", icon="🚨")
    if st.button("✅ Uyarıyı kapat", key="close_theft_banner"):
        st.session_state.theft_banner = None
        st.rerun()

c1, c2 = st.columns([1, 4])
with c1:
    if st.button("🧹 Oyunu Sıfırla"):
        st.session_state.clear()
        st.rerun()
with c2:
    st.caption(
        "Kurgu: Gelir sabit, giderler enflasyonla artar. Nakit risklidir (hırsızlık). "
        "Bankalar ve piyasa araçları devreye girdikçe seçenekler artar; ama komisyon/spread/ceza gibi maliyetler vardır."
    )

name = st.text_input("Oyuncu Adı")
if not name:
    st.stop()

p = get_player(name)
month = int(p["month"])
opened = open_assets_by_month(month)

# =========================
# LEADERBOARD
# =========================
st.subheader("🏆 Oyuncu Sıralaması")

rows = []
for pname, pp in st.session_state.players.items():
    cash = float(pp["holdings"]["cash"])
    inv = float(sum(pp["holdings"].get(k, 0.0) for k in RISK_ASSETS)) + float(sum(pp.get("dd_accounts", {}).values())) + float(sum(pp.get("td_accounts", {}).values()))
    debt = float(pp.get("debt", 0.0))
    net = cash + inv - debt
    status = "Devam"
    if pp.get("finished") and pp.get("defaulted"):
        status = "Temerrüt"
    elif pp.get("finished"):
        status = "Bitti"
    month_done = CFG["MONTHS"] if pp.get("finished") else max(int(pp.get("month", 1)) - 1, 0)
    rows.append({"Sıra": 0, "Oyuncu": pname, "Durum": status, "Ay": month_done, "Servet(Net)": round(net, 0), "Borç": round(debt, 0)})

lb = pd.DataFrame(rows).sort_values(["Servet(Net)", "Borç"], ascending=[False, True]).reset_index(drop=True)
lb["Sıra"] = lb.index + 1
st.dataframe(lb, use_container_width=True, hide_index=True, height=220)
st.divider()

# =========================
# OYUN BİTTİ
# =========================
if p.get("finished", False):
    if p.get("defaulted", False):
        st.error("⛔ Oyun bitti: Ay 1–3 döneminde açık oluştu (borç yok) → temerrüt.")
    else:
        st.success("✅ Oyun bitti: 12. ay tamamlandı.")
    a, b, c, d = st.columns(4)
    a.metric("Nakit", fmt_tl(p["holdings"]["cash"]))
    b.metric("Yatırım (Toplam)", fmt_tl(total_investments(p)))
    c.metric("Borç", fmt_tl(p["debt"]))
    d.metric("Servet (Net)", fmt_tl(net_wealth(p)))
    with st.expander("📒 Geçmiş (Sade)", expanded=True):
        if p["log"]:
            st.dataframe(pd.DataFrame(p["log"]), use_container_width=True, hide_index=True, height=360)
    st.stop()

# =========================
# AY PANELİ
# =========================
income = float(p["income_fixed"])
infl = inflation_rate(month)
fixed_this_month = float(p["fixed_current"])

st.subheader(f"📅 Ay {month} / {CFG['MONTHS']} | Aşama: {stage_label(month)}")
st.progress((month - 1) / CFG["MONTHS"])

k1, k2, k3, k4 = st.columns(4)
k1.metric("Gelir (Sabit)", fmt_tl(income))
k2.metric("Enflasyon Oranı", fmt_pct(infl))
k3.metric("Bu Ay Sabit Gider", fmt_tl(fixed_this_month))
k4.metric("Borç Mekanizması", "Açık" if can_borrow(month) else "Kapalı (Ay1-3)")

m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("Nakit", fmt_tl(p["holdings"]["cash"]))
m2.metric("Vadesiz Toplam", fmt_tl(dd_total(p)))
m3.metric("Vadeli Toplam", fmt_tl(td_total(p)))
m4.metric("Diğer Yatırımlar", fmt_tl(other_investments_total(p)))
m5.metric("Borç", fmt_tl(p["debt"]))
m6.metric("Servet (Net)", fmt_tl(net_wealth(p)))

with st.expander("🏦 Mevduat Dökümü (Banka Bazında)", expanded=False):
    cA, cB = st.columns(2)
    with cA:
        st.write("**Vadesiz (banka bazında):**")
        ddf = dd_breakdown_df(p)
        if ddf.empty:
            st.caption("Vadesiz mevduat yok.")
        else:
            st.dataframe(ddf, use_container_width=True, hide_index=True, height=220)
    with cB:
        st.write("**Vadeli (banka bazında):**")
        tdf = td_breakdown_df(p)
        if tdf.empty:
            st.caption("Vadeli mevduat yok.")
        else:
            st.dataframe(tdf, use_container_width=True, hide_index=True, height=220)

# =========================
# BANKALAR (Ay 4+)
# =========================
bank_map = {}
if month >= 4:
    st.divider()
    st.subheader("🏦 Bankalar (Bu Ay) — Vadeli Faiz / Güvence Trade-off")
    b_list = banks_for_month(month)
    bank_map = {b["Bank"]: b for b in b_list}
    st.dataframe(banks_df(month), use_container_width=True, hide_index=True, height=220)

    banks_names = list(bank_map.keys())
    if p.get("last_dd_bank") is None:
        p["last_dd_bank"] = banks_names[-1]
    if p.get("last_td_bank") is None:
        p["last_td_bank"] = banks_names[0]

    cA, cB = st.columns(2)
    with cA:
        p["last_dd_bank"] = st.selectbox("Vadesiz mevduat bankası", banks_names, index=banks_names.index(p["last_dd_bank"]))
    with cB:
        p["last_td_bank"] = st.selectbox("Vadeli mevduat bankası", banks_names, index=banks_names.index(p["last_td_bank"]))

# =========================
# 0) BOZDURMA / SATIŞ
# =========================
st.divider()
st.subheader("0) Bozdurma / Satış (Opsiyonel)")
st.caption("Her kalemde: Maks işlem tutarı + seçtiğiniz işlem sonrası tahmini NET nakit girişi gösterilir.")

sell_inputs = {k: 0.0 for k in RISK_ASSETS}
sell_dd_amt = 0.0
sell_td_amt = 0.0
sell_dd_bank = None
sell_td_bank = None

fee = float(CFG["TX_FEE"])
pen = float(CFG["EARLY_BREAK_PENALTY"])

colS1, colS2 = st.columns(2)

with colS1:
    st.markdown("#### Riskli Varlık Satışı (Döviz/Metal/Hisse/Kripto)")
    for k in RISK_ASSETS:
        if k not in opened:
            continue
        max_sell = float(p["holdings"].get(k, 0.0))
        rate = sell_cost_rate(k)
        st.caption(f"➡️ {ASSETS[k]} | **maks satılabilir:** {fmt_tl(max_sell)} | **maliyet:** {rate*100:.2f}%")

        sell_amt = safe_number_input(
            f"{ASSETS[k]} Satış (TL)",
            f"sell_{k}_{name}_{month}",
            max_sell,
            1000.0
        )
        sell_inputs[k] = float(sell_amt)
        net_cash = float(sell_amt) * (1.0 - rate)
        st.caption(f"✅ Tahmini net nakit girişi: {fmt_tl(net_cash)}")

with colS2:
    st.markdown("#### Mevduat Bozdurma / Çekim")

    if month >= 4:
        # Vadesiz
        dd_banks = [bk for bk, bal in p["dd_accounts"].items() if float(bal) > 0]
        if dd_banks:
            sell_dd_bank = st.selectbox("Vadesizden çekilecek banka", dd_banks, key=f"dd_with_bank_{name}_{month}")
            max_dd = float(p["dd_accounts"].get(sell_dd_bank, 0.0))
            st.caption(f"➡️ Vadesiz ({sell_dd_bank}) | **maks çekilebilir:** {fmt_tl(max_dd)} | **komisyon:** {fee*100:.2f}%")

            sell_dd_amt = safe_number_input(
                "Vadesiz Çekim (TL)",
                f"sell_dd_{name}_{month}",
                max_dd,
                1000.0
            )
            st.caption(f"✅ Tahmini net nakit girişi: {fmt_tl(float(sell_dd_amt) * (1.0 - fee))}")
        else:
            st.caption("➡️ Vadesiz | maks çekilebilir: 0 TL")

        # Vadeli
        td_banks = [bk for bk, bal in p["td_accounts"].items() if float(bal) > 0]
        if td_banks:
            sell_td_bank = st.selectbox("Vadeliden bozulacak banka", td_banks, key=f"td_break_bank_{name}_{month}")
            max_td = float(p["td_accounts"].get(sell_td_bank, 0.0))
            st.caption(
                f"➡️ Vadeli ({sell_td_bank}) | **maks bozdurulabilir:** {fmt_tl(max_td)} | "
                f"**ceza:** {pen*100:.2f}% + **komisyon:** {fee*100:.2f}%"
            )

            sell_td_amt = safe_number_input(
                "Vadeli Bozma (TL)",
                f"sell_td_{name}_{month}",
                max_td,
                1000.0
            )
            st.caption(f"✅ Tahmini net nakit girişi: {fmt_tl(float(sell_td_amt) * (1.0 - fee - pen))}")
        else:
            st.caption("➡️ Vadeli | maks bozdurulabilir: 0 TL")
    else:
        st.caption("Ay 1–3: Bankalar yok (mevduat işlemi yok).")

# Satış/Bozma önizleme (toplam)
projected_sell_cash_in = 0.0
projected_sell_costs = 0.0

for k, amt in sell_inputs.items():
    amt = float(amt)
    if amt <= 0:
        continue
    rate = sell_cost_rate(k)
    projected_sell_cash_in += amt * (1.0 - rate)
    projected_sell_costs += amt * rate

if month >= 4 and sell_dd_amt > 0:
    projected_sell_cash_in += float(sell_dd_amt) * (1.0 - fee)
    projected_sell_costs += float(sell_dd_amt) * fee

if month >= 4 and sell_td_amt > 0:
    projected_sell_cash_in += float(sell_td_amt) * (1.0 - fee - pen)
    projected_sell_costs += float(sell_td_amt) * (fee + pen)

st.info(
    f"📌 Toplam (satış/bozma) tahmini NET nakit girişi: **{fmt_tl(projected_sell_cash_in)}** | "
    f"Toplam maliyet: **{fmt_tl(projected_sell_costs)}**"
)

# =========================
# 1) BÜTÇE
# =========================
st.divider()
st.subheader("1) Bütçe (Bu Ay)")

available_without_borrow = float(p["holdings"]["cash"]) + income
extra_max = int(max(0.0, available_without_borrow - fixed_this_month)) if not can_borrow(month) else int(income * 3)
extra_default = min(5000, max(0, extra_max))
extra = st.number_input("Ek Harcama", 0, max(0, extra_max), extra_default, 1000)

total_exp = fixed_this_month + float(extra)
st.write(f"Toplam gider: **{fmt_tl(total_exp)}**")

if (not can_borrow(month)) and (total_exp > available_without_borrow):
    st.error("Ay 1–3'te borç yok. Bu bütçe (nakit+gelir) sınırını aşıyor → temerrüt olur. Ek harcamayı azaltın.")

available_for_invest_preview = float(p["holdings"]["cash"]) + projected_sell_cash_in + income - total_exp
if not can_borrow(month):
    available_for_invest_preview = max(0.0, available_for_invest_preview)

st.success(f"💰 Bu ay yatırım için kullanılabilir MAX nakit (önizleme): **{fmt_tl(available_for_invest_preview)}**")

# =========================
# 2) YATIRIM (ALIŞ)
# =========================
st.divider()
st.subheader("2) Yatırım Kararı (TL) — Alış")

inv_inputs = {}
max_buy = float(available_for_invest_preview)

colB1, colB2 = st.columns(2)

with colB1:
    if "dd" in opened and month >= 4:
        inv_inputs["dd"] = safe_number_input(
            f"Vadesiz Mevduat ALIŞ (TL) | Komisyon: {fee*100:.2f}%",
            f"buy_dd_{name}_{month}",
            max_buy,
            1000.0
        )
    if "td" in opened and month >= 4:
        inv_inputs["td"] = safe_number_input(
            f"Vadeli Mevduat ALIŞ (TL) | Komisyon: {fee*100:.2f}%",
            f"buy_td_{name}_{month}",
            max_buy,
            1000.0
        )
    if "fx" in opened:
        inv_inputs["fx"] = safe_number_input(
            f"Döviz ALIŞ (TL) | Maliyet: {buy_cost_rate('fx')*100:.2f}%",
            f"buy_fx_{name}_{month}",
            max_buy,
            1000.0
        )
    if "pm" in opened:
        inv_inputs["pm"] = safe_number_input(
            f"Kıymetli Metal ALIŞ (TL) | Maliyet: {buy_cost_rate('pm')*100:.2f}%",
            f"buy_pm_{name}_{month}",
            max_buy,
            1000.0
        )

with colB2:
    if "eq" in opened:
        inv_inputs["eq"] = safe_number_input(
            f"Hisse Senedi ALIŞ (TL) | Maliyet: {buy_cost_rate('eq')*100:.2f}%",
            f"buy_eq_{name}_{month}",
            max_buy,
            1000.0
        )
    if "cr" in opened:
        inv_inputs["cr"] = safe_number_input(
            f"Kripto ALIŞ (TL) | Maliyet: {buy_cost_rate('cr')*100:.2f}%",
            f"buy_cr_{name}_{month}",
            max_buy,
            1000.0
        )

total_buy = float(sum(inv_inputs.values())) if inv_inputs else 0.0
st.write(f"Bu ay toplam ALIŞ (brüt): **{fmt_tl(total_buy)}**")
if total_buy > max_buy + 1e-9:
    st.error("Toplam alış, bu ay yatırım için kullanılabilir MAX nakdi aşıyor. Tutarları düşürün.")

# =========================
# 3) BORÇ ÖDEME (TUTAR)
# =========================
st.divider()
st.subheader("3) Borç Ödeme (Ay Sonu)")

repay_amt_input = 0.0
if can_borrow(month) and float(p["debt"]) > 0:
    st.caption(f"Mevcut borç: **{fmt_tl(float(p['debt']))}**")
    st.info(f"📌 Şu an kasadaki nakit: **{fmt_tl(float(p['holdings']['cash']))}** (Ayı tamamladığınızda nakit değişecektir.)")

    repay_max_preview = float(p["holdings"]["cash"])
    repay_amt_input = safe_number_input(
        "Bu ay borca ödemek istediğiniz tutar (TL)",
        f"repay_amt_{name}_{month}",
        repay_max_preview,
        1000.0
    )
    st.caption(f"➡️ Bu ekranda seçebileceğiniz **maks ödeme**: {fmt_tl(repay_max_preview)}")
else:
    st.caption("Bu ay borç yok veya borç mekanizması aktif değil.")

# =========================
# AYI TAMAMLA
# =========================
btn_label = "✅ Ayı Tamamla" if month < CFG["MONTHS"] else "✅ 12. Ayı Tamamla ve Bitir"

if st.button(btn_label):
    rng = rng_for_player(name, month)

    theft_loss = 0.0
    bank_loss = 0.0
    td_interest = 0.0
    tx_fee_total = 0.0
    spread_cost_total = 0.0
    early_break_penalty_total = 0.0
    repay_amt = 0.0

    # A) SATIŞ/BOZMA (NAKDE ÇEVİR)
    for k, amt in sell_inputs.items():
        amt = float(amt)
        if amt <= 0:
            continue
        amt = min(amt, float(p["holdings"][k]))

        rate = sell_cost_rate(k)
        fee_part = amt * float(CFG["TX_FEE"])
        spr_part = amt * (float(CFG["SPREAD"].get(k, 0.0)) / 2.0)

        net_cash = amt * (1.0 - rate)

        p["holdings"][k] -= amt
        p["holdings"]["cash"] += max(net_cash, 0.0)

        tx_fee_total += fee_part
        spread_cost_total += spr_part

    if month >= 4 and sell_dd_amt > 0 and sell_dd_bank:
        bal = float(p["dd_accounts"].get(sell_dd_bank, 0.0))
        amt = float(min(sell_dd_amt, bal))
        fee_part = amt * fee
        net_cash = amt * (1.0 - fee)
        p["dd_accounts"][sell_dd_bank] = bal - amt
        p["holdings"]["cash"] += max(net_cash, 0.0)
        tx_fee_total += fee_part

    if month >= 4 and sell_td_amt > 0 and sell_td_bank:
        bal = float(p["td_accounts"].get(sell_td_bank, 0.0))
        amt = float(min(sell_td_amt, bal))
        pen_part = amt * pen
        fee_part = amt * fee
        net_cash = amt * (1.0 - pen - fee)
        p["td_accounts"][sell_td_bank] = bal - amt
        p["holdings"]["cash"] += max(net_cash, 0.0)
        early_break_penalty_total += pen_part
        tx_fee_total += fee_part

    # B) GELİR / GİDER
    p["holdings"]["cash"] += income
    p["holdings"]["cash"] -= total_exp

    if p["holdings"]["cash"] < 0:
        deficit = -float(p["holdings"]["cash"])
        if not can_borrow(month):
            p["holdings"]["cash"] = 0.0
            p["defaulted"] = True
            p["finished"] = True
            st.error("⛔ Ay 1–3 döneminde borç yokken açık oluştu: TEMERRÜT!")
            st.rerun()
        else:
            p["debt"] += deficit
            p["holdings"]["cash"] = 0.0

    # C) ALIŞLAR (YATIRIM)
    max_cash_for_buy_now = float(p["holdings"]["cash"])
    total_buy = float(sum(inv_inputs.values())) if inv_inputs else 0.0
    if total_buy > max_cash_for_buy_now + 1e-9 and not can_borrow(month):
        st.error("Ay 1–3'te borç yok: alışlar mevcut nakdi aşıyor → temerrüt olur. Alış tutarlarını azaltın.")
        st.stop()

    for k, buy_amt in inv_inputs.items():
        buy_amt = float(buy_amt)
        if buy_amt <= 0:
            continue

        p["holdings"]["cash"] -= buy_amt
        if p["holdings"]["cash"] < 0 and can_borrow(month):
            deficit2 = -float(p["holdings"]["cash"])
            p["debt"] += deficit2
            p["holdings"]["cash"] = 0.0
        elif p["holdings"]["cash"] < 0 and not can_borrow(month):
            p["holdings"]["cash"] = 0.0
            p["defaulted"] = True
            p["finished"] = True
            st.error("⛔ Ay 1–3 döneminde yatırım yüzünden açık oluştu: TEMERRÜT!")
            st.rerun()

        if k in DEPOSIT_ASSETS:
            fee_part = buy_amt * fee
            net = buy_amt * (1.0 - fee)
            tx_fee_total += fee_part

            if k == "dd":
                bank = p.get("last_dd_bank") or "Banka 1"
                p["dd_accounts"][bank] = float(p["dd_accounts"].get(bank, 0.0) + max(net, 0.0))
            else:
                bank = p.get("last_td_bank") or "Banka 1"
                p["td_accounts"][bank] = float(p["td_accounts"].get(bank, 0.0) + max(net, 0.0))
        else:
            spr_half = float(CFG["SPREAD"].get(k, 0.0)) / 2.0
            fee_part = buy_amt * fee
            spr_part = buy_amt * spr_half
            net = buy_amt * (1.0 - (fee + spr_half))

            tx_fee_total += fee_part
            spread_cost_total += spr_part
            p["holdings"][k] += max(net, 0.0)

    # D) NAKİT HIRSIZLIK
    prob = CFG["CASH_THEFT_PROB_STAGE1"] if month <= 3 else CFG["CASH_THEFT_PROB_STAGE2"]
    if p["holdings"]["cash"] > 0 and rng.random() < prob:
        sev = float(rng.uniform(CFG["CASH_THEFT_SEV_MIN"], CFG["CASH_THEFT_SEV_MAX"]))
        theft_loss = float(p["holdings"]["cash"]) * sev
        p["holdings"]["cash"] -= theft_loss
        st.session_state.theft_banner = {"loss": float(theft_loss), "remain": float(p["holdings"]["cash"])}

    # E) BANKA OLAYI + VADELİ FAİZ
    if month >= 4:
        b_list = banks_for_month(month)
        bmap = {b["Bank"]: b for b in b_list}

        for bank, bal in list(p["dd_accounts"].items()):
            if float(bal) > 0 and bank in bmap and rng.random() < CFG["BANK_INCIDENT_PROB"]:
                guar = float(bmap[bank]["Guarantee"])
                loss = float(bal * (1.0 - guar))
                p["dd_accounts"][bank] = float(max(0.0, bal - loss))
                bank_loss += loss

        for bank, bal in list(p["td_accounts"].items()):
            if float(bal) > 0 and bank in bmap and rng.random() < CFG["BANK_INCIDENT_PROB"]:
                guar = float(bmap[bank]["Guarantee"])
                loss = float(bal * (1.0 - guar))
                p["td_accounts"][bank] = float(max(0.0, bal - loss))
                bank_loss += loss

        for bank, bal in list(p["td_accounts"].items()):
            if float(bal) > 0 and bank in bmap:
                before = float(bal)
                rate = float(bmap[bank]["TD_Rate"])
                after = float(before * (1.0 + rate))
                p["td_accounts"][bank] = after
                td_interest += (after - before)

    # F) PİYASA GETİRİLERİ
    if "eq" in opened:
        eq_r = float(rng.normal(CFG["EQ_MU"], CFG["EQ_SIG"]))
        if month == CFG["CRISIS_MONTH"]:
            eq_r += CFG["CRISIS_EQ"]
        p["holdings"]["eq"] *= (1.0 + eq_r)

    if "cr" in opened:
        cr_r = float(rng.normal(CFG["CR_MU"], CFG["CR_SIG"]))
        if month == CFG["CRISIS_MONTH"]:
            cr_r += CFG["CRISIS_CR"]
        p["holdings"]["cr"] *= (1.0 + cr_r)

    if "pm" in opened:
        pm_r = float(rng.normal(CFG["PM_MU"], CFG["PM_SIG"]))
        if month == CFG["CRISIS_MONTH"]:
            pm_r += CFG["CRISIS_PM"]
        p["holdings"]["pm"] *= (1.0 + pm_r)

    if "fx" in opened:
        fx_r = float(rng.normal(CFG["FX_MU"], CFG["FX_SIG"]))
        if month == CFG["CRISIS_MONTH"]:
            fx_r += CFG["CRISIS_FX"]
        p["holdings"]["fx"] *= (1.0 + fx_r)

    # G) BORÇ FAİZİ + BORÇ ÖDEME (MAKS = O ANDAKİ NAKİT)
    if can_borrow(month) and float(p["debt"]) > 0:
        p["debt"] *= (1.0 + float(CFG["LOAN_RATE"]))

    if can_borrow(month) and float(p["debt"]) > 0 and float(repay_amt_input) > 0:
        repay_amt = min(float(repay_amt_input), float(p["holdings"]["cash"]), float(p["debt"]))
        p["holdings"]["cash"] -= repay_amt
        p["debt"] -= repay_amt

    # H) LOG
    end_cash = float(p["holdings"]["cash"])
    end_inv = float(total_investments(p))
    end_debt = float(p["debt"])
    end_total = float(end_cash + end_inv - end_debt)

    p["log"].append({
        "Ay": month,
        "Aşama": stage_label(month),
        "EnflasyonOranı": infl,
        "Gelir(TL)": income,
        "SabitGider(TL)": fixed_this_month,
        "EkHarcama(TL)": float(extra),
        "İşlemÜcreti(TL)": float(tx_fee_total),
        "SpreadMaliyeti(TL)": float(spread_cost_total),
        "VadeliBozmaCezası(TL)": float(early_break_penalty_total),
        "VadeliFaizGeliri(TL)": float(td_interest),
        "NakitHırsızlıkKayıp(TL)": float(theft_loss),
        "BankaKayıp(TL)": float(bank_loss),
        "BorçÖdeme(TL)": float(repay_amt),
        "DönemSonuNakit(TL)": float(end_cash),
        "DönemSonuYatırım(TL)": float(end_inv),
        "DönemSonuBorç(TL)": float(end_debt),
        "ToplamServet(TL)": float(end_total),
    })

    # I) SABİT GİDERİ BİR SONRAKİ AYA TAŞI (enflasyon giderde)
    if month < CFG["MONTHS"]:
        next_month = month + 1
        next_infl = inflation_rate(next_month)
        p["fixed_current"] = float(fixed_this_month * (1.0 + next_infl))

    # J) AY İLERLET / BİTİR
    if month >= CFG["MONTHS"]:
        p["finished"] = True
    else:
        p["month"] += 1

    st.rerun()

# =========================
# GEÇMİŞ TABLO
# =========================
if p["log"]:
    st.divider()
    st.subheader("📒 Geçmiş (Sade)")
    st.dataframe(pd.DataFrame(p["log"]), use_container_width=True, hide_index=True, height=360)
