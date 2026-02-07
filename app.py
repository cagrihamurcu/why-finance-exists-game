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

    # Direct (tekil yatırım) — yüksek oynaklık
    "P_SUCCESS": 0.65,
    "R_SUCCESS": 0.35,
    "R_FAILURE": -0.60,

    # Deposit — düşük risk, sabit getiri + likidite
    "R_DEPOSIT": 0.12,

    # Banka üzerinden (aracılı yatırım) — daha istikrarlı ama maliyetli (spread/fee)
    "BANK_EXPECTED": 0.18,
    "BANK_VOL": 0.05,
    "BANK_FEE": 0.03,  # maliyet: spread/komisyon

    # Likidite ihtiyacı (Direct'i vurur: zararına bozdurma/likidite maliyeti)
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
    if "turn" not in pl:
        pl["turn"] = 1
    if "wealth" not in pl:
        pl["wealth"] = CFG["START_CAP"]
    if "returns" not in pl:
        pl["returns"] = []
    if "log" not in pl:
        pl["log"] = []
    if "counterfactual_savings" not in pl:
        pl["counterfactual_savings"] = 0.0  # "finansın katkısı" göstergesi
    return pl

def get_player(name: str):
    if name not in st.session_state.players:
        st.session_state.players[name] = {
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
# UTIL: RETURN GENERATION
# =========================
def rng_for(name, turn):
    # deterministik: aynı oyuncu+tur -> aynı sonuç (tekrar edilebilir ders)
    return np.random.default_rng(st.session_state.seed + turn * 1000 + (hash(name) % 1000))

def direct_return(rng):
    success = rng.random() < CFG["P_SUCCESS"]
    return CFG["R_SUCCESS"] if success else CFG["R_FAILURE"]

def deposit_return():
    return CFG["R_DEPOSIT"]

def bank_return(rng, turn):
    vol = CFG["BANK_VOL"] + (CFG["CRISIS_VOL_BONUS"] if turn == CFG["CRISIS_TURN"] else 0.0)
    return rng.normal(CFG["BANK_EXPECTED"], vol) - CFG["BANK_FEE"]

def liquidity_shock_happens(rng, turn):
    p = CFG["P_LIQ"] + (CFG["CRISIS_LIQ_BONUS"] if turn == CFG["CRISIS_TURN"] else 0.0)
    return rng.random() < p

# =========================
# UI: HEADER + RESET
# =========================
st.title("🎮 1. Hafta Oyunu: Finansal Piyasalar ve Kurumlar Neden Var?")

with st.expander("📌 Oyun Nedir? (1 dakikalık açıklama)", expanded=True):
    st.markdown(
        """
**Senaryo:** Siz bir ekonomik birimsiniz (hane/şirket). Elinizde sermaye var. 6 tur boyunca karar veriyorsunuz.

**Amaç:** Şunu yaşayarak görmek:
- **Belirsizlik (risk)** altında sonuçlar nasıl dağılıyor?
- **Likidite ihtiyacı** gelince ne oluyor?
- **Finansal kurumlar** (banka/mevduat) neyi “maliyet karşılığında” iyileştiriyor?

**3 ana ders mesajı**
1) Risk yönetimi (oynaklık ve kötü senaryolar)  
2) Likidite (acil nakit ihtiyacı maliyeti)  
3) Aracılık (spread/komisyon karşılığında istikrar)

⚠️ **Tur 1–2:** “Finans yok” → sadece Direct Investment  
⚠️ **Tur 4:** Makro kriz → risk artar, likidite daha kritik olur  
        """
    )

col_reset1, col_reset2 = st.columns([1,3])
with col_reset1:
    if st.button("🧹 Oyunu Sıfırla"):
        st.session_state.clear()
        st.success("Sıfırlandı.")
        st.rerun()
with col_reset2:
    st.caption("Not: Kod güncelleyince garip hata olursa önce 'Oyunu Sıfırla'ya basın.")

# =========================
# MAIN LAYOUT
# =========================
left, right = st.columns([2.2, 1])

with left:
    name = st.text_input("Oyuncu Adı (takma isim)", placeholder="örn. T3_Ayşe / Mehmet / Takım-4")
    if not name:
        st.stop()

    pl = get_player(name)
    turn = pl["turn"]

    if turn > CFG["N_TURNS"]:
        st.success("✅ Oyun bitti. Sağdaki 'Finansın katkısı' paneline ve lider tablosuna bakın.")
    else:
        st.subheader(f"Tur {turn} / {CFG['N_TURNS']}")
        st.metric("Mevcut Servet (TL)", f"{pl['wealth']:,.0f}".replace(",", "."))

        # Turn narrative
        if turn in [1, 2]:
            st.info("🌍 TUR 1–2: 'Finans yok' dünyası. Seçenek yok: **Direct Investment** (tekil risk).")
        elif turn == 3:
            st.info("🏦 TUR 3: Mevduat ve banka seçeneği açıldı. Artık risk/likidite yönetebilirsiniz.")
        elif turn == CFG["CRISIS_TURN"]:
            st.warning("⚠️ TUR 4: MAKRO KRİZ. Sistematik risk artar, likidite şoku olasılığı yükselir.")
        else:
            st.info("🎯 Serbest tur: Risk–getiri–likidite dengesini siz kurun.")

        # Choices by turn
        options = ["Direct Investment"]
        if turn >= 3:
            options = ["Direct Investment", "Deposit", "Intermediated Investment (Banka)"]

        choice = st.radio("Seçiminiz:", options, horizontal=True)

        # Explain each option briefly (very important for clarity)
        with st.expander("Seçenekler ne anlama geliyor?", expanded=False):
            st.markdown(
                f"""
**Direct Investment:** Yüksek risk. Başarılıysa yüksek getiri, başarısızsa sert kayıp.  
Ayrıca **likidite ihtiyacı** gelirse “zararına bozdurma” maliyeti doğar.

**Deposit (Mevduat):** Daha güvenli ve likit. Getiri sınırlı ama istikrarlı.

**Intermediated Investment (Banka):** Spread/komisyon ödersiniz (**{CFG['BANK_FEE']*100:.1f}%**).  
Karşılığında sonuçlar genelde daha istikrarlıdır (risk yönetimi + aracılık).
                """
            )

        if st.button("✅ Kararı Onayla ve Sonucu Gör"):
            rng = rng_for(name, turn)

            # ---- Compute return with decomposition ----
            crisis = (turn == CFG["CRISIS_TURN"])
            liq = liquidity_shock_happens(rng, turn)

            base_r = 0.0
            fee_r = 0.0
            liq_penalty_r = 0.0
            crisis_r = 0.0

            if choice == "Direct Investment":
                base_r = direct_return(rng)
                # liquidity penalty only meaningful for Direct
                if liq:
                    liq_penalty_r = -CFG["LIQ_COST"]
                if crisis:
                    crisis_r = -CFG["CRISIS_HIT_DIRECT"]

            elif choice == "Deposit":
                base_r = deposit_return()
                # deposit: no extra crisis penalty in Week1 (flight to quality message)

            else:  # Bank
                # bank_return already includes fee subtraction, but we want decomposition:
                # compute before fee
                vol = CFG["BANK_VOL"] + (CFG["CRISIS_VOL_BONUS"] if crisis else 0.0)
                gross = rng.normal(CFG["BANK_EXPECTED"], vol)
                fee_r = -CFG["BANK_FEE"]
                base_r = gross
                if crisis:
                    crisis_r = -CFG["CRISIS_HIT_BANK"]

            total_r = base_r + fee_r + liq_penalty_r + crisis_r

            # ---- Apply to wealth ----
            old_wealth = pl["wealth"]
            new_wealth = old_wealth * (1.0 + total_r)
            pl["wealth"] = new_wealth
            pl["returns"].append(float(total_r))

            # ---- Counterfactual: "Finansın katkısı" görünür olsun ----
            # Compare to always-Direct path for THIS turn (same RNG seed logic)
            # This is not perfect economics; it's a teaching device.
            rng_cf = rng_for(name + "_cf", turn)  # different but deterministic
            cf_base = direct_return(rng_cf)
            cf_liq = liquidity_shock_happens(rng_cf, turn)
            cf_r = cf_base + (-CFG["LIQ_COST"] if cf_liq else 0.0) + (-CFG["CRISIS_HIT_DIRECT"] if crisis else 0.0)
            cf_wealth = old_wealth * (1.0 + cf_r)

            # If their chosen path yields higher wealth than cf, accumulate "benefit"
            pl["counterfactual_savings"] += max(0.0, new_wealth - cf_wealth)

            # ---- Log ----
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
                "Wealth": new_wealth
            })

            # ---- Display results in a TEACHING way ----
            st.success(f"Toplam Getiri: %{total_r*100:.2f} | Yeni Servet: {new_wealth:,.0f} TL".replace(",", "."))

            st.markdown("### Bu tur ne oldu? (Getiri bileşenleri)")
            comp = pd.DataFrame([{
                "Bileşen": "Temel getiri",
                "Etki (%)": base_r * 100
            },{
                "Bileşen": "Aracılık maliyeti (spread/fee)",
                "Etki (%)": fee_r * 100
            },{
                "Bileşen": "Likidite ihtiyacı maliyeti",
                "Etki (%)": liq_penalty_r * 100
            },{
                "Bileşen": "Makro kriz etkisi",
                "Etki (%)": crisis_r * 100
            },{
                "Bileşen": "TOPLAM",
                "Etki (%)": total_r * 100
            }])
            st.dataframe(comp, use_container_width=True, hide_index=True)

            st.markdown("### Finansın katkısı (bu tur karşılaştırma)")
            st.caption("Karşılaştırma: Bu tur aynı sermaye ile **Direct Investment yapsaydınız** ne olurdu? (öğretici karşı-olgusal kıyas)")
            st.write(
                f"- Seçtiğiniz yol ile tur sonu servet: **{new_wealth:,.0f} TL**\n"
                f"- Direct yapsaydınız tur sonu servet: **{cf_wealth:,.0f} TL**"
                .replace(",", ".")
            )

            # Next turn
            pl["turn"] += 1
            st.button("➡️ Devam (Yeni Tur)", on_click=st.rerun)

    # Personal log
    if pl["log"]:
        st.markdown("## Tur Geçmişi (Kişisel)")
        df = pd.DataFrame(pl["log"])
        df["TotalReturn %"] = df["TotalReturn"] * 100
        show = df[["Turn","Choice","TotalReturn %","MacroCrisis","LiquidityShock","Wealth"]].copy()
        st.dataframe(show, use_container_width=True, hide_index=True)

with right:
    st.subheader("🎓 Finansın Katkısı (öğrenme paneli)")

    loss_turns = sum(1 for r in pl["returns"] if r < 0)
    st.metric("Zarar Yaşanan Tur", str(loss_turns))
    st.metric("VaR %5 (Getiri)", f"{var5(pl)*100:.2f}%")
    st.metric("Skor", f"{score(pl):,.0f}".replace(",", "."))

    st.divider()
    st.metric("‘Finansın katkısı’ göstergesi (birikimli)", f"{pl['counterfactual_savings']:,.0f} TL".replace(",", "."))
    st.caption("Bu değer, seçtiğiniz istikrarlı/likit seçeneklerin Direct’e göre koruduğu serveti öğretici amaçla gösterir.")

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
