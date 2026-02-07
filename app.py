import streamlit as st
import numpy as np
import pandas as pd

st.set_page_config(page_title="Risk Havuzu Oyunu — 1. Hafta", layout="wide")

# -----------------------------
# Parameters (Week 1: Why finance exists?)
# -----------------------------
DEFAULTS = {
    "START_CAP": 1_000_000.0,
    "N_TURNS": 6,

    # Shock process
    "P_SHOCK": 0.20,          # probability each turn
    "SHOCK_LOSS": 250_000.0,  # TL loss if shock happens

    # Pool mechanics
    "PREMIUM": 35_000.0,      # TL paid per turn if you join the pool
    "COVERAGE": 0.80,         # pool pays this fraction of loss
    "POOL_INITIAL": 0.0,      # start pool balance
    "POOL_INTEREST": 0.00,    # optional interest on pool balance per turn (keep 0 for week 1 clarity)

    # Scoring
    "LOSS_TURN_PENALTY": 120_000.0,  # TL penalty per loss turn (keeps luck from dominating)
}

# -----------------------------
# Session state init
# -----------------------------
if "players" not in st.session_state:
    st.session_state.players = {}  # name -> dict

if "world_seed" not in st.session_state:
    st.session_state.world_seed = 20260208  # fixed seed for reproducibility

if "pool_balance" not in st.session_state:
    st.session_state.pool_balance = DEFAULTS["POOL_INITIAL"]

if "current_turn" not in st.session_state:
    st.session_state.current_turn = 1

if "turn_resolved" not in st.session_state:
    st.session_state.turn_resolved = False  # prevent double-resolve

def get_player(name: str):
    if name not in st.session_state.players:
        st.session_state.players[name] = {
            "wealth": DEFAULTS["START_CAP"],
            "joined": [],         # join decision each turn (bool)
            "shocks": [],         # shock occurred (bool)
            "net_change": [],     # TL net change each turn
            "log": []             # per-turn record
        }
    return st.session_state.players[name]

def score(player):
    loss_turns = sum(1 for x in player["net_change"] if x < 0)
    return player["wealth"] - DEFAULTS["LOSS_TURN_PENALTY"] * loss_turns

def var5_tl(player):
    # VaR on TL net changes (negative tail). Report 5th percentile of net change.
    if len(player["net_change"]) == 0:
        return 0.0
    return float(np.percentile(np.array(player["net_change"]), 5))

# -----------------------------
# Sidebar: Instructor controls
# -----------------------------
with st.sidebar:
    st.header("🎛️ Eğitmen Paneli")
    st.caption("1. hafta için: risk havuzunun (aracılığın) değerini 'hissettirme' amaçlıdır.")

    seed = st.number_input("Dünya Seed", value=int(st.session_state.world_seed), step=1)
    if st.button("Seed uygula"):
        st.session_state.world_seed = int(seed)
        st.success("Seed güncellendi. Yeni şok dizisi oluşur (gelecek turlar için).")

    st.divider()
    st.subheader("Oyun Parametreleri (isteğe bağlı)")
    START_CAP = st.number_input("START_CAP", value=float(DEFAULTS["START_CAP"]), step=50_000.0)
    N_TURNS = st.number_input("N_TURNS", value=int(DEFAULTS["N_TURNS"]), step=1, min_value=3, max_value=12)
    P_SHOCK = st.slider("P_SHOCK", 0.05, 0.60, float(DEFAULTS["P_SHOCK"]), 0.01)
    SHOCK_LOSS = st.number_input("SHOCK_LOSS (TL)", value=float(DEFAULTS["SHOCK_LOSS"]), step=25_000.0)
    PREMIUM = st.number_input("PREMIUM (TL)", value=float(DEFAULTS["PREMIUM"]), step=5_000.0)
    COVERAGE = st.slider("COVERAGE", 0.10, 1.00, float(DEFAULTS["COVERAGE"]), 0.05)
    POOL_INTEREST = st.slider("POOL_INTEREST (turn)", 0.00, 0.05, float(DEFAULTS["POOL_INTEREST"]), 0.005)
    LOSS_TURN_PENALTY = st.number_input("LOSS_TURN_PENALTY", value=float(DEFAULTS["LOSS_TURN_PENALTY"]), step=10_000.0)

    st.caption("Not: Parametreleri derste değiştirmeyin; önceden belirleyip sabitlemek daha iyi.")

    st.divider()
    if st.button("🧹 Oyunu Sıfırla (Tüm Oyuncular + Havuz)"):
        st.session_state.players = {}
        st.session_state.pool_balance = DEFAULTS["POOL_INITIAL"]
        st.session_state.current_turn = 1
        st.session_state.turn_resolved = False
        st.success("Oyun sıfırlandı.")

