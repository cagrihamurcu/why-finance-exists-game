import streamlit as st
import numpy as np
import pandas as pd

st.set_page_config(page_title="Finans Neden Var?", layout="wide")

# =========================
# AYARLAR
# =========================
CFG = {
    "MONTHS": 12,
    "NO_INSTITUTIONS_UNTIL": 3,

    "INFLATION_M": 0.02,

    "CASH_LOSS_PROB": 0.05,
    "CASH_LOSS_SEV": 0.10,

    "DD_RATE": 0.003,
    "TD_RATE": 0.01,

    "EQ_MU": 0.015,
    "EQ_SIG": 0.06,

    "CR_MU": 0.02,
    "CR_SIG": 0.12,

    "PM_MU": 0.008,
    "PM_SIG": 0.03,

    "FX_MU": 0.01,
    "FX_SIG": 0.04,

    "CRISIS_MONTH": 6,
    "CRISIS_EQ": -0.12,
    "CRISIS_CR": -0.20,
    "CRISIS_PM": +0.04,
    "CRISIS_FX": +0.07,
}

ASSETS = {
    "cash": "Nakit",
    "dd": "Vadesiz Mevduat",
    "td": "Vadeli Mevduat",
    "eq": "Hisse Senedi",
    "cr": "Kripto",
    "pm": "Kıymetli Metal",
    "fx": "Döviz",
}

# =========================
# SESSION
# =========================
if "players" not in st.session_state:
    st.session_state.players = {}

def get_player(name):
    if name not in st.session_state.players:
        st.session_state.players[name] = {
            "month": 1,
            "income": None,
            "fixed": None,
            "holdings": {k: 0.0 for k in ASSETS},
            "log": []
        }
    return st.session_state.players[name]

def total_wealth(p):
    return sum(p["holdings"].values())

def rng_for(name, month):
    return np.random.default_rng(hash(name) % 10000 + month*100)

# =========================
# UI
# =========================
st.title("🎮 Finansal Piyasalar Neden Var?")

name = st.text_input("Oyuncu Adı")
if not name:
    st.stop()

p = get_player(name)

# =========================
# BAŞLANGIÇ
# =========================
if p["income"] is None:
    st.subheader("Başlangıç Bilgileri")
    income = st.number_input("Aylık Gelir", 20000, 500000, 60000, 5000)
    fixed = st.number_input("Sabit Gider", 10000, 400000, 30000, 5000)

    if st.button("Başla"):
        p["income"] = income
        p["fixed"] = fixed
        st.rerun()
    st.stop()

# =========================
# AY PANELİ
# =========================
month = p["month"]
st.subheader(f"Ay {month} / {CFG['MONTHS']}")

if month <= CFG["NO_INSTITUTIONS_UNTIL"]:
    st.info("Finansal kurum yok. Tasarruf sadece nakit olarak tutulabilir.")
elif month == CFG["NO_INSTITUTIONS_UNTIL"] + 1:
    st.success("Finansal kurumlar devrede! Yatırım seçenekleri açıldı.")
elif month == CFG["CRISIS_MONTH"]:
    st.warning("Makro kriz!")

st.metric("Toplam Servet", f"{total_wealth(p):,.0f} TL")

# =========================
# BÜTÇE
# =========================
st.subheader("Bu Ay Bütçe")

income = p["income"]
fixed = p["fixed"]
extra = st.number_input("Ek Harcama", 0, int(income), 5000, 1000)

# Gelir ekle
p["holdings"]["cash"] += income

# Gider düş
total_exp = fixed + extra
p["holdings"]["cash"] -= total_exp

if p["holdings"]["cash"] < 0:
    st.error("Nakit açığı! Finansal kırılganlık.")
    p["holdings"]["cash"] = 0

# Tasarruf otomatik kalan
saving = p["holdings"]["cash"]
st.write(f"Bu ay tasarruf edilen tutar: **{saving:,.0f} TL**")

# =========================
# YATIRIM KARARI
# =========================
st.subheader("Tasarrufu Nereye Yatıracaksınız?")

alloc = {}
alloc_sum = 0

if month <= CFG["NO_INSTITUTIONS_UNTIL"]:
    st.write("Kurum yok → tasarruf nakitte kalır.")
else:
    for k in ["dd","td","eq","cr","pm","fx"]:
        col1, col2 = st.columns([3,1])
        with col1:
            alloc[k] = st.number_input(ASSETS[k], 0, 100, 0, 5)
        with col2:
            st.write("%")

    alloc_sum = sum(alloc.values())
    st.write(f"Toplam: {alloc_sum}%")

# =========================
# AYI ÇALIŞTIR
# =========================
if st.button("Ayı Tamamla"):

    # Tasarrufu dağıt
    if month > CFG["NO_INSTITUTIONS_UNTIL"] and alloc_sum > 0:

        # normalize
        if alloc_sum > 100:
            alloc = {k: v/alloc_sum*100 for k,v in alloc.items()}

        for k,v in alloc.items():
            invest = saving * (v/100)
            p["holdings"][k] += invest
            p["holdings"]["cash"] -= invest

    # GETİRİLER
    rng = rng_for(name, month)

    if month > CFG["NO_INSTITUTIONS_UNTIL"]:

        p["holdings"]["dd"] *= (1 + CFG["DD_RATE"])
        p["holdings"]["td"] *= (1 + CFG["TD_RATE"])

        eq_r = rng.normal(CFG["EQ_MU"], CFG["EQ_SIG"])
        cr_r = rng.normal(CFG["CR_MU"], CFG["CR_SIG"])
        pm_r = rng.normal(CFG["PM_MU"], CFG["PM_SIG"])
        fx_r = rng.normal(CFG["FX_MU"], CFG["FX_SIG"])

        if month == CFG["CRISIS_MONTH"]:
            eq_r += CFG["CRISIS_EQ"]
            cr_r += CFG["CRISIS_CR"]
            pm_r += CFG["CRISIS_PM"]
            fx_r += CFG["CRISIS_FX"]

        p["holdings"]["eq"] *= (1 + eq_r)
        p["holdings"]["cr"] *= (1 + cr_r)
        p["holdings"]["pm"] *= (1 + pm_r)
        p["holdings"]["fx"] *= (1 + fx_r)

    else:
        # kurum yok → nakit kayıp riski
        if rng.random() < CFG["CASH_LOSS_PROB"]:
            loss = p["holdings"]["cash"] * CFG["CASH_LOSS_SEV"]
            p["holdings"]["cash"] -= loss
            st.warning("Nakit kaybı yaşandı!")

    # enflasyon
    p["holdings"]["cash"] *= (1 - CFG["INFLATION_M"])

    # log
    p["log"].append({
        "Ay": month,
        "Servet": total_wealth(p)
    })

    p["month"] += 1
    st.rerun()

# =========================
# GRAFİK
# =========================
if p["log"]:
    df = pd.DataFrame(p["log"])
    st.line_chart(df.set_index("Ay"))

# =========================
# LİDER TABLOSU
# =========================
st.subheader("🏆 Lider Tablosu")
rows = []
for pname, player in st.session_state.players.items():
    rows.append({
        "Oyuncu": pname,
        "Servet": total_wealth(player)
    })

if rows:
    lb = pd.DataFrame(rows).sort_values("Servet", ascending=False)
    st.dataframe(lb, hide_index=True)
