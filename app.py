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

    # Nakit hırsızlık (rastgele turlar): banka öncesi daha yüksek
    "CASH_THEFT_PROB_STAGE1": 0.12,  # Ay 1-3
    "CASH_THEFT_PROB_STAGE2": 0.05,  # Ay 4-12
    "CASH_THEFT_SEV_MIN": 0.10,
    "CASH_THEFT_SEV_MAX": 0.35,

    # Banka olayı (çok düşük olasılık)
    "BANK_INCIDENT_PROB": 0.02,  # her banka/ay için olay olasılığı

    # Vadeli mevduat faiz aralığı (aylık) (trade-off için)
    "TD_RATE_MIN": 0.0070,   # %0.70 aylık
    "TD_RATE_MAX": 0.0140,   # %1.40 aylık

    # Güvence aralığı (trade-off için)
    "GUAR_MIN": 0.70,
    "GUAR_MAX": 0.99,

    # Erken bozdurma cezası (bozulan tutarın %'si)
    "EARLY_BREAK_PENALTY": 0.01,  # %1 ceza

    # Riskli varlıklar (aylık)
    "EQ_MU": 0.015,
    "EQ_SIG": 0.060,
    "CR_MU": 0.020,
    "CR_SIG": 0.120,
    "PM_MU": 0.008,
    "PM_SIG": 0.030,
    "FX_MU": 0.010,
    "FX_SIG": 0.040,

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
    return f"{x*100:.0f}%"

def rng_for_global(month: int):
    return np.random.default_rng(st.session_state.seed + month * 999)

def rng_for_player(name: str, month: int):
    return np.random.default_rng((hash(name) % 10000) + month * 1000 + st.session_state.seed)

def bank_count_for_month(month: int) -> int:
    if month < 4:
        return 0
    return min(2 + (month - 4), 8)

def banks_for_month(month: int):
    """
    Trade-off: Vadeli faiz yükseldikçe güvence ortalamada düşer.
    Vadesiz mevduat faizsiz (0).
    """
    n = bank_count_for_month(month)
    if n == 0:
        return []

    r = rng_for_global(month)

    td_rates = r.uniform(CFG["TD_RATE_MIN"], CFG["TD_RATE_MAX"], size=n)
    td_sorted_idx = np.argsort(td_rates)  # düşükten yükseğe

    banks = [None] * n
    for rank, idx in enumerate(td_sorted_idx):
        td = float(td_rates[idx])

        x = rank / max(n - 1, 1)  # 0..1
        base_guar = CFG["GUAR_MAX"] - x * (CFG["GUAR_MAX"] - CFG["GUAR_MIN"])
        noise = float(r.normal(0, 0.015))
        guarantee = float(np.clip(base_guar + noise, CFG["GUAR_MIN"], CFG["GUAR_MAX"]))

        banks[idx] = {
            "Bank": f"Banka {idx + 1}",
            "TD_Rate": td,
            "DD_Rate": 0.0,
            "Guarantee": guarantee
        }
    return banks

def banks_df(month: int) -> pd.DataFrame:
    b = banks_for_month(month)
    if not b:
        return pd.DataFrame()
    df = pd.DataFrame(b)
    df["Vadeli Faiz (Aylık)"] = df["TD_Rate"].map(lambda x: f"{x*100:.2f}%")
    df["Güvence Oranı"] = df["Guarantee"].map(lambda x: f"{x*100:.0f}%")
    return df.sort_values("TD_Rate", ascending=False)[["Bank", "Vadeli Faiz (Aylık)", "Güvence Oranı"]]

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
            "holdings": {k: 0.0 for k in ASSETS},
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
    p.setdefault("last_event", None)
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
    "Vadesiz faizsizdir. Vadeli mevduat ERKEN BOZDURULABİLİR (ceza var)."
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

