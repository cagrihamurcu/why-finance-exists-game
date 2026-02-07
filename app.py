import streamlit as st
import numpy as np
import pandas as pd
from dataclasses import dataclass

st.set_page_config(page_title="Why Finance Exists? - Week 1 Game", layout="wide")

# -----------------------------
# Game parameters (Week 1)
# -----------------------------
@dataclass
class Params:
    start_cap: float = 1_000_000.0

    # Direct deal
    p_success: float = 0.70
    r_success_mu: float = 0.35
    r_success_sigma: float = 0.10

    # "Failure" in direct deal uses recovery
    recovery: float = 0.40
    r_fail_sigma: float = 0.05  # around -(1-recovery)

    # Deposit
    r_deposit: float = 0.12

    # Bank pooling
    r_loan: float = 0.20
    p_default: float = 0.20
    n_loans: int = 50

    # Game
    n_turns: int = 5

P = Params()

# -----------------------------
# Utilities
# -----------------------------
def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def draw_direct_deal_return(rng: np.random.Generator, p_success, r_success_mu, r_success_sigma, recovery, r_fail_sigma):
    success = rng.random() < p_success
    if success:
        r = rng.normal(r_success_mu, r_success_sigma)
    else:
        r = rng.normal(-(1.0 - recovery), r_fail_sigma)
    return r

def draw_deposit_return(_rng, r_deposit):
    return r_deposit

def draw_bank_pooling_return(rng: np.random.Generator, r_loan, p_default, recovery, n_loans):
    # Default count ~ Binomial(n_loans, p_default)
    d = rng.binomial(n_loans, p_default)
    # fraction defaulted
    frac = d / max(1, n_loans)
    # performing loans earn r_loan; defaulted loans lose (1-recovery)
    r = (1 - frac) * r_loan + frac * (-(1.0 - recovery))
    # add small noise so VaR is meaningful
    r += rng.normal(0.0, 0.01)
    return r

def var5(returns):
    if len(returns) == 0:
        return 0.0
    return float(np.percentile(np.array(returns), 5))

# -----------------------------
# Persistent storage in session
# -----------------------------
if "rng_seed" not in st.session_state:
    st.session_state.rng_seed = 20260207  # fixed seed -> same macro world for everyone (fairness)

if "players" not in st.session_state:
    st.session_state.players = {}  # name -> state dict

def get_player(name: str):
    if name not in st.session_state.players:
        st.session_state.players[name] = {
            "turn": 1,
            "wealth": P.start_cap,
            "returns": [],
            "loss_turns": 0,
            "log": []
        }
    return st.session_state.players[name]

# -----------------------------
# Sidebar: Instructor controls (optional)
# -----------------------------
with st.sidebar:
    st.header("🎛️ Eğitmen Paneli (opsiyonel)")
    st.caption("Sınıfta adil olması için aynı makro dünyayı kullanıyoruz.")
    seed = st.number_input("Makro dünya seed", value=int(st.session_state.rng_seed), step=1)
    if st.button("Seed uygula"):
        st.session_state.rng_seed = int(seed)
        st.success("Seed güncellendi. Yeni dünyada sonuçlar değişir.")
    st.divider()

    st.subheader("Makro Şok Ayarları")
    st.caption("Tur 4'te pDefault otomatik artar. İsterseniz burada ayarlayın.")
    shock_pdefault = st.slider("Tur 4 pDefault", 0.05, 0.80, 0.35, 0.01)
    st.session_state.shock_pdefault = shock_pdefault

    st.divider()
    if st.button("🧹 Tüm oyunu sıfırla (dikkat)"):
        st.session_state.players = {}
        st.success("Sıfırlandı.")

# -----------------------------
# Main UI
# -----------------------------
st.title("🎮 Why Finance Exists? — 1. Hafta Oyunu")
st.write("5 tur boyunca seçim yapın. Amaç: **finansın neden var olduğunu yaşamak**.")

colA, colB = st.columns([2, 1])

