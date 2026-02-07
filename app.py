import time
import streamlit as st
import numpy as np
import pandas as pd

st.set_page_config(page_title="Finans Neden Var?", layout="wide")

# =========================
# AYARLAR
# =========================
CFG = {
    "MONTHS": 12,

    # ENFLASYON (aylık)
    "INFLATION_M": 0.020,  # %2 / ay

    # Kurum yokken elde nakit riski
    "CASH_LOSS_PROB": 0.05,
    "CASH_LOSS_SEV": 0.10,

    # Mevduat (aylık)
    "DD_RATE": 0.003,   # vadesiz
    "TD_RATE": 0.010,   # vadeli

    # Riskli varlıklar (aylık)
    "EQ_MU": 0.015,
    "EQ_SIG": 0.060,
    "CR_MU": 0.020,
    "CR_SIG": 0.120,
    "PM_MU": 0.008,
    "PM_SIG": 0.030,
    "FX_MU": 0.010,
    "FX_SIG": 0.040,

    # Makro kriz ayı
    "CRISIS_MONTH": 6,
    "CRISIS_EQ": -0.12,
    "CRISIS_CR": -0.20,
    "CRISIS_PM": +0.04,
    "CRISIS_FX": +0.07,

    # Kredi faizi (aylık)
    "LOAN_RATE": 0.025,  # %2.5 / ay

    # Karar süreleri (saniye)
    "TIMER_STAGE_1": 60,  # Ay 1-3
    "TIMER_STAGE_2": 75,  # Ay 4-5
    "TIMER_STAGE_3": 75,  # Ay 6-7
    "TIMER_STAGE_4": 90,  # Ay 8-12

    # Paket yokken sayfa yenileme aralığı (sn)
    "REFRESH_SEC": 1.0,
}

ASSETS = {
    "cash": "Nakit",
    "dd": "Vadesiz Mevduat",
    "td": "Vadeli Mevduat",
    "fx": "Döviz",
    "pm": "Kıymetli Metal",
    "eq": "Hisse Senedi",
    "cr": "Kripto",
}

# =========================
# AŞAMALI ÜRÜN AÇILIMI
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

# =========================
# TIMER (Deadline mantığı)
# =========================
def stage_time_limit_seconds(month: int) -> int:
    if month <= 3:
        return int(CFG["TIMER_STAGE_1"])
    if month <= 5:
        return int(CFG["TIMER_STAGE_2"])
    if month <= 7:
        return int(CFG["TIMER_STAGE_3"])
    return int(CFG["TIMER_STAGE_4"])

def ensure_timer(p: dict, month: int):
    key = f"deadline_m{month}"
    if key not in p:
        p[key] = time.time() + stage_time_limit_seconds(month)

def time_left_seconds(p: dict, month: int) -> int:
    key = f"deadline_m{month}"
    deadline = float(p.get(key, time.time()))
    return max(int(deadline - time.time()), 0)

def format_mmss(seconds: int) -> str:
    m = seconds // 60
    s = seconds % 60
    return f"{m:02d}:{s:02d}"

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
            "income": None,
            "fixed": None,
            "debt": 0.0,
            "holdings": {k: 0.0 for k in ASSETS},
            "log": []
        }
    p = st.session_state.players[name]
    p.setdefault("month", 1)
    p.setdefault("finished", False)
    p.setdefault("defaulted", False)
    p.setdefault("income", None)
    p.setdefault("fixed", None)
    p.setdefault("debt", 0.0)
    p.setdefault("holdings", {k: 0.0 for k in ASSETS})
    p.setdefault("log", [])
    for k in ASSETS:
        p["holdings"].setdefault(k, 0.0)
    return p

def total_investments(p: dict) -> float:
    return float(sum(v for k, v in p["holdings"].items() if k != "cash"))

def net_wealth(p: dict) -> float:
    return float(p["holdings"]["cash"] + total_investments(p) - float(p.get("debt", 0.0)))

def rng_for(name: str, month: int):
    return np.random.default_rng((hash(name) % 10000) + month * 1000 + st.session_state.seed)

# =========================
# UI
# =========================
st.title("🎮 Finansal Piyasalar Neden Var? (1. Hafta Oyunu)")
st.caption(
    "Kurallar: (i) Ay 1–3 borç yok: gider+harcama nakit+geliri aşarsa temerrüt ve oyun biter. "
    "(ii) Ay 4+ borç var: açık otomatik krediyle kapanır. "
    "(iii) Ay sonunda (Ay 4+) borç geri ödeme seçeneği vardır. "
    "(iv) Her ay süre var; süre dolunca girişler kilitlenir ve yatırım=0, borç ödeme=0 kabul edilir. "
    "(v) Oyun 12. ay sonunda biter."
)

c1, c2 = st.columns([1, 3])
with c1:
    if st.button("🧹 Oyunu Sıfırla"):
        st.session_state.clear()
        st.rerun()
with c2:
    st.caption("Parametreler sabit: sınıfta karşılaştırma yapmak kolay olsun diye.")

name = st.text_input("Oyuncu Adı")
if not name:
    st.stop()

