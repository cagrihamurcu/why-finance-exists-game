import streamlit as st
import numpy as np
import pandas as pd

st.set_page_config(page_title="1. Hafta Oyunu — Finans Neden Var?", layout="wide")

# =========================
# PARAMETRELER (1. hafta)
# =========================
CFG = {
    "START_CAP": 1_000_000.0,
    "N_TURNS": 6,

    # Direct Investment (tekil yatırım) — yüksek oynaklık
    "P_SUCCESS": 0.65,
    "R_SUCCESS": 0.35,
    "R_FAILURE": -0.60,

    # Deposit (mevduat) — düşük risk
    "R_DEPOSIT": 0.12,

    # Intermediated Investment (banka) — daha istikrarlı ama maliyetli
    "BANK_EXPECTED": 0.18,
    "BANK_VOL": 0.05,
    "BANK_FEE": 0.03,  # spread/komisyon

    # Likidite ihtiyacı (Direct'i vurur)
    "P_LIQ": 0.15,
    "LIQ_COST": 0.20,

    # Makro kriz (Tur 4)
    "CRISIS_TURN": 4,
    "CRISIS_HIT_DIRECT": 0.15,
    "CRISIS_HIT_BANK": 0.08,
    "CRISIS_VOL_BONUS": 0.06,
    "CRISIS_LIQ_BONUS": 0.15,

    # Skor (şansı törpüler)
    "LOSS_PENALTY": 120_000.0,
}

# =========================
# SESSION STATE
# =========================
if "seed" not in st.session_state:
    st.session_state.seed = 20260209

if "players" not in st.session_state:
    st.session_state.players = {}

def migrate_player(pl):
    # Eski sürümlerden kalan kayıtları otomatik düzeltir (KeyError önler)
    if "scenario_ok" not in pl:
        pl["scenario_ok"] = False
    if "turn" not in pl:
        pl["turn"] = 1
    if "wealth" not in pl:
        pl["wealth"] = CFG["START_CAP"]
    if "returns" not in pl:
        pl["returns"] = []
    if "log" not in pl:
        pl["log"] = []
    if "counterfactual_savings" not in pl:
        pl["counterfactual_savings"] = 0.0
    return pl

def get_player(name: str):
    if name not in st.session_state.players:
        st.session_state.players[name] = {
            "scenario_ok": False,
            "turn": 1,
            "wealth": CFG["START_CAP"],
            "returns": [],
            "log": [],
            "counterfactual_savings": 0.0
        }
    st.session_state.players[name] = migrate_player(st.session_state.players[name])
    return st.session_state.players[name]

def score(pl):
    loss_turns = sum(1 for r in pl["returns"] if r < 0)
    return pl["wealth"] - CFG["LOSS_PENALTY"] * loss_turns

def var5(pl):
    if not pl["returns"]:
        return 0.0
    return float(np.percentile(np.array(pl["returns"]), 5))

# =========================
# RNG & RETURN HELPERS
# =========================
def rng_for(name, turn):
    return np.random.default_rng(st.session_state.seed + turn * 1000 + (hash(name) % 1000))

def direct_return(rng):
    success = rng.random() < CFG["P_SUCCESS"]
    return CFG["R_SUCCESS"] if success else CFG["R_FAILURE"]

def deposit_return():
    return CFG["R_DEPOSIT"]

def bank_return_components(rng, turn):
    vol = CFG["BANK_VOL"] + (CFG["CRISIS_VOL_BONUS"] if turn == CFG["CRISIS_TURN"] else 0.0)
    gross = rng.normal(CFG["BANK_EXPECTED"], vol)
    fee = -CFG["BANK_FEE"]
    return gross, fee

def liquidity_shock_happens(rng, turn):
    p = CFG["P_LIQ"] + (CFG["CRISIS_LIQ_BONUS"] if turn == CFG["CRISIS_TURN"] else 0.0)
    return rng.random() < p

# =========================
# UI: HEADER + RESET
# =========================
st.title("🎮 1. Hafta Oyunu: Finansal Piyasalar ve Kurumlar Neden Var?")

top1, top2 = st.columns([1, 2])
with top1:
    if st.button("🧹 Oyunu Sıfırla"):
        st.session_state.clear()
        st.success("Sıfırlandı.")
        st.rerun()
with top2:
    st.caption("Kod güncellemesi sonrası hata olursa önce 'Oyunu Sıfırla'ya basın.")

# =========================
# MAIN LAYOUT
# =========================
left, right = st.columns([2.2, 1])

