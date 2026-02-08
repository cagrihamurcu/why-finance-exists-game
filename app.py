import streamlit as st
import numpy as np
import pandas as pd
import time

st.set_page_config(page_title="Finans Neden Var?", layout="wide")

# =========================
# SABİT BAŞLANGIÇ
# =========================
DEFAULT_MONTHLY_INCOME = 60000
START_FIXED_COST = 30000

CFG = {
    "MONTHS": 12,

    # Enflasyon
    "INFL_START": 0.20,
    "INFL_STEP": 0.05,

    # Hırsızlık
    "CASH_THEFT_PROB_STAGE1": 0.12,
    "CASH_THEFT_PROB_STAGE2": 0.05,
    "CASH_THEFT_SEV_MIN": 0.10,
    "CASH_THEFT_SEV_MAX": 0.35,

    # Banka
    "BANK_INCIDENT_PROB": 0.02,
    "TD_RATE_MIN": 0.007,
    "TD_RATE_MAX": 0.014,
    "GUAR_MIN": 0.70,
    "GUAR_MAX": 0.99,

    # Vadeli bozma cezası
    "EARLY_BREAK_PENALTY": 0.01,

    # İşlem ücreti
    "TX_FEE": 0.005,

    # Spread
    "SPREAD": {
        "fx": 0.01,
        "pm": 0.012,
        "eq": 0.02,
        "cr": 0.05,
    },

    # Getiriler
    "EQ_MU": 0.015, "EQ_SIG": 0.06,
    "CR_MU": 0.02, "CR_SIG": 0.12,
    "PM_MU": 0.008, "PM_SIG": 0.03,
    "FX_MU": 0.01, "FX_SIG": 0.04,

    "CRISIS_MONTH": 6,
    "CRISIS_EQ": -0.12,
    "CRISIS_CR": -0.20,
    "CRISIS_PM": 0.04,
    "CRISIS_FX": 0.07,

    "LOAN_RATE": 0.025,
}

ASSETS = ["cash","fx","pm","eq","cr"]

# =========================
# YARDIMCI
# =========================
def fmt(x): return f"{x:,.0f} TL".replace(",", ".")

def infl(month):
    return CFG["INFL_START"] + CFG["INFL_STEP"]*(month-1)

def rng(name,month):
    return np.random.default_rng(hash(name)%10000 + month*100)

def buy_cost(asset):
    return CFG["TX_FEE"] + CFG["SPREAD"].get(asset,0)/2

def sell_cost(asset):
    return CFG["TX_FEE"] + CFG["SPREAD"].get(asset,0)/2

# =========================
# SESSION
# =========================
if "players" not in st.session_state:
    st.session_state.players = {}

if "seed" not in st.session_state:
    st.session_state.seed = 42

# =========================
# OYUNCU
# =========================
name = st.text_input("Oyuncu Adı")
if not name:
    st.stop()

if name not in st.session_state.players:
    st.session_state.players[name] = {
        "month":1,
        "cash":0.0,
        "holdings":{"fx":0,"pm":0,"eq":0,"cr":0},
        "dd":{},
        "td":{},
        "debt":0.0,
        "fixed":START_FIXED_COST,
        "log":[],
        "finished":False
    }

p = st.session_state.players[name]

# =========================
# OYUN BİTTİ
# =========================
if p["finished"]:
    st.success("Oyun tamamlandı.")
    df = pd.DataFrame(p["log"])
    st.dataframe(df,use_container_width=True)
    st.stop()

# =========================
# AY PANELİ
# =========================
m = p["month"]
income = DEFAULT_MONTHLY_INCOME
fixed = p["fixed"]

st.title(f"Ay {m}/12")

col1,col2,col3 = st.columns(3)
col1.metric("Gelir",fmt(income))
col2.metric("Sabit Gider",fmt(fixed))
col3.metric("Enflasyon",f"{infl(m)*100:.0f}%")

# =========================
# SATIŞ
# =========================
st.subheader("Bozdurma / Satış")

sell = {}
for a in p["holdings"]:
    if p["holdings"][a] > 0:
        sell[a] = st.number_input(f"{a.upper()} Satış (TL)",0.0,p["holdings"][a],0.0,1000.0)

# =========================
# BÜTÇE
# =========================
extra = st.number_input("Ek Harcama",0,50000,5000,1000)
total_exp = fixed + extra

# =========================
# YATIRIM
# =========================
st.subheader("Yatırım")

buy = {}
for a in p["holdings"]:
    buy[a] = st.number_input(f"{a.upper()} Alış (TL)",0.0,1000000.0,0.0,1000.0)

# =========================
# AYI TAMAMLA
# =========================
if st.button("Ayı Tamamla"):

    r = rng(name,m)

    # SATIŞ
    for a,amt in sell.items():
        cost = sell_cost(a)
        net = amt*(1-cost)
        p["holdings"][a] -= amt
        p["cash"] += net

    # GELİR
    p["cash"] += income

    # GİDER
    p["cash"] -= total_exp

    # ALIŞ
    for a,amt in buy.items():
        if amt>0:
            cost = buy_cost(a)
            net = amt*(1-cost)
            p["cash"] -= amt
            p["holdings"][a] += net

    # HIRSIZLIK
    prob = CFG["CASH_THEFT_PROB_STAGE1"] if m<=3 else CFG["CASH_THEFT_PROB_STAGE2"]
    theft_loss = 0
    if p["cash"]>0 and r.random()<prob:
        sev = r.uniform(CFG["CASH_THEFT_SEV_MIN"],CFG["CASH_THEFT_SEV_MAX"])
        theft_loss = p["cash"]*sev
        p["cash"] -= theft_loss

        st.error("🚨🚨🚨 NAKİT HIRSIZLIĞI! 🚨🚨🚨")
        st.markdown(f"""
        <div style="padding:20px;border:3px solid red;background:#ffe6e6;font-size:20px;">
        <b>Kayıp:</b> {fmt(theft_loss)}<br>
        <b>Kalan Nakit:</b> {fmt(p["cash"])}
        </div>
        """,unsafe_allow_html=True)
        st.toast(f"Hırsızlık! {fmt(theft_loss)} kayıp!",icon="🚨")
        time.sleep(1)

    # GETİRİLER
    for a in p["holdings"]:
        mu = CFG.get(a.upper()+"_MU",0)
        sig = CFG.get(a.upper()+"_SIG",0)
        ret = r.normal(mu,sig)
        if m==CFG["CRISIS_MONTH"]:
            ret += CFG.get("CRISIS_"+a.upper(),0)
        p["holdings"][a] *= (1+ret)

    # ENFLASYON SABİT GİDER
    if m<12:
        p["fixed"] = fixed*(1+infl(m+1))

    # LOG
    total_inv = sum(p["holdings"].values())
    total = p["cash"]+total_inv-p["debt"]

    p["log"].append({
        "Ay":m,
        "Nakit":p["cash"],
        "Yatırım":total_inv,
        "ToplamServet":total,
        "HırsızlıkKayıp":theft_loss
    })

    if m==12:
        p["finished"]=True
    else:
        p["month"]+=1

    st.rerun()

# =========================
# GEÇMİŞ
# =========================
if p["log"]:
    st.subheader("Geçmiş")
    df = pd.DataFrame(p["log"])
    st.dataframe(df,use_container_width=True,height=300)
