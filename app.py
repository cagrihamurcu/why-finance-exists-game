import streamlit as st
import numpy as np
import pandas as pd

st.set_page_config(page_title="Finansal Kurumun Rolü — 1. Hafta", layout="wide")

# -----------------------------
# Default Parameters
# -----------------------------
DEFAULT = {
    "START_CAP": 1_000_000.0,
    "N_TURNS": 6,

    # Direct investment
    "P_SUCCESS": 0.65,
    "R_SUCCESS": 0.35,
    "R_FAILURE": -0.60,

    # Deposit
    "R_DEPOSIT": 0.12,

    # Intermediated (bank) investment
    "BANK_EXPECTED": 0.18,   # average stabilized return
    "BANK_VOL": 0.05,        # lower volatility
    "BANK_FEE": 0.03,        # spread / fee

    # Liquidity shock
    "P_LIQUIDITY": 0.15,
    "LIQUIDITY_COST": 0.20,  # forced liquidation loss %

    # Scoring
    "LOSS_PENALTY": 120_000.0
}

if "players" not in st.session_state:
    st.session_state.players = {}

if "turn" not in st.session_state:
    st.session_state.turn = 1

if "seed" not in st.session_state:
    st.session_state.seed = 20260209

def get_player(name):
    if name not in st.session_state.players:
        st.session_state.players[name] = {
            "wealth": DEFAULT["START_CAP"],
            "returns": [],
            "log": []
        }
    return st.session_state.players[name]

def score(player):
    loss_turns = sum(1 for r in player["returns"] if r < 0)
    return player["wealth"] - DEFAULT["LOSS_PENALTY"] * loss_turns

def var5(player):
    if not player["returns"]:
        return 0
    return float(np.percentile(player["returns"], 5))

# -----------------------------
# UI
# -----------------------------
st.title("🎮 Ekonomide Finansal Kurumun Rolü")
st.write(
    "Her tur yatırım tercihi yapacaksınız.\n\n"
    "Bu oyunda üç temel finansal işlevi deneyimleyeceksiniz:\n"
    "1️⃣ Risk yönetimi\n"
    "2️⃣ Likidite sağlama\n"
    "3️⃣ Finansal aracılık (maliyet karşılığında istikrar)\n"
)

name = st.text_input("Oyuncu Adı")
if not name:
    st.stop()

player = get_player(name)

st.subheader(f"Tur: {st.session_state.turn}/{DEFAULT['N_TURNS']}")
st.metric("Mevcut Servet", f"{player['wealth']:,.0f} TL".replace(",", "."))

choice = st.radio(
    "Yatırım tercihiniz:",
    ["Direct Investment", "Deposit", "Intermediated Investment (Banka)"],
    horizontal=True
)

if st.button("Kararı Onayla"):
    rng = np.random.default_rng(st.session_state.seed + st.session_state.turn * 1000 + hash(name)%1000)