# Son olay mesajı
if p.get("last_event"):
    kind = p["last_event"].get("kind")
    msg = p["last_event"].get("msg", "")
    if kind in ("theft", "bank"):
        st.warning(msg)
    elif kind == "error":
        st.error(msg)
    elif kind == "info":
        st.info(msg)

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
            st.dataframe(df, use_container_width=True, hide_index=True, height=340)
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
# 0) VADELİ BOZMA (Ay 4+)
# =========================
early_break_amount = 0.0
early_break_penalty = 0.0
selected_break_bank = None

if month >= 4 and td_total(p) > 0:
    st.divider()
    st.subheader("0) Vadeli Bozma (Opsiyonel)")

    st.caption("Vadeli mevduatı istersen bu ay nakde çevirebilirsin. Ceza: bozulan tutarın %1'i (basit model).")

    td_banks = [bk for bk, bal in p["td_accounts"].items() if bal > 0]
    if td_banks:
        selected_break_bank = st.selectbox("Hangi bankadaki vadeli bozulacak?", td_banks)
        max_break = float(p["td_accounts"].get(selected_break_bank, 0.0))

        early_break_amount = st.number_input(
            "Bozdurulacak tutar (TL)",
            min_value=0.0,
            max_value=max_break,
            value=0.0,
            step=1000.0
        )
        early_break_penalty = float(early_break_amount * CFG["EARLY_BREAK_PENALTY"])
        st.write(f"Bozma cezası: **{fmt_tl(early_break_penalty)}** | Nakde geçecek: **{fmt_tl(max(early_break_amount - early_break_penalty, 0.0))}**")

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

# Bu ay giderlerden sonra elde kalacak nakit + (vadeli bozma neti) yatırım için potansiyel kaynaktır
cash_available_for_invest_base = float(p["holdings"]["cash"]) + income - total_exp
cash_available_for_invest_base = max(cash_available_for_invest_base, 0.0)

cash_from_break = float(max(early_break_amount - early_break_penalty, 0.0))
cash_available_for_invest = float(cash_available_for_invest_base + cash_from_break)

# =========================
# 2) YATIRIM (TL ile)
# =========================
st.divider()
st.subheader("2) Yatırım Kararı (TL)")

st.caption("Tüm girişler TL’dir. Toplam yatırım, bu ay yatırılabilir kaynağı aşamaz. Kalan para nakitte kalır (hırsızlık riski).")

inv_inputs = {}

def money_input(label, key, maxv):
    return st.number_input(label, min_value=0.0, max_value=float(maxv), value=0.0, step=1000.0, key=key)

colL, colR = st.columns(2)

with colL:
    if "dd" in opened and month >= 4:
        inv_inputs["dd"] = money_input("Vadesiz Mevduat (TL) — faiz yok", f"dd_amt_{name}_{month}", cash_available_for_invest)
    if "td" in opened and month >= 4:
        inv_inputs["td"] = money_input("Vadeli Mevduat (TL)", f"td_amt_{name}_{month}", cash_available_for_invest)
    if "fx" in opened:
        inv_inputs["fx"] = money_input("Döviz (TL)", f"fx_amt_{name}_{month}", cash_available_for_invest)
    if "pm" in opened:
        inv_inputs["pm"] = money_input("Kıymetli Metal (TL)", f"pm_amt_{name}_{month}", cash_available_for_invest)

with colR:
    if "eq" in opened:
        inv_inputs["eq"] = money_input("Hisse Senedi (TL)", f"eq_amt_{name}_{month}", cash_available_for_invest)
    if "cr" in opened:
        inv_inputs["cr"] = money_input("Kripto (TL)", f"cr_amt_{name}_{month}", cash_available_for_invest)

total_alloc = float(sum(inv_inputs.values())) if inv_inputs else 0.0
remaining_cash_after_alloc = float(max(cash_available_for_invest - total_alloc, 0.0))

st.write(f"Yatırılabilir kaynak: **{fmt_tl(cash_available_for_invest)}**")
st.write(f"Bu ay yatırım toplamı: **{fmt_tl(total_alloc)}**")
st.write(f"Yatırım sonrası nakitte kalacak: **{fmt_tl(remaining_cash_after_alloc)}**")