# Apply live params (kept in local variables)
PARAM = {
    "START_CAP": START_CAP,
    "N_TURNS": int(N_TURNS),
    "P_SHOCK": float(P_SHOCK),
    "SHOCK_LOSS": float(SHOCK_LOSS),
    "PREMIUM": float(PREMIUM),
    "COVERAGE": float(COVERAGE),
    "POOL_INTEREST": float(POOL_INTEREST),
    "LOSS_TURN_PENALTY": float(LOSS_TURN_PENALTY),
}

# -----------------------------
# Header
# -----------------------------
st.title("🎮 Risk Havuzu Oyunu — 1. Hafta (Finans Neden Var?)")
st.write(
    "Her tur bir seçim yapacaksınız: **Havuza gir** (prim öde) veya **Tek başına kal**.\n\n"
    "Şok gelirse tek başına kalanlar zararı tamamen taşır; havuzdakiler zararın bir kısmını havuzdan alır.\n\n"
    "Ama havuzun da bir bütçesi var: **havuz bakiyesi** sınıfın ortak riski taşıma kapasitesini gösterir."
)

# -----------------------------
# Main layout
# -----------------------------
left, right = st.columns([2.2, 1])

with left:
    name = st.text_input("Oyuncu Adı (takma isim):", placeholder="örn. T2_Ayşe / Mehmet / Takım-4")
    if not name:
        st.info("Başlamak için bir oyuncu adı girin.")
        st.stop()

    player = get_player(name)

    # sync start cap if user changed param mid-session
    if len(player["log"]) == 0 and player["wealth"] != PARAM["START_CAP"]:
        player["wealth"] = PARAM["START_CAP"]

    turn = st.session_state.current_turn
    st.subheader(f"Tur: {turn} / {PARAM['N_TURNS']}")

    st.metric("Mevcut Servet (TL)", f"{player['wealth']:,.0f}".replace(",", "."))
    st.metric("Havuz Bakiyesi (TL)", f"{st.session_state.pool_balance:,.0f}".replace(",", "."))

    st.write("### Seçim")
    join_pool = st.radio(
        "Bu tur havuza girecek misiniz?",
        options=["Havuza gir (prim öde)", "Tek başıma kal"],
        horizontal=True
    ) == "Havuza gir (prim öde)"

    st.caption(
        f"Prim: {PARAM['PREMIUM']:,.0f} TL | Şok olursa zarar: {PARAM['SHOCK_LOSS']:,.0f} TL | "
        f"Havuz kapsamı: %{int(PARAM['COVERAGE']*100)}".replace(",", ".")
    )

    # Submit decision (stored, turn resolved centrally)
    if st.button("✅ Kararı Kaydet"):
        # Ensure player hasn't already submitted for this turn
        already = any(rec["Turn"] == turn for rec in player["log"])
        if already:
            st.warning("Bu tur için kararınız zaten kaydedilmiş.")
        else:
            player["joined"].append(bool(join_pool))
            player["log"].append({
                "Turn": turn,
                "Decision": "JOIN" if join_pool else "SOLO",
                "Shock": None,
                "PremiumPaid": 0.0,
                "Compensation": 0.0,
                "NetChange": 0.0,
                "Wealth": player["wealth"],
                "PoolBalance": st.session_state.pool_balance
            })
            st.success("Karar kaydedildi. (Tur sonuçları 'Tur Sonuçlarını Çalıştır' ile açıklanacak.)")

    st.divider()

    # Instructor-like "Run turn" button visible to all (works well in lab if you ask everyone not to press)
    # If you prefer: only instructor presses on projected PC.
    st.write("### 🧪 Tur Sonuçlarını Çalıştır (sınıfça aynı anda)")
    st.caption("Öneri: Bu butona sadece öğretim elemanı bassın (projeksiyondaki bilgisayardan).")

    if st.button("🎲 TURU ÇALIŞTIR"):
        if st.session_state.turn_resolved:
            st.warning("Bu tur zaten çalıştırıldı. Yeni tur için 'Yeni Tura Geç' kullanın.")
        else:
            # apply pool interest
            st.session_state.pool_balance *= (1.0 + PARAM["POOL_INTEREST"])

            # resolve shocks for all players who submitted decision for this turn
            rng = np.random.default_rng(st.session_state.world_seed + turn * 10_000)

            for pname, pl in st.session_state.players.items():
                # find turn record
                recs = [r for r in pl["log"] if r["Turn"] == turn]
                if not recs:
                    continue  # no decision submitted
                rec = recs[0]
                # decide shock
                shock = rng.random() < PARAM["P_SHOCK"]
                loss = PARAM["SHOCK_LOSS"] if shock else 0.0

                # premium if joined
                joined = (rec["Decision"] == "JOIN")
                premium_paid = PARAM["PREMIUM"] if joined else 0.0

                # update pool with premium
                st.session_state.pool_balance += premium_paid

                # compensation if shock and joined
                comp = 0.0
                if shock and joined:
                    desired = PARAM["COVERAGE"] * loss
                    # pay as much as pool allows (pool can run low -> important lesson)
                    pay = min(desired, st.session_state.pool_balance)
                    comp = pay
                    st.session_state.pool_balance -= pay

                # net change
                net = -premium_paid - loss + comp

                pl["wealth"] += net
                pl["shocks"].append(bool(shock))
                pl["net_change"].append(float(net))

                # update record
                rec["Shock"] = shock
                rec["PremiumPaid"] = float(premium_paid)
                rec["Compensation"] = float(comp)
                rec["NetChange"] = float(net)
                rec["Wealth"] = float(pl["wealth"])
                rec["PoolBalance"] = float(st.session_state.pool_balance)

            st.session_state.turn_resolved = True
            st.success("Tur çalıştırıldı. Sonuçları aşağıdaki tablolardan inceleyin.")

    if st.button("➡️ Yeni Tura Geç"):
        if not st.session_state.turn_resolved:
            st.warning("Önce tur sonuçlarını çalıştırın.")
        else:
            if st.session_state.current_turn >= PARAM["N_TURNS"]:
                st.info("Oyun bitti. Lider tablosuna bakın.")
            else:
                st.session_state.current_turn += 1
                st.session_state.turn_resolved = False
                st.success("Yeni tura geçildi.")

    # Show player's log
    if player["log"]:
        st.write("### Tur Geçmişi (Kişisel)")
        df = pd.DataFrame(player["log"])
        df_disp = df[["Turn", "Decision", "Shock", "PremiumPaid", "Compensation", "NetChange", "Wealth"]].copy()
        st.dataframe(df_disp, use_container_width=True, hide_index=True)