with colA:
    name = st.text_input("Oyuncu Adı (takma isim):", placeholder="örn. Takım-3 / Ayşe / Mehmet")
    if not name:
        st.info("Başlamak için bir oyuncu adı girin.")
        st.stop()

    player = get_player(name)
    turn = player["turn"]

    # Macro regime by turn
    p_default_turn = P.p_default
    note = ""
    if turn == 4:
        p_default_turn = float(st.session_state.get("shock_pdefault", 0.35))
        note = f"⚠️ Makro Şok: pDefault = {p_default_turn:.2f}"
    elif turn in [1, 2]:
        note = "🌍 'Finans yok' dünyası: çoğu kişi tek yatırıma koşar."
    elif turn == 3:
        note = "🏦 Bank_Pooling açıldı: risk havuzu artık mümkün."

    st.subheader(f"Tur: {turn} / {P.n_turns}")
    if note:
        st.warning(note)

    st.metric("Mevcut Servet (TL)", f"{player['wealth']:,.0f}".replace(",", "."))

    st.write("### Seçimini yap")
    choices = ["Direct_Deal", "Deposit", "Bank_Pooling"]
    # optional: force direct deal first 2 turns
    forced = (turn in [1, 2])
    if forced:
        st.info("Bu turda sadece **Direct_Deal** seçilebilir (Finans yok).")
        choice = "Direct_Deal"
        st.write("Seçim: **Direct_Deal**")
    else:
        choice = st.radio("Seçenek", choices, horizontal=True)

    if st.button("✅ Kararı Onayla ve Sonucu Gör"):
        rng = np.random.default_rng(st.session_state.rng_seed + hash((name, turn)) % 10_000_000)

        if choice == "Direct_Deal":
            r = draw_direct_deal_return(
                rng,
                P.p_success,
                P.r_success_mu,
                P.r_success_sigma,
                P.recovery,
                P.r_fail_sigma
            )
        elif choice == "Deposit":
            r = draw_deposit_return(rng, P.r_deposit)
        else:
            r = draw_bank_pooling_return(
                rng,
                P.r_loan,
                p_default_turn,
                P.recovery,
                P.n_loans
            )

        # Update wealth
        new_wealth = player["wealth"] * (1.0 + r)

        player["returns"].append(float(r))
        if r < 0:
            player["loss_turns"] += 1

        player["wealth"] = new_wealth
        player["log"].append({
            "Turn": turn,
            "Choice": choice,
            "Return": r,
            "Wealth": new_wealth,
            "pDefault": p_default_turn
        })

        player["turn"] += 1

        st.success(f"Sonuç: Getiri = {r*100:.2f}% | Yeni Servet = {new_wealth:,.0f} TL".replace(",", "."))

        if player["turn"] > P.n_turns:
            st.balloons()

    # Player log
    if player["log"]:
        st.write("### Tur Geçmişi")
        df_log = pd.DataFrame(player["log"])
        df_log["Return %"] = df_log["Return"] * 100
        df_log["Wealth (TL)"] = df_log["Wealth"]
        df_log = df_log[["Turn", "Choice", "Return %", "Wealth (TL)", "pDefault"]]
        st.dataframe(df_log, use_container_width=True)

with colB:
    st.subheader("📈 Kişisel Risk Özeti")
    rets = player["returns"]
    loss_turns = player["loss_turns"]
    v5 = var5(rets)
    st.metric("Zarar Yaşanan Tur", str(loss_turns))
    st.metric("VaR %5 (Getiri)", f"{v5*100:.2f}%")
    if len(rets) > 1:
        st.metric("Ortalama Getiri", f"{np.mean(rets)*100:.2f}%")
        st.metric("Std. Sapma", f"{np.std(rets, ddof=1)*100:.2f}%")
    else:
        st.caption("En az 2 tur oynayınca ortalama/std görünür.")

    # Score
    score = player["wealth"] - 150_000 * loss_turns
    st.metric("Skor", f"{score:,.0f}".replace(",", "."))

    st.divider()
    st.subheader("🏆 Lider Tablosu")
    rows = []
    for n, pl in st.session_state.players.items():
        sc = pl["wealth"] - 150_000 * pl["loss_turns"]
        rows.append({
            "Oyuncu": n,
            "Tur": min(pl["turn"]-1, P.n_turns),
            "Final Servet (TL)": pl["wealth"],
            "Zarar Tur": pl["loss_turns"],
            "VaR %5": var5(pl["returns"]),
            "Skor": sc
        })
    if rows:
        lb = pd.DataFrame(rows).sort_values("Skor", ascending=False)
        lb["Final Servet (TL)"] = lb["Final Servet (TL)"].round(0)
        lb["VaR %5"] = (lb["VaR %5"]*100).round(2).astype(str) + "%"
        st.dataframe(lb, use_container_width=True, hide_index=True)
    else:
        st.caption("Henüz oyuncu yok.")