with left:
    name = st.text_input("Oyuncu Adı (takma isim)", placeholder="örn. T3_Ayşe / Mehmet / Takım-4")
    if not name:
        st.stop()

    pl = get_player(name)

    # Ensure start cap applies for new players
    if len(pl["log"]) == 0 and abs(pl["wealth"] - CFG["START_CAP"]) > 1e-6:
        pl["wealth"] = CFG["START_CAP"]

    # -------------------------
    # Scenario gate (must read)
    # -------------------------
    if not pl["scenario_ok"]:
        st.subheader("📌 OYUN SENARYOSU (Okuyun → Başlayın)")
        st.markdown(
            """
## 🌍 Finansal Sistem Olmadan Bir Ekonomi

Bu oyunda yeni kurulmuş bir ekonomide faaliyet gösteriyorsunuz.

- **Başlangıç sermayeniz:** 1.000.000 TL  
- **Süre:** 6 tur  
- Ekonomide **belirsizlik** vardır.  
- Zaman zaman **likidite ihtiyacı** doğabilir.  
- **4. turda makro bir kriz** yaşanacaktır.

### İlk iki turda (Tur 1–2):
- **Banka yok**
- **Mevduat yok**
- **Risk yönetimi/likidite desteği yok**
- Yalnızca **Direct Investment** (tekil risk) vardır.

### 3. turdan itibaren:
- **Mevduat** ve **Banka aracılığıyla yatırım** seçenekleri açılır.
- Banka seçeneği daha istikrarlı olabilir; ancak **spread/komisyon** maliyeti vardır.

### 🎯 Amaç:
6 tur sonunda şu soruya veriyle cevap vereceğiz:

**“Finansal kurumlar sadece maliyet mi üretir, yoksa belirsizliği ve likiditeyi yöneterek istikrar mı sağlar?”**
            """
        )
        if st.button("✅ Senaryoyu okudum, oyuna başla"):
            pl["scenario_ok"] = True
            st.rerun()
        st.stop()

    # -------------------------
    # Turn panel
    # -------------------------
    turn = pl["turn"]
    if turn > CFG["N_TURNS"]:
        st.success("✅ Oyun bitti. Sağdaki panel ve lider tablosunu inceleyin.")
    else:
        st.subheader(f"Tur {turn} / {CFG['N_TURNS']}")
        st.metric("Mevcut Servet (TL)", f"{pl['wealth']:,.0f}".replace(",", "."))

        # Turn narrative
        if turn in [1, 2]:
            st.info("🌍 TUR 1–2: Finansal kurum yok → seçenek yok: **Direct Investment** (tekil risk).")
        elif turn == 3:
            st.info("🏦 TUR 3: Mevduat ve banka seçeneği açıldı → risk/likidite yönetilebilir.")
        elif turn == CFG["CRISIS_TURN"]:
            st.warning("⚠️ TUR 4: MAKRO KRİZ → risk artar, likidite ihtiyacı daha kritik olur.")
        else:
            st.info("🎯 Serbest tur: Risk–getiri–likidite dengesini siz kurun.")

        # Choices by turn
        options = ["Direct Investment"]
        if turn >= 3:
            options = ["Direct Investment", "Deposit", "Intermediated Investment (Banka)"]

        choice = st.radio("Seçiminiz:", options, horizontal=True)

        with st.expander("Seçeneklerin anlamı (kısa)", expanded=False):
            st.markdown(
                f"""
**Direct Investment:** Yüksek risk. Başarılıysa yüksek getiri, başarısızsa sert kayıp.  
Likidite ihtiyacı gelirse ayrıca maliyet doğabilir.

**Deposit (Mevduat):** Daha güvenli ve likit. Getiri sınırlı ama istikrarlı.

**Intermediated Investment (Banka):** Spread/komisyon ödersiniz (**{CFG['BANK_FEE']*100:.1f}%**).  
Karşılığında sonuçlar genelde daha istikrarlıdır.
                """
            )

        if st.button("✅ Kararı Onayla ve Sonucu Gör"):
            rng = rng_for(name, turn)
            crisis = (turn == CFG["CRISIS_TURN"])
            liq = liquidity_shock_happens(rng, turn)

            # Decomposition
            base_r = 0.0
            fee_r = 0.0
            liq_penalty_r = 0.0
            crisis_r = 0.0

            if choice == "Direct Investment":
                base_r = direct_return(rng)
                if liq:
                    liq_penalty_r = -CFG["LIQ_COST"]
                if crisis:
                    crisis_r = -CFG["CRISIS_HIT_DIRECT"]

            elif choice == "Deposit":
                base_r = deposit_return()
                # deposit: crisis penalty intentionally 0 for week1 message (flight-to-quality)

            else:
                gross, fee = bank_return_components(rng, turn)
                base_r = gross
                fee_r = fee
                if crisis:
                    crisis_r = -CFG["CRISIS_HIT_BANK"]

            total_r = base_r + fee_r + liq_penalty_r + crisis_r

            old_wealth = pl["wealth"]
            new_wealth = old_wealth * (1.0 + total_r)
            pl["wealth"] = new_wealth
            pl["returns"].append(float(total_r))

            # Teaching counterfactual: "If Direct this turn"
            rng_cf = rng_for(name + "_cf", turn)
            cf_base = direct_return(rng_cf)
            cf_liq = liquidity_shock_happens(rng_cf, turn)
            cf_r = cf_base + (-CFG["LIQ_COST"] if cf_liq else 0.0) + (-CFG["CRISIS_HIT_DIRECT"] if crisis else 0.0)
            cf_wealth = old_wealth * (1.0 + cf_r)
            pl["counterfactual_savings"] += max(0.0, new_wealth - cf_wealth)

            pl["log"].append({
                "Turn": turn,
                "Choice": choice,
                "BaseReturn": base_r,
                "Fee": fee_r,
                "LiquidityPenalty": liq_penalty_r,
                "CrisisEffect": crisis_r,
                "TotalReturn": total_r,
                "MacroCrisis": crisis,
                "LiquidityShock": (liq and choice == "Direct Investment"),
                "Wealth": new_wealth,
                "Direct_CF_Wealth": cf_wealth
            })

            st.success(f"Toplam Getiri: %{total_r*100:.2f} | Yeni Servet: {new_wealth:,.0f} TL".replace(",", "."))

            st.markdown("### Bu tur getiri nasıl oluştu? (bileşenler)")
            comp = pd.DataFrame([
                {"Bileşen": "Temel getiri", "Etki (%)": base_r * 100},
                {"Bileşen": "Aracılık maliyeti (spread/komisyon)", "Etki (%)": fee_r * 100},
                {"Bileşen": "Likidite ihtiyacı maliyeti", "Etki (%)": liq_penalty_r * 100},
                {"Bileşen": "Makro kriz etkisi", "Etki (%)": crisis_r * 100},
                {"Bileşen": "TOPLAM", "Etki (%)": total_r * 100},
            ])
            st.dataframe(comp, use_container_width=True, hide_index=True)

            st.markdown("### Finansın katkısı (bu tur karşılaştırma)")
            st.caption("Öğretici kıyas: Bu tur Direct Investment yapsaydınız tur sonu servet ne olurdu?")
            st.write(
                f"- Seçtiğiniz yol: **{new_wealth:,.0f} TL**\n"
                f"- Bu tur Direct yapsaydınız: **{cf_wealth:,.0f} TL**"
                .replace(",", ".")
            )

            # Next turn
            pl["turn"] += 1
            st.rerun()

    # Personal log
    if pl["log"]:
        st.markdown("## Tur Geçmişi (Kişisel)")
        df = pd.DataFrame(pl["log"])
        df["TotalReturn %"] = df["TotalReturn"] * 100
        show = df[["Turn","Choice","TotalReturn %","MacroCrisis","LiquidityShock","Wealth"]].copy()
        st.dataframe(show, use_container_width=True, hide_index=True)