if total_alloc > cash_available_for_invest + 1e-9:
    st.error("Toplam yatırım, bu ay yatırılabilir kaynağı aşıyor. Tutarları düşürün.")

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
    if total_alloc > cash_available_for_invest + 1e-9:
        st.stop()

    rng = rng_for_player(name, month)

    repay_amt = 0.0
    cash_theft_loss = 0.0
    bank_incident_loss = 0.0
    td_interest_income = 0.0
    early_break_loss = 0.0

    # 0) Vade bozma uygula (önce) — mevcut TD'den düş, nakde ekle (ceza kayıp)
    if month >= 4 and early_break_amount > 0 and selected_break_bank:
        bal = float(p["td_accounts"].get(selected_break_bank, 0.0))
        amt = float(min(early_break_amount, bal))
        pen = float(amt * CFG["EARLY_BREAK_PENALTY"])
        net_cash = float(max(amt - pen, 0.0))

        p["td_accounts"][selected_break_bank] = float(bal - amt)
        p["holdings"]["cash"] += net_cash
        early_break_loss = float(pen)

        p["last_event"] = {"kind": "info", "msg": f"⏳ Vadeli bozdurdun: **{fmt_tl(amt)}** | Ceza: **{fmt_tl(pen)}** | Nakde geçen: **{fmt_tl(net_cash)}**"}

    # 1) gelir ekle
    p["holdings"]["cash"] += income

    # 2) giderleri öde
    p["holdings"]["cash"] -= total_exp

    # açık varsa
    if p["holdings"]["cash"] < 0:
        deficit = -float(p["holdings"]["cash"])
        if not can_borrow(month):
            p["holdings"]["cash"] = 0.0
            p["defaulted"] = True
            p["finished"] = True
            p["last_event"] = {"kind": "error", "msg": "⛔ Ay 1–3 döneminde borç yokken açık oluştu: TEMERRÜT!"}
            st.rerun()
        else:
            p["debt"] += deficit
            p["holdings"]["cash"] = 0.0

    # 3) yatırım aktarımı (TL)
    for k, amt in inv_inputs.items():
        amt = float(amt)
        if amt <= 0:
            continue

        if k == "dd":
            bank = p.get("last_dd_bank") or "Banka 1"
            p["dd_accounts"][bank] = float(p["dd_accounts"].get(bank, 0.0) + amt)
        elif k == "td":
            bank = p.get("last_td_bank") or "Banka 1"
            p["td_accounts"][bank] = float(p["td_accounts"].get(bank, 0.0) + amt)
        else:
            p["holdings"][k] += amt

        p["holdings"]["cash"] -= amt

    # yatırım sonrası nakit negatife düştüyse
    if p["holdings"]["cash"] < 0:
        deficit2 = -float(p["holdings"]["cash"])
        if can_borrow(month):
            p["debt"] += deficit2
            p["holdings"]["cash"] = 0.0
        else:
            p["holdings"]["cash"] = 0.0
            p["defaulted"] = True
            p["finished"] = True
            p["last_event"] = {"kind": "error", "msg": "⛔ Ay 1–3 döneminde yatırım yüzünden açık oluştu: TEMERRÜT!"}
            st.rerun()

    # 4) Nakit hırsızlık
    theft_prob = CFG["CASH_THEFT_PROB_STAGE1"] if month <= 3 else CFG["CASH_THEFT_PROB_STAGE2"]
    if p["holdings"]["cash"] > 0 and rng.random() < theft_prob:
        sev = float(rng.uniform(CFG["CASH_THEFT_SEV_MIN"], CFG["CASH_THEFT_SEV_MAX"]))
        cash_theft_loss = float(p["holdings"]["cash"]) * sev
        p["holdings"]["cash"] -= cash_theft_loss
        p["last_event"] = {"kind": "theft", "msg": f"🚨 Nakit hırsızlığı! Kayıp: **{fmt_tl(cash_theft_loss)}**"}

    # 5) Banka olayı + vadeli faiz (Ay4+)
    if month >= 4:
        b_list = banks_for_month(month)
        bmap = {b["Bank"]: b for b in b_list}

        # banka olayı: güvence dışı kısım kayıp (dd + td)
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
            p["last_event"] = {"kind": "bank", "msg": f"🏦⚠️ Banka olayı! Mevduat kaybı: **{fmt_tl(bank_incident_loss)}**"}

        # vadeli faiz getirisi (sadece td)
        for bank, bal in list(p["td_accounts"].items()):
            if bal > 0 and bank in bmap:
                before = float(bal)
                rate = float(bmap[bank]["TD_Rate"])
                after = float(before * (1.0 + rate))
                p["td_accounts"][bank] = after
                td_interest_income += (after - before)

    # 6) Riskli varlık getirileri
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

    # 7) Borç faizi
    if can_borrow(month) and float(p["debt"]) > 0:
        p["debt"] *= (1.0 + float(CFG["LOAN_RATE"]))

    # 8) Borç geri ödeme
    if can_borrow(month) and float(p["debt"]) > 0 and repay_pct > 0:
        target = float(p["debt"]) * (float(repay_pct) / 100.0)
        repay_amt = min(float(p["holdings"]["cash"]), target)
        p["holdings"]["cash"] -= repay_amt
        p["debt"] -= repay_amt
        if p["debt"] < 0:
            p["debt"] = 0.0

    # 9) Dönem sonu
    end_cash = float(p["holdings"]["cash"])
    end_inv = total_investments(p)
    end_debt = float(p["debt"])
    end_total = end_cash + end_inv - end_debt

    # 10) Log
    p["log"].append({
        "Ay": month,
        "Aşama": stage_label(month),
        "EnflasyonOranı": infl,
        "Gelir(TL)": income,
        "SabitGider(TL)": fixed_this_month,
        "EkHarcama(TL)": float(extra),
        "Tasarruf(TL)": float(max(income - total_exp, 0.0)),
        "VadeBozma(TL)": float(early_break_amount),
        "VadeBozmaCezası(TL)": float(early_break_loss),
        "DD_Yatırım(TL)": float(inv_inputs.get("dd", 0.0)),
        "TD_Yatırım(TL)": float(inv_inputs.get("td", 0.0)),
        "SeçilenDD_Banka": p.get("last_dd_bank", "") if month >= 4 else "",
        "SeçilenTD_Banka": p.get("last_td_bank", "") if month >= 4 else "",
        "VadeliFaizGeliri(TL)": float(td_interest_income),
        "NakitKaybı(TL)": float(cash_theft_loss),
        "BankaKaybı(TL)": float(bank_incident_loss),
        "BorçÖdeme(TL)": float(repay_amt),
        "DönemSonuNakit(TL)": end_cash,
        "DönemSonuYatırım(TL)": end_inv,
        "DönemSonuBorç(TL)": end_debt,
        "ToplamServet(TL)": end_total,
    })

    # 11) Sabit gideri bir sonraki aya taşı (bileşik artış)
    if month < CFG["MONTHS"]:
        next_month = month + 1
        next_infl = inflation_rate_for_month(next_month)
        p["fixed_current"] = float(fixed_this_month * (1.0 + next_infl))

    # 12) Ay ilerlet / bitir
    if month >= CFG["MONTHS"]:
        p["finished"] = True
    else:
        p["month"] += 1

    st.rerun()

# =========================
# GEÇMİŞ TABLO (EKRANA SIĞSIN)
# =========================
if p["log"]:
    st.divider()
    st.subheader("📒 Geçmiş (Sade)")

    df = pd.DataFrame(p["log"]).copy()
    for col in df.columns:
        if "(TL)" in col:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).round(0)

    with st.expander("Geçmiş Tablosunu Göster/Gizle", expanded=True):
        st.dataframe(df, use_container_width=True, hide_index=True, height=340)
