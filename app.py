import streamlit as st
import numpy as np
import pandas as pd

st.set_page_config(page_title="Finans Neden Var?", layout="wide")

# =========================
# KİLİTLİ BAŞLANGIÇ DEĞERLERİ
# =========================
DEFAULT_MONTHLY_INCOME = 60000
START_FIXED_COST = 30000  # Ay1 sabit gider

# =========================
# AYARLAR
# =========================
CFG = {
    "MONTHS": 12,

    # Enflasyon: %20 ile başlar, her ay +%5 artar
    "INFL_START": 0.20,
    "INFL_STEP": 0.05,

    # Nakit hırsızlık
    "CASH_THEFT_PROB_STAGE1": 0.12,  # Ay 1-3
    "CASH_THEFT_PROB_STAGE2": 0.05,  # Ay 4-12
    "CASH_THEFT_SEV_MIN": 0.10,
    "CASH_THEFT_SEV_MAX": 0.35,

    # Banka olayı (çok düşük)
    "BANK_INCIDENT_PROB": 0.02,

    # Vadeli faiz aralığı (aylık) - trade-off
    "TD_RATE_MIN": 0.0070,
    "TD_RATE_MAX": 0.0140,

    # Güvence aralığı (trade-off)
    "GUAR_MIN": 0.70,
    "GUAR_MAX": 0.99,

    # Vadeli bozma cezası (bozulan tutarın %'si)
    "EARLY_BREAK_PENALTY": 0.01,  # %1

    # İŞLEM ÜCRETİ (tüm alım/satım + mevduat giriş/çıkış)
    "TX_FEE": 0.005,  # %0.5 komisyon

    # SPREAD (alış-satış farkı): toplam spread. Alışta yarısı, satışta yarısı uygulanır.
    "SPREAD": {
        "fx": 0.010,  # %1.0
        "pm": 0.012,  # %1.2
        "eq": 0.020,  # %2.0
        "cr": 0.050,  # %5.0
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

    # Kredi faizi (aylık)
    "LOAN_RATE": 0.025,
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

# =========================
# YARDIMCI FONKSİYONLAR
# =========================
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

def can_borrow(month: int) -> bool:
    return month >= 4

def inflation_rate_for_month(month: int) -> float:
    return float(CFG["INFL_START"] + CFG["INFL_STEP"] * (month - 1))

def fmt_tl(x: float) -> str:
    return f"{x:,.0f} TL".replace(",", ".")

def fmt_pct(x: float) -> str:
    return f"{x*100:.1f}%"

def rng_for_global(month: int):
    return np.random.default_rng(st.session_state.seed + month * 999)

def rng_for_player(name: str, month: int):
    return np.random.default_rng((hash(name) % 10000) + month * 1000 + st.session_state.seed)

def bank_count_for_month(month: int) -> int:
    if month < 4: return 0
    return min(2 + (month - 4), 8)

def banks_for_month(month: int):
    n = bank_count_for_month(month)
    if n == 0:
        return []

    r = rng_for_global(month)
    td_rates = r.uniform(CFG["TD_RATE_MIN"], CFG["TD_RATE_MAX"], size=n)
    td_sorted_idx = np.argsort(td_rates)  # düşükten yükseğe

    banks = [None] * n
    for rank, idx in enumerate(td_sorted_idx):
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
    """Alım maliyeti oranı: komisyon + spread/2 (riskli varlıklar için)."""
    fee = float(CFG["TX_FEE"])
    spr = float(CFG["SPREAD"].get(asset_key, 0.0))
    return fee + spr / 2.0

def sell_cost_rate(asset_key: str) -> float:
    """Satış maliyeti oranı: komisyon + spread/2 (riskli varlıklar için)."""
    fee = float(CFG["TX_FEE"])
    spr = float(CFG["SPREAD"].get(asset_key, 0.0))
    return fee + spr / 2.0

# =========================
# SESSION
# =========================
if "seed" not in st.session_state:
    st.session_state.seed = 20260209
if "players" not in st.session_state:
    st.session_state.players = {}

def get_player(name: str) -> dict:
    if name not in st.session_state.players:
        st.session_state.players[name] = {
            "month": 1,
            "finished": False,
            "defaulted": False,
            "debt": 0.0,
            "holdings": {k: 0.0 for k in ASSETS},  # cash, fx, pm, eq, cr
            "dd_accounts": {},  # bank -> balance
            "td_accounts": {},  # bank -> balance
            "log": [],
            "income_fixed": float(DEFAULT_MONTHLY_INCOME),
            "fixed_current": float(START_FIXED_COST),
            "last_event": None,
            "last_dd_bank": None,
            "last_td_bank": None,
        }
    p = st.session_state.players[name]
    for k in ASSETS:
        p["holdings"].setdefault(k, 0.0)
    p.setdefault("dd_accounts", {})
    p.setdefault("td_accounts", {})
    p.setdefault("log", [])
    return p

def dd_total(p: dict) -> float:
    return float(sum(p.get("dd_accounts", {}).values()))

def td_total(p: dict) -> float:
    return float(sum(p.get("td_accounts", {}).values()))

def total_investments(p: dict) -> float:
    other = float(sum(v for k, v in p["holdings"].items() if k != "cash"))
    return float(other + dd_total(p) + td_total(p))

def net_wealth(p: dict) -> float:
    return float(p["holdings"]["cash"] + total_investments(p) - float(p.get("debt", 0.0)))

# =========================
# UI - ÜST
# =========================
st.title("🎮 Finansal Piyasalar Neden Var? (1. Hafta Oyunu)")
st.caption(
    "Ay 1–3 borç yok (açık → temerrüt). Ay 4+ kredi var. Enflasyon sabit gideri artırır. "
    "Nakit bazı turlarda çalınabilir. Ay 4+ bankalar: vadeli faiz + güvence trade-off. "
    "Vadesiz faizsizdir. Tüm varlıklar bozdurulabilir/satılabilir. Alış-satış farkı (spread) + işlem ücreti (komisyon) vardır."
)

c1, c2 = st.columns([1, 3])
with c1:
    if st.button("🧹 Oyunu Sıfırla"):
        st.session_state.clear()
        st.rerun()
with c2:
    st.caption("Gelir ve başlangıç sabit gideri standarttır; oyuncu değiştiremez.")

name = st.text_input("Oyuncu Adı")
if not name:
    st.stop()

p = get_player(name)

# =========================
# LEADERBOARD
# =========================
st.subheader("🏆 Oyuncu Sıralaması")
rows = []
for pname, pp in st.session_state.players.items():
    cash = float(pp["holdings"].get("cash", 0.0))
    inv_other = float(sum(v for k, v in pp["holdings"].items() if k != "cash"))
    inv = inv_other + float(sum(pp.get("dd_accounts", {}).values())) + float(sum(pp.get("td_accounts", {}).values()))
    debt = float(pp.get("debt", 0.0))
    net = cash + inv - debt
    status = "Devam"
    if pp.get("finished") and pp.get("defaulted"):
        status = "Temerrüt"
    elif pp.get("finished"):
        status = "Bitti"
    month_done = CFG["MONTHS"] if pp.get("finished") else max(int(pp.get("month", 1)) - 1, 0)
    rows.append({"Sıra": 0, "Oyuncu": pname, "Durum": status, "Ay": month_done,
                 "Servet(Net)": round(net, 0), "Borç": round(debt, 0)})

lb = pd.DataFrame(rows).sort_values(["Servet(Net)", "Borç"], ascending=[False, True]).reset_index(drop=True)
lb["Sıra"] = lb.index + 1
st.dataframe(lb, use_container_width=True, hide_index=True, height=220)

st.divider()

# =========================
# OYUN BİTTİ EKRANI
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
            df = pd.DataFrame(p["log"]).copy()
            for col in df.columns:
                if "(TL)" in col:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).round(0)
            st.dataframe(df, use_container_width=True, hide_index=True, height=360)
    st.stop()

# =========================
# AY PANELİ
# =========================
month = int(p["month"])
opened = open_assets_by_month(month)

income = float(p["income_fixed"])
infl = inflation_rate_for_month(month)
fixed_this_month = float(p["fixed_current"])

st.subheader(f"📅 Ay {month} / {CFG['MONTHS']} | Aşama: {stage_label(month)}")
st.progress((month - 1) / CFG["MONTHS"])

k1, k2, k3 = st.columns(3)
k1.metric("Enflasyon Oranı", fmt_pct(infl))
k2.metric("Gelir (Sabit)", fmt_tl(income))
k3.metric("Bu Ay Sabit Gider", fmt_tl(fixed_this_month))

m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("Nakit", fmt_tl(p["holdings"]["cash"]))
m2.metric("Vadesiz (Toplam)", fmt_tl(dd_total(p)))
m3.metric("Vadeli (Toplam)", fmt_tl(td_total(p)))
m4.metric("Diğer Yatırımlar", fmt_tl(sum(v for k, v in p["holdings"].items() if k != "cash")))
m5.metric("Borç", fmt_tl(p["debt"]))
m6.metric("Servet (Net)", fmt_tl(net_wealth(p)))

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
        p["last_dd_bank"] = st.selectbox(
            "Vadesiz mevduat için bankanı seç",
            banks_names,
            index=banks_names.index(p["last_dd_bank"]) if p["last_dd_bank"] in banks_names else 0
        )
    with cB:
        p["last_td_bank"] = st.selectbox(
            "Vadeli mevduat için bankanı seç",
            banks_names,
            index=banks_names.index(p["last_td_bank"]) if p["last_td_bank"] in banks_names else 0
        )

# =========================
# 0) BOZDURMA / SATIŞ (Opsiyonel)
# =========================
st.divider()
st.subheader("0) Bozdurma / Satış (Opsiyonel)")

st.caption(
    "Bu ay istersen yatırımlarının bir kısmını nakde çevirebilirsin. "
    "Riskli varlıklarda: komisyon + spread (alış-satış farkı). "
    "Mevduatta: komisyon var; vadeli bozarsan ayrıca ceza var."
)

# Satış girişleri (TL olarak)
sell_inputs = {"fx": 0.0, "pm": 0.0, "eq": 0.0, "cr": 0.0}
sell_dd_amt = 0.0
sell_td_amt = 0.0
sell_td_bank = None
sell_dd_bank = None

colS1, colS2 = st.columns(2)

with colS1:
    # Riskli varlıklardan satış
    for k in ["fx", "pm", "eq", "cr"]:
        if k in opened:
            maxv = float(p["holdings"].get(k, 0.0))
            if maxv > 0:
                rate = sell_cost_rate(k)
                sell_inputs[k] = st.number_input(
                    f"{ASSETS[k]} Satış (TL)  | Maliyet: {rate*100:.2f}%",
                    min_value=0.0,
                    max_value=maxv,
                    value=0.0,
                    step=1000.0,
                    key=f"sell_{k}_{name}_{month}"
                )

with colS2:
    # Vadesiz çekme
    if month >= 4 and dd_total(p) > 0:
        dd_banks = [bk for bk, bal in p["dd_accounts"].items() if bal > 0]
        if dd_banks:
            sell_dd_bank = st.selectbox("Vadesizden çekilecek banka", dd_banks, key=f"ddbank_{name}_{month}")
            max_dd = float(p["dd_accounts"].get(sell_dd_bank, 0.0))
            sell_dd_amt = st.number_input(
                f"Vadesiz Çekim (TL) | Komisyon: {CFG['TX_FEE']*100:.2f}%",
                min_value=0.0,
                max_value=max_dd,
                value=0.0,
                step=1000.0,
                key=f"sell_dd_{name}_{month}"
            )

    # Vadeli bozma
    if month >= 4 and td_total(p) > 0:
        td_banks = [bk for bk, bal in p["td_accounts"].items() if bal > 0]
        if td_banks:
            sell_td_bank = st.selectbox("Vadeliden bozulacak banka", td_banks, key=f"tdbank_{name}_{month}")
            max_td = float(p["td_accounts"].get(sell_td_bank, 0.0))
            sell_td_amt = st.number_input(
                f"Vadeli Bozma (TL) | Ceza: {CFG['EARLY_BREAK_PENALTY']*100:.2f}% + Komisyon: {CFG['TX_FEE']*100:.2f}%",
                min_value=0.0,
                max_value=max_td,
                value=0.0,
                step=1000.0,
                key=f"sell_td_{name}_{month}"
            )

# =========================
# 1) BÜTÇE
# =========================
st.divider()
st.subheader("1) Bütçe (Bu Ay)")

available_without_borrow = p["holdings"]["cash"] + income
extra_max = int(max(0.0, available_without_borrow - fixed_this_month)) if not can_borrow(month) else int(income * 3)
extra_default = min(5000, max(0, extra_max))
extra = st.number_input("Ek Harcama", 0, max(0, extra_max), extra_default, 1000)

total_exp = fixed_this_month + float(extra)
saving = max(income - total_exp, 0.0)

st.write(f"Gelir: **{fmt_tl(income)}** | Toplam gider: **{fmt_tl(total_exp)}** | Tasarruf: **{fmt_tl(saving)}**")

if (not can_borrow(month)) and (total_exp > available_without_borrow):
    st.error("Ay 1–3'te borç yok. Bu bütçe nakit+geliri aşıyor → temerrüt olur. Ek harcamayı düşürün.")

# Bu ay giderlerden sonra elde kalacak nakit (satışlar hariç)
cash_available_for_invest = float(p["holdings"]["cash"]) + income - total_exp
cash_available_for_invest = max(cash_available_for_invest, 0.0)

# =========================
# 2) YATIRIM (TL ile) — ayrım: vadeli/vadesiz ayrı girilir
# =========================
st.divider()
st.subheader("2) Yatırım Kararı (TL) — Alım (Komisyon/Spread Var)")

st.caption(
    "Tüm girişler TL’dir. Alımda komisyon + (varsa) spread uygulanır; bu yüzden yatırdığın TL'nin tamamı varlığa dönüşmez. "
    "Toplam alım, bu ay yatırılabilir kaynağı aşmamalı. Kalan para nakitte kalır (hırsızlık riski)."
)

inv_inputs = {}

def money_input(label, key, maxv):
    return st.number_input(label, min_value=0.0, max_value=float(maxv), value=0.0, step=1000.0, key=key)

colB1, colB2 = st.columns(2)

with colB1:
    if "dd" in opened and month >= 4:
        inv_inputs["dd"] = money_input(
            f"Vadesiz Mevduat ALIŞ (TL) | Komisyon: {CFG['TX_FEE']*100:.2f}%",
            f"buy_dd_{name}_{month}", cash_available_for_invest
        )
    if "td" in opened and month >= 4:
        inv_inputs["td"] = money_input(
            f"Vadeli Mevduat ALIŞ (TL) | Komisyon: {CFG['TX_FEE']*100:.2f}%",
            f"buy_td_{name}_{month}", cash_available_for_invest
        )
    if "fx" in opened:
        inv_inputs["fx"] = money_input(
            f"Döviz ALIŞ (TL) | Maliyet: {buy_cost_rate('fx')*100:.2f}%",
            f"buy_fx_{name}_{month}", cash_available_for_invest
        )
    if "pm" in opened:
        inv_inputs["pm"] = money_input(
            f"Kıymetli Metal ALIŞ (TL) | Maliyet: {buy_cost_rate('pm')*100:.2f}%",
            f"buy_pm_{name}_{month}", cash_available_for_invest
        )

with colB2:
    if "eq" in opened:
        inv_inputs["eq"] = money_input(
            f"Hisse Senedi ALIŞ (TL) | Maliyet: {buy_cost_rate('eq')*100:.2f}%",
            f"buy_eq_{name}_{month}", cash_available_for_invest
        )
    if "cr" in opened:
        inv_inputs["cr"] = money_input(
            f"Kripto ALIŞ (TL) | Maliyet: {buy_cost_rate('cr')*100:.2f}%",
            f"buy_cr_{name}_{month}", cash_available_for_invest
        )

total_buy = float(sum(inv_inputs.values())) if inv_inputs else 0.0
st.write(f"Bu ay toplam ALIŞ (brüt): **{fmt_tl(total_buy)}**")
if total_buy > cash_available_for_invest + 1e-9:
    st.error("Toplam alım, bu ay yatırılabilir kaynağı aşıyor. Tutarları düşürün.")

# =========================
# 3) BORÇ GERİ ÖDEME
# =========================
st.divider()
st.subheader("3) Borç Geri Ödeme (Ay Sonu)")

repay_pct = 0
if month >= 4 and float(p["debt"]) > 0:
    repay_pct = st.slider("Borcun ne kadarını ödemek istersiniz? (%)", 0, 100, 20, 5)
else:
    st.caption("Bu ay borç yok veya borç mekanizması henüz aktif değil.")

# =========================
# AYI TAMAMLA
# =========================
btn_label = "✅ Ayı Tamamla" if month < CFG["MONTHS"] else "✅ 12. Ayı Tamamla ve Bitir"

if st.button(btn_label):
    if total_buy > cash_available_for_invest + 1e-9:
        st.stop()

    rng = rng_for_player(name, month)

    # İzleme kalemleri
    repay_amt = 0.0
    cash_theft_loss = 0.0
    bank_incident_loss = 0.0
    td_interest_income = 0.0

    tx_fee_total = 0.0
    spread_cost_total = 0.0
    early_break_loss = 0.0

    # -----------------------
    # A) SATIŞ/BOZMA ÖNCE UYGULANIR (nakit yaratır)
    # -----------------------
    # Riskli varlık satışları
    for k, sell_amt in sell_inputs.items():
        sell_amt = float(sell_amt)
        if sell_amt <= 0:
            continue
        maxv = float(p["holdings"].get(k, 0.0))
        sell_amt = min(sell_amt, maxv)

        fee = float(CFG["TX_FEE"])
        spr_half = float(CFG["SPREAD"].get(k, 0.0)) / 2.0
        cost_rate = fee + spr_half

        fee_part = sell_amt * fee
        spr_part = sell_amt * spr_half
        net_cash = sell_amt * (1.0 - cost_rate)

        p["holdings"][k] -= sell_amt
        p["holdings"]["cash"] += net_cash

        tx_fee_total += fee_part
        spread_cost_total += spr_part

    # Vadesiz çekim (komisyon var)
    if month >= 4 and sell_dd_amt > 0 and sell_dd_bank:
        bal = float(p["dd_accounts"].get(sell_dd_bank, 0.0))
        amt = float(min(sell_dd_amt, bal))
        fee = float(CFG["TX_FEE"])
        fee_part = amt * fee
        net_cash = amt * (1.0 - fee)

        p["dd_accounts"][sell_dd_bank] = bal - amt
        p["holdings"]["cash"] += net_cash

        tx_fee_total += fee_part

    # Vadeli bozma (ceza + komisyon)
    if month >= 4 and sell_td_amt > 0 and sell_td_bank:
        bal = float(p["td_accounts"].get(sell_td_bank, 0.0))
        amt = float(min(sell_td_amt, bal))

        pen = float(CFG["EARLY_BREAK_PENALTY"])
        fee = float(CFG["TX_FEE"])

        pen_part = amt * pen
        fee_part = amt * fee
        net_cash = amt * (1.0 - pen - fee)

        p["td_accounts"][sell_td_bank] = bal - amt
        p["holdings"]["cash"] += max(net_cash, 0.0)

        early_break_loss += pen_part
        tx_fee_total += fee_part

    # -----------------------
    # B) GELİR / GİDER
    # -----------------------
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

    # -----------------------
    # C) ALIŞLAR (komisyon/spread ile nete dönüşür)
    # -----------------------
    for k, buy_amt in inv_inputs.items():
        buy_amt = float(buy_amt)
        if buy_amt <= 0:
            continue

        # Nakitten brüt tutarı düş
        p["holdings"]["cash"] -= buy_amt

        if k in ("dd", "td"):
            # mevduat: spread yok, komisyon var
            fee = float(CFG["TX_FEE"])
            fee_part = buy_amt * fee
            net = buy_amt * (1.0 - fee)

            tx_fee_total += fee_part

            if k == "dd":
                bank = p.get("last_dd_bank") or "Banka 1"
                p["dd_accounts"][bank] = float(p["dd_accounts"].get(bank, 0.0) + net)
            else:
                bank = p.get("last_td_bank") or "Banka 1"
                p["td_accounts"][bank] = float(p["td_accounts"].get(bank, 0.0) + net)

        else:
            # riskli varlık: komisyon + spread/2
            fee = float(CFG["TX_FEE"])
            spr_half = float(CFG["SPREAD"].get(k, 0.0)) / 2.0
            fee_part = buy_amt * fee
            spr_part = buy_amt * spr_half
            net = buy_amt * (1.0 - (fee + spr_half))

            tx_fee_total += fee_part
            spread_cost_total += spr_part

            p["holdings"][k] += max(net, 0.0)

    # alım sonrası nakit negatifse
    if p["holdings"]["cash"] < 0:
        deficit2 = -float(p["holdings"]["cash"])
        if can_borrow(month):
            p["debt"] += deficit2
            p["holdings"]["cash"] = 0.0
        else:
            p["holdings"]["cash"] = 0.0
            p["defaulted"] = True
            p["finished"] = True
            st.error("⛔ Ay 1–3 döneminde yatırım yüzünden açık oluştu: TEMERRÜT!")
            st.rerun()

    # -----------------------
    # D) NAKİT HIRSIZLIK
    # -----------------------
    theft_prob = CFG["CASH_THEFT_PROB_STAGE1"] if month <= 3 else CFG["CASH_THEFT_PROB_STAGE2"]
    if p["holdings"]["cash"] > 0 and rng.random() < theft_prob:
        sev = float(rng.uniform(CFG["CASH_THEFT_SEV_MIN"], CFG["CASH_THEFT_SEV_MAX"]))
        cash_theft_loss = float(p["holdings"]["cash"]) * sev
        p["holdings"]["cash"] -= cash_theft_loss
        st.warning(f"🚨 Nakit hırsızlığı! Kayıp: {fmt_tl(cash_theft_loss)}")

    # -----------------------
    # E) BANKA OLAYI + VADELİ FAİZ
    # -----------------------
    if month >= 4:
        b_list = banks_for_month(month)
        bmap = {b["Bank"]: b for b in b_list}

        # banka olayı (dd + td): güvence dışı kısım kayıp
        for bank, bal in list(p["dd_accounts"].items()):
            if bal > 0 and bank in bmap and rng.random() < CFG["BANK_INCIDENT_PROB"]:
                guar = float(bmap[bank]["Guarantee"])
                loss = float(bal * (1.0 - guar))
                p["dd_accounts"][bank] = float(max(0.0, bal - loss))
                bank_incident_loss += loss

        for bank, bal in list(p["td_accounts"].items()):
            if bal > 0 and bank in bmap and rng.random() < CFG["BANK_INCIDENT_PROB"]:
                guar = float(bmap[bank]["Guarantee"])
                loss = float(bal * (1.0 - guar))
                p["td_accounts"][bank] = float(max(0.0, bal - loss))
                bank_incident_loss += loss

        if bank_incident_loss > 0:
            st.warning(f"🏦⚠️ Banka olayı! Mevduat kaybı: {fmt_tl(bank_incident_loss)}")

        # vadeli faiz (sadece td)
        for bank, bal in list(p["td_accounts"].items()):
            if bal > 0 and bank in bmap:
                before = float(bal)
                rate = float(bmap[bank]["TD_Rate"])
                after = float(before * (1.0 + rate))
                p["td_accounts"][bank] = after
                td_interest_income += (after - before)

    # -----------------------
    # F) PİYASA GETİRİLERİ (değer üstünden)
    # -----------------------
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

    # -----------------------
    # G) BORÇ FAİZİ + ÖDEME
    # -----------------------
    if can_borrow(month) and float(p["debt"]) > 0:
        p["debt"] *= (1.0 + float(CFG["LOAN_RATE"]))

    if can_borrow(month) and float(p["debt"]) > 0 and repay_pct > 0:
        target = float(p["debt"]) * (float(repay_pct) / 100.0)
        repay_amt = min(float(p["holdings"]["cash"]), target)
        p["holdings"]["cash"] -= repay_amt
        p["debt"] -= repay_amt
        if p["debt"] < 0:
            p["debt"] = 0.0

    # -----------------------
    # H) DÖNEM SONU + LOG
    # -----------------------
    end_cash = float(p["holdings"]["cash"])
    end_inv = total_investments(p)
    end_debt = float(p["debt"])
    end_total = end_cash + end_inv - end_debt

    p["log"].append({
        "Ay": month,
        "Aşama": stage_label(month),
        "EnflasyonOranı": infl,
        "Gelir(TL)": income,
        "SabitGider(TL)": fixed_this_month,
        "EkHarcama(TL)": float(extra),

        "SAT_FX(TL)": float(sell_inputs.get("fx", 0.0)),
        "SAT_PM(TL)": float(sell_inputs.get("pm", 0.0)),
        "SAT_EQ(TL)": float(sell_inputs.get("eq", 0.0)),
        "SAT_CR(TL)": float(sell_inputs.get("cr", 0.0)),
        "VadesizÇekim(TL)": float(sell_dd_amt),
        "VadeliBozma(TL)": float(sell_td_amt),

        "AL_DD(TL)": float(inv_inputs.get("dd", 0.0)),
        "AL_TD(TL)": float(inv_inputs.get("td", 0.0)),
        "AL_FX(TL)": float(inv_inputs.get("fx", 0.0)),
        "AL_PM(TL)": float(inv_inputs.get("pm", 0.0)),
        "AL_EQ(TL)": float(inv_inputs.get("eq", 0.0)),
        "AL_CR(TL)": float(inv_inputs.get("cr", 0.0)),

        "İşlemÜcreti(TL)": float(tx_fee_total),
        "SpreadMaliyeti(TL)": float(spread_cost_total),
        "VadeliBozmaCezası(TL)": float(early_break_loss),

        "VadeliFaizGeliri(TL)": float(td_interest_income),
        "NakitKaybı(TL)": float(cash_theft_loss),
        "BankaKaybı(TL)": float(bank_incident_loss),
        "BorçÖdeme(TL)": float(repay_amt),

        "DönemSonuNakit(TL)": end_cash,
        "DönemSonuYatırım(TL)": end_inv,
        "DönemSonuBorç(TL)": end_debt,
        "ToplamServet(TL)": end_total,
    })

    # sabit gideri bir sonraki aya taşı
    if month < CFG["MONTHS"]:
        next_month = month + 1
        next_infl = inflation_rate_for_month(next_month)
        p["fixed_current"] = float(fixed_this_month * (1.0 + next_infl))

    # ay ilerlet / bitir
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

    df = pd.DataFrame(p["log"]).copy()
    for col in df.columns:
        if "(TL)" in col:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).round(0)

    with st.expander("Geçmiş Tablosunu Göster/Gizle", expanded=True):
        st.dataframe(df, use_container_width=True, hide_index=True, height=360)