with right:
    # If name not provided, right panel will be blank (handled by stop above)
    if name:
        pl = get_player(name)

        st.subheader("🎓 Öğrenme Paneli")
        loss_turns = sum(1 for r in pl["returns"] if r < 0)
        st.metric("Zarar Yaşanan Tur", str(loss_turns))
        st.metric("VaR %5 (Getiri)", f"{var5(pl)*100:.2f}%")
        st.metric("Skor", f"{score(pl):,.0f}".replace(",", "."))

        st.divider()
        st.metric("Finansın katkısı (birikimli)", f"{pl['counterfactual_savings']:,.0f} TL".replace(",", "."))
        st.caption("Bu değer, seçtiğiniz seçeneklerin Direct’e göre koruduğu serveti öğretici amaçla gösterir.")

    st.divider()
    st.subheader("🏆 Lider Tablosu")
    rows = []
    for pname, p in st.session_state.players.items():
        p = migrate_player(p)
        rows.append({
            "Oyuncu": pname,
            "Tur": min(p["turn"] - 1, CFG["N_TURNS"]),
            "Servet (TL)": p["wealth"],
            "Zarar Tur": sum(1 for r in p["returns"] if r < 0),
            "VaR %5": var5(p),
            "Skor": score(p),
        })

    if rows:
        lb = pd.DataFrame(rows).sort_values("Skor", ascending=False)
        lb["Servet (TL)"] = lb["Servet (TL)"].round(0)
        lb["VaR %5"] = (lb["VaR %5"]*100).round(2).astype(str) + "%"
        lb["Skor"] = lb["Skor"].round(0)
        st.dataframe(lb, use_container_width=True, hide_index=True)
    else:
        st.caption("Henüz oyuncu yok.")
