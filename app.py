import streamlit as st
import streamlit.components.v1 as components
import numpy as np
import pandas as pd

st.set_page_config(layout="wide")

# ======================
# SABİT PARAMETRELER
# ======================
MONTHS = 12
DEFAULT_INCOME = 60000
START_FIXED_COST = 30000

TX_FEE = 0.005
EARLY_BREAK = 0.01

# ======================
# SESSION
# ======================
if "players" not in st.session_state:
    st.session_state.players = {}

if "seed" not in st.session_state:
    st.session_state.seed = 42

if "theft_banner" not in st.session_state:
    st.session_state.theft_banner = None

# ======================
# FORMAT
# ======================
def tl(x):
    return f"{x:,.0f} TL".replace(",", ".")

# ======================
# OYUNCU OLUŞTUR
# ======================
def get_player(name):
    if name not in st.session_state.players:
        rng = np.random.default_rng(hash(name) % 10000 + st.session_state.seed)
        theft_months = sorted(
            rng.choice(np.arange(1, MONTHS+1), size=3, replace=False)
        )

        st.session_state.players[name] = {
            "month": 1,
            "cash": 0.0,
            "dd": {},
            "td": {},
            "debt": 0.0,
            "debt_rate": 0.03,
            "income": DEFAULT_INCOME,
            "fixed": START_FIXED_COST,
            "infl": 0.20,
            "theft_months": theft_months,
            "log": []
        }
    return st.session_state.players[name]

# ======================
# HIRSIZLIK MESAJI
# ======================
if st.session_state.theft_banner:
    loss = st.session_state.theft_banner["loss"]
    remain = st.session_state.theft_banner["remain"]

    components.html(
        f"""
        <div id="alertbox" style="
        padding:20px;
        background:#ff0000;
        color:white;
        font-size:24px;
        font-weight:bold;
        border-radius:15px;">
        🚨 NAKİT HIRSIZLIĞI! 🚨<br>
        Kayıp: {tl(loss)}<br>
        Kalan Nakit: {tl(remain)}
        </div>

        <script>
        setTimeout(function(){{
            document.getElementById("alertbox").style.display="none";
        }},10000);
        </script>
        """,
        height=140
    )

    st.session_state.theft_banner = None

# ======================
# ARAYÜZ
# ======================
st.title("🎮 Finansal Sistem Oyunu")

name = st.text_input("Oyuncu Adı")
if not name:
    st.stop()

p = get_player(name)
month = p["month"]

st.subheader(f"Ay {month} / {MONTHS}")

col1,col2,col3 = st.columns(3)
col1.metric("Nakit", tl(p["cash"]))
col2.metric("Borç", tl(p["debt"]))
col3.metric("Sabit Gider", tl(p["fixed"]))

# ======================
# BÜTÇE
# ======================
extra = st.number_input("Ek Harcama", 0, 50000, 5000, 1000)
total_exp = p["fixed"] + extra

st.write("Toplam Gider:", tl(total_exp))

# ======================
# BORÇ ALMA (Ay4+)
# ======================
borrow = 0
if month >= 4:
    borrow = st.number_input("Bankadan Borç Al", 0, 200000, 0, 1000)

# ======================
# AYI TAMAMLA
# ======================
if st.button("Ayı Tamamla"):

    # GELİR
    p["cash"] += p["income"]

    # BORÇ EKLE
    if borrow > 0:
        p["cash"] += borrow
        p["debt"] += borrow

    # GİDER
    p["cash"] -= total_exp

    # BORÇ FAİZİ
    if p["debt"] > 0:
        p["debt"] *= (1 + p["debt_rate"])

    # HIRSIZLIK (en az 3 kez garantili)
    theft_loss = 0
    if month in p["theft_months"] and p["cash"] > 0:
        sev = np.random.uniform(0.15,0.35)
        theft_loss = p["cash"] * sev
        p["cash"] -= theft_loss

        st.session_state.theft_banner = {
            "loss": theft_loss,
            "remain": p["cash"]
        }

    # ENFLASYON GÜNCELLE
    step = np.random.uniform(0.01,0.05)
    if np.random.rand()<0.5:
        p["infl"] += step
    else:
        p["infl"] -= step

    p["infl"] = max(0, min(0.8, p["infl"]))
    p["fixed"] *= (1 + p["infl"])

    # LOG
    p["log"].append({
        "Ay": month,
        "Gelir": p["income"],
        "ToplamGider": total_exp,
        "Hırsızlık": theft_loss,
        "DönemSonuNakit": p["cash"],
        "Borç": p["debt"]
    })

    # AY İLERLET
    if month >= MONTHS:
        st.success("Oyun Bitti")
    else:
        p["month"] += 1

    st.rerun()

# ======================
# GEÇMİŞ
# ======================
if p["log"]:
    st.divider()
    st.subheader("Geçmiş")
    st.dataframe(pd.DataFrame(p["log"]), use_container_width=True)