p = get_player(name)

# =========================
# BAŞLANGIÇ
# =========================
if p["income"] is None:
    st.subheader("Başlangıç Bilgileri")
    income_in = st.number_input("Aylık Gelir", 20000, 500000, 60000, 5000)
    fixed_in = st.number_input("Sabit Gider", 10000, 400000, 30000, 5000)
    if fixed_in > income_in:
        st.warning("Sabit gider geliri aşıyor. Ay 1–3'te borç yok → temerrüt riski yüksek.")
    if st.button("Başla"):
        p["income"] = float(income_in)
        p["fixed"] = float(fixed_in)
        st.rerun()
    st.stop()

# =========================
# OYUNCU SIRALAMASI
# =========================
st.subheader("🏆 Oyuncu Sıralaması")
rows = []
for pname, pp in st.session_state.players.items():
    cash = float(pp["holdings"].get("cash", 0.0))
    invest = float(sum(v for k, v in pp["holdings"].items() if k != "cash"))
    debt = float(pp.get("debt", 0.0))
    net = float(cash + invest - debt)

    status = "Devam"
    if pp.get("finished", False) and pp.get("defaulted", False):
        status = "Temerrüt"
    elif pp.get("finished", False):
        status = "Bitti"

    month_done = CFG["MONTHS"] if pp.get("finished", False) else max(int(pp.get("month", 1)) - 1, 0)

    rows.append({
        "Sıra": 0,
        "Oyuncu": pname,
        "Durum": status,
        "Ay": month_done,
        "Servet(Net)": round(net, 0),
        "Borç": round(debt, 0),
    })

lb = pd.DataFrame(rows).sort_values(["Servet(Net)", "Borç"], ascending=[False, True]).reset_index(drop=True)
lb["Sıra"] = lb.index + 1
st.dataframe(lb, use_container_width=True, hide_index=True)

st.divider()

# =========================
# OYUN BİTTİ DURUMU
# =========================
if p.get("finished", False):
    st.success("✅ Oyun bitti (12. ay tamamlandı)." if not p.get("defaulted", False) else "⛔ Oyun bitti: temerrüt.")
    a, b, c, d = st.columns(4)
    a.metric("Nakit", f"{p['holdings']['cash']:,.0f} TL".replace(",", "."))
    b.metric("Yatırım", f"{total_investments(p):,.0f} TL".replace(",", "."))
    c.metric("Borç", f"{p['debt']:,.0f} TL".replace(",", "."))
    d.metric("Servet (Net)", f"{net_wealth(p):,.0f} TL".replace(",", "."))
    st.stop()

# =========================
# AY PANELİ
# =========================
month = int(p["month"])
opened = open_assets_by_month(month)
investable = [k for k in opened if k != "cash"]

# Timer kur
ensure_timer(p, month)
left = time_left_seconds(p, month)
time_up = (left == 0)

st.subheader(f"📅 Ay {month} / {CFG['MONTHS']}")
st.progress((month - 1) / CFG["MONTHS"])
st.info(f"⏳ Kalan karar süresi: **{format_mmss(left)}** (Aşama: {stage_label(month)})")

# ==== PAKETSİZ AUTO-REFRESH: sayaç aksın ====
# Bu blok EN SONDA tekrar rerun yapacağı için, buton işlemleri öncelik kazanır.
# Sadece süre devam ederken yeniler.
if (not time_up) and (not p.get("finished", False)):
    time.sleep(float(CFG["REFRESH_SEC"]))
    st.rerun()

m1, m2, m3, m4 = st.columns(4)
m1.metric("Nakit", f"{p['holdings']['cash']:,.0f} TL".replace(",", "."))
m2.metric("Yatırım", f"{total_investments(p):,.0f} TL".replace(",", "."))
m3.metric("Borç", f"{p['debt']:,.0f} TL".replace(",", "."))
m4.metric("Servet (Net)", f"{net_wealth(p):,.0f} TL".replace(",", "."))

# =========================
# 1) BÜTÇE
# =========================
st.divider()
st.subheader("1) Bütçe (Bu Ay)")

income = float(p["income"])
fixed = float(p["fixed"])

available_without_borrow = p["holdings"]["cash"] + income
extra_max = int(max(0.0, available_without_borrow - fixed)) if not can_borrow(month) else int(income * 3)

extra_default = min(5000, max(0, extra_max))
extra = st.number_input(
    "Ek Harcama",
    0,
    max(0, extra_max),
    extra_default,
    1000,
    disabled=time_up
)

total_exp = fixed + float(extra)
saving = max(income - total_exp, 0.0)

st.write(f"Gelir: **{income:,.0f} TL**".replace(",", "."))
st.write(f"Toplam gider: **{total_exp:,.0f} TL**".replace(",", "."))
st.write(f"Tasarruf: **{saving:,.0f} TL**".replace(",", "."))

if (not can_borrow(month)) and (total_exp > available_without_borrow):
    st.error("Ay 1–3'te borç yok. Bu bütçe nakit+geliri aşıyor → temerrüt. Ek harcamayı düşürün.")

