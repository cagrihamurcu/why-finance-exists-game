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

    # Direct investment (tek yatırım)
    "P_SUCCESS": 0.65,
    "R_SUCCESS": 0.35,
    "R_FAILURE": -0.60,

    # Deposit (mevduat)
    "R_DEPOSIT": 0.12,

    # Intermediated (banka üzerinden) yatırım
    "BANK_EXPECTED": 0.18,
    "BANK_VOL": 0.05,
    "BANK_FEE": 0.03,  # spread/komisyon

    # Liquidity shock (likidite ihtiyacı)
    "P_LIQUIDITY": 0.15,
    "LIQUIDITY_COST": 0.20,  # forced liquidation loss (Direct için ek ceza)

    # Macro crisis (Tur 4)
    "CRISIS_TURN": 4,
    "CRISIS_HIT_DIRECT": 0.15,   # Direct getiriden düşer
    "CRISIS_HIT_BANK": 0.08,     # Banka üzerinden yatırım daha az etkilenir
    "CRISIS_VOL_BONUS": 0.06,    # Krizde oynaklık artar (bankanın vol'u artar)
    "CRISIS_LIQ_BONUS": 0.15,    # Krizde likidite şoku ihtimali artar (Direct için)

    # Scoring
    "LOSS_PENALTY": 120_000.0
}

# -----------------------------
# Session state init
# -----------------------------
if "players" not in st.session_state:
    st.session_state.players = {}

if "seed" not in st.session_state:
    st.session_state.seed = 20260209

def get_player(name: str):
    if name not in st.session_state.players:
        st.session_state.players[name] = {
            "turn": 1,
            "wealth": DEFAULT["START_CAP"],
            "returns": [],
            "log": []
        }
    return st.session_state.players[name]

def score(pl):
    loss_turns = sum(1 for r in pl["returns"] if r < 0)
    return pl["wealth"] - DEFAULT["LOSS_PENALTY"] * loss_turns

def var5(pl):
    if not pl["returns"]:
        return 0.0
    return float(np.percentile(np.array(pl["returns"]), 5))

# -----------------------------
# UI
# -----------------------------
st.title("🎮 Ekonomide Finansal Kurumun Rolü — 1. Hafta")
st.write(
    "Bu oyun 1. haftanın sorusuna cevap verir:\n"
    "**Neden finansal piyasalar ve kurumlarla ilgilenmekteyiz?**\n\n"
    "Çünkü finansal sistem:\n"
    "1) **Risk yönetimi** sağlar\n"
    "2) **Likidite** sağlar\n"
    "3) **Aracılık** yapar (maliyet/spread karşılığında istikrar üretir)\n\n"
    f"⚠️ **Tur {DEFAULT['CRISIS_TURN']}**: *Makro Kriz* gerçekleşir."
)

name = st.text_input("Oyuncu Adı (takma isim)", placeholder="örn. T3_Ayşe / Mehmet / Takım-4")
if not name:
    st.stop()

player = get_player(name)
turn = player["turn"]

# Game end
if turn > DEFAULT["N_TURNS"]:
    st.success("Oyun bitti. Lider tablosunu inceleyin.")
else:
    st.subheader(f"Tur: {turn}/{DEFAULT['N_TURNS']}")
    st.metric("Mevcut Servet", f"{player['wealth']:,.0f} TL".replace(",", "."))

    if turn == DEFAULT["CRISIS_TURN"]:
        st.warning("⚠️ MAKRO KRİZ TURU: Risk artar, likidite daha kritik hale gelir.")

    choice = st.radio(
        "Yatırım tercihiniz:",
        ["Direct Investment", "Deposit", "Intermediated Investment (Banka)"],
        horizontal=True
    )

    if st.button("✅ Kararı Onayla ve Sonucu Gör"):
        # RNG: deterministic per player+turn for reproducibility
        rng = np.random.default_rng(st.session_state.seed + turn * 1000 + (hash(name) % 1000))

        # Base returns
        if choice == "Direct Investment":
            success = rng.random() < DEFAULT["P_SUCCESS"]
            r = DEFAULT["R_SUCCESS"] if success else DEFAULT["R_FAILURE"]

        elif choice == "Deposit":
            r = DEFAULT["R_DEPOSIT"]

        else:
            # bank return with volatility
            vol = DEFAULT["BANK_VOL"]
            if turn == DEFAULT["CRISIS_TURN"]:
                vol += DEFAULT["CRISIS_VOL_BONUS"]
            r = rng.normal(DEFAULT["BANK_EXPECTED"], vol) - DEFAULT["BANK_FEE"]

        # Liquidity shock (only hurts Direct)
        p_liq = DEFAULT["P_LIQUIDITY"]
        if turn == DEFAULT["CRISIS_TURN"]:
            p_liq += DEFAULT["CRISIS_LIQ_BONUS"]

        liquidity_shock = (rng.random() < p_liq)

        if choice == "Direct Investment" and liquidity_shock:
            r -= DEFAULT["LIQUIDITY_COST"]

        # Macro crisis impact (systematic shock)
        crisis = (turn == DEFAULT["CRISIS_TURN"])
        if crisis:
            if choice == "Direct Investment":
                r -= DEFAULT["CRISIS_HIT_DIRECT"]
            elif choice == "Intermediated Investment (Banka)":
                r -= DEFAULT["CRISIS_HIT_BANK"]
            # Deposit: kriz etkisi yok (flight-to-quality mesajı)

        # Apply
        player["wealth"] *= (1 + r)
        player["returns"].append(float(r))

        player["log"].append({
            "Turn": turn,
            "Choice": choice,
            "Return": r,
            "MacroCrisis": crisis,
            "LiquidityShock": (liquidity_shock and choice == "Direct Investment"),
            "Wealth": player["wealth"]
        })

        st.success(f"Sonuç: Getiri = %{r*100:.2f} | Yeni Servet = {player['wealth']:,.0f} TL".replace(",", "."))

        # Next turn
        player["turn"] += 1
        st.rerun()

# -----------------------------
# Player log
# -----------------------------
if player["log"]:
    st.write("### Tur Geçmişi")
    df = pd.DataFrame(player["log"])
    df["Return %"] = df["Return"] * 100
    st.dataframe(df[["Turn","Choice","Return %","MacroCrisis","LiquidityShock","Wealth"]], use_container_width=True)

# -----------------------------
# Leaderboard
# -----------------------------
st.subheader("🏆 Lider Tablosu")
rows = []
for pname, pl in st.session_state.players.items():
    rows.append({
        "Oyuncu": pname,
        "Tur": min(pl["turn"] - 1, DEFAULT["N_TURNS"]),
        "Servet (TL)": pl["wealth"],
        "Zarar Tur": sum(1 for r in pl["returns"] if r < 0),
        "VaR %5 (Getiri)": var5(pl),
        "Skor": score(pl)
    })

if rows:
    lb = pd.DataFrame(rows).sort_values("Skor", ascending=False)
    lb["Servet (TL)"] = lb["Servet (TL)"].round(0)
    lb["VaR %5 (Getiri)"] = (lb["VaR %5 (Getiri)"]*100).round(2).astype(str) + "%"
    lb["Skor"] = lb["Skor"].round(0)
    st.dataframe(lb, use_container_width=True, hide_index=True)
else:
    st.caption("Henüz oyuncu yok.")