with right:
    st.subheader("📌 Kişisel Risk Özeti")
    loss_turns = sum(1 for x in player["net_change"] if x < 0)
    st.metric("Zarar Yaşanan Tur", str(loss_turns))
    st.metric("VaR %5 (Net Değişim, TL)", f"{var5_tl(player):,.0f}".replace(",", "."))
    st.metric("Skor", f"{score(player):,.0f}".replace(",", "."))

    st.divider()
    st.subheader("🏦 Havuz İstatistikleri (Sınıf)")
    # class summary for current turn
    total_players = len(st.session_state.players)
    joined_count = 0
    submitted_count = 0
    for pname, pl in st.session_state.players.items():
        if any(r["Turn"] == st.session_state.current_turn for r in pl["log"]):
            submitted_count += 1
            rec = [r for r in pl["log"] if r["Turn"] == st.session_state.current_turn][0]
            if rec["Decision"] == "JOIN":
                joined_count += 1

    st.metric("Toplam Oyuncu", str(total_players))
    st.metric("Bu Tur Karar Veren", str(submitted_count))
    st.metric("Bu Tur Havuza Giren", str(joined_count))
    st.metric("Havuz Bakiyesi (TL)", f"{st.session_state.pool_balance:,.0f}".replace(",", "."))

    st.divider()
    st.subheader("🏆 Lider Tablosu")
    rows = []
    for pname, pl in st.session_state.players.items():
        rows.append({
            "Oyuncu": pname,
            "Tur": len(pl["net_change"]),
            "Servet (TL)": pl["wealth"],
            "Zarar Tur": sum(1 for x in pl["net_change"] if x < 0),
            "VaR%5 (TL)": var5_tl(pl),
            "Skor": score(pl),
        })
    if rows:
        lb = pd.DataFrame(rows).sort_values("Skor", ascending=False)
        # pretty formatting
        lb["Servet (TL)"] = lb["Servet (TL)"].round(0)
        lb["VaR%5 (TL)"] = lb["VaR%5 (TL)"].round(0)
        lb["Skor"] = lb["Skor"].round(0)
        st.dataframe(lb, use_container_width=True, hide_index=True)
    else:
        st.caption("Henüz oyuncu yok.")

    st.divider()
    st.subheader("💡 Ders Mesajı (1 cümle)")
    st.write("Finans = **riskin havuzlanması ve paylaşılması**. Tek başına kalan, aynı şoka daha kırılgan olur.")