# =========================
# 2) YATIRIM
# =========================
st.divider()
st.subheader("2) Yatırım (Tasarrufu Dağıt)")

alloc = {}
alloc_sum = 0.0

if saving <= 0:
    st.caption("Tasarruf yok → yatırım yok.")
elif not investable:
    st.caption("Bu ay yatırım ürünü yok → tasarruf nakitte kalır.")
else:
    for k in investable:
        c1, c2, c3 = st.columns([2.8, 1.2, 0.6])
        with c1:
            st.write(ASSETS[k])
        with c2:
            alloc[k] = st.number_input(
                f"{k}_pct",
                min_value=0,
                max_value=100,
                value=0,
                step=5,
                label_visibility="collapsed",
                disabled=time_up
            )
        with c3:
            st.write("%")
    alloc_sum = float(sum(alloc.values()))
    st.write(f"Toplam: **{int(alloc_sum)}%** (100'ü aşarsa normalize edilir)")

# =========================
# 3) BORÇ GERİ ÖDEME
# =========================
st.divider()
st.subheader("3) Borç Geri Ödeme (Ay Sonu)")

repay_pct = 0
if not can_borrow(month):
    st.caption("Ay 1–3: borç yok → geri ödeme yok.")
else:
    if float(p["debt"]) <= 0:
        st.caption("Borcunuz yok.")
    else:
        repay_pct = st.slider(
            "Borcun ne kadarını ödemek istersiniz? (%)",
            0, 100, 20, 5,
            disabled=time_up
        )

if time_up:
    alloc = {}
    alloc_sum = 0.0
    repay_pct = 0
    st.warning("⏱️ Süre doldu: yatırım=0 ve borç ödeme=0 uygulanacak.")

# =========================
# AYI TAMAMLA
# =========================
btn_label = "✅ Ayı Tamamla" if month < CFG["MONTHS"] else "✅ 12. Ayı Tamamla ve Bitir"

if st.button(btn_label):
    rng = rng_for(name, month)

    invested_amount = 0.0
    repay_amt = 0.0
    inflation_loss = 0.0

    # Gelir
    p["holdings"]["cash"] += income

    # Gider
    p["holdings"]["cash"] -= total_exp

    if p["holdings"]["cash"] < 0:
        deficit = -float(p["holdings"]["cash"])
        if not can_borrow(month):
            p["holdings"]["cash"] = 0.0
            p["defaulted"] = True
            p["finished"] = True
            st.rerun()
        else:
            p["debt"] += deficit
            p["holdings"]["cash"] = 0.0

    # Yatırım transferi
    if saving > 0 and investable and alloc_sum > 0:
        invested_amount = saving if alloc_sum >= 100 else saving * (alloc_sum / 100.0)

        alloc_adj = dict(alloc)
        if alloc_sum > 100:
            alloc_adj = {k: (v / alloc_sum) * 100 for k, v in alloc.items()}

        for k, pct in alloc_adj.items():
            invest_amt = saving * (float(pct) / 100.0)
            if invest_amt <= 0:
                continue
            p["holdings"][k] += invest_amt
            p["holdings"]["cash"] -= invest_amt

        if p["holdings"]["cash"] < 0:
            deficit2 = -float(p["holdings"]["cash"])
            if can_borrow(month):
                p["debt"] += deficit2
                p["holdings"]["cash"] = 0.0
            else:
                p["holdings"]["cash"] = 0.0
                p["defaulted"] = True
                p["finished"] = True
                st.rerun()

    # Kurum yokken nakit kayıp riski
    if month <= 3 and p["holdings"]["cash"] > 0:
        if rng.random() < CFG["CASH_LOSS_PROB"]:
            p["holdings"]["cash"] -= p["holdings"]["cash"] * CFG["CASH_LOSS_SEV"]

    # Getiriler
    if "dd" in opened:
        p["holdings"]["dd"] *= (1.0 + CFG["DD_RATE"])
    if "td" in opened:
        p["holdings"]["td"] *= (1.0 + CFG["TD_RATE"])

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

    # Borç faizi
    if can_borrow(month) and float(p["debt"]) > 0:
        p["debt"] *= (1.0 + float(CFG["LOAN_RATE"]))

    # Enflasyon kaybı
    infl_rate = float(CFG["INFLATION_M"])
    inflation_loss = float(p["holdings"]["cash"]) * infl_rate
    p["holdings"]["cash"] *= (1.0 - infl_rate)

    # Borç ödeme
    if can_borrow(month) and float(p["debt"]) > 0 and repay_pct > 0:
        target = float(p["debt"]) * (float(repay_pct) / 100.0)
        repay_amt = min(float(p["holdings"]["cash"]), target)
        p["holdings"]["cash"] -= repay_amt
        p["debt"] -= repay_amt
        p["debt"] = max(p["debt"], 0.0)

    # Ay sonu
    if month >= CFG["MONTHS"]:
        p["finished"] = True
    else:
        p["month"] += 1

    # yeni ay için timer anahtarı zaten farklı (deadline_m{month}) olduğu için otomatik yeni deadline oluşacak
    st.rerun()
