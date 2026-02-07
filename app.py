import streamlit as st
import numpy as np
import pandas as pd

st.set_page_config(page_title="1. Hafta Oyunu — Finans Neden Var?", layout="wide")

# =========================
# 1. HAFTA PARAMETRELERİ
# =========================
CFG = {
    "START_CAP": 1_000_000.0,
    "N_TURNS": 6,

    # Direct Investment (tekil yatırım) — yüksek oynaklık
    "P_SUCCESS": 0.65,
    "R_SUCCESS": 0.35,
    "R_FAILURE": -0.60,

    # Deposit (mevduat) — düşük risk (krizde hafif etkilenebilir)
    "R_DEPOSIT": 0.12,
    "DEPOSIT_CRISIS_HIT": 0.02,  # tur 4'te mevduata küçük negatif etki (opsiyonel ama eğitici)

    # Intermediated (banka üzerinden) — daha istikrarlı ama maliyetli (spread/fee)
    "BANK_EXPECTED": 0.18,
    "BANK_VOL": 0.05,
    "BANK_FEE": 0.03,  # spread/komisyon

    # Likidite ihtiyacı: Direct'i vurur (zararına bozdurma)
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

NEWS = {
    1: "🗞️ Haber: Piyasa yeni kuruluyor. Finansal kurumlar yok. Yatırımlar doğrudan ve kırılgan.",
    2: "🗞️ Haber: Belirsizlik sürüyor. Likidite ihtiyacı olanlar yatırımını zararına bozuyor.",
    3: "🗞️ Haber: Bankalar ve mevduat ürünleri devreye giriyor. Aracılık maliyeti (spread) ortaya çıkıyor.",
    4: "🚨 MANŞET: Makro kriz! Risk artıyor, likidite sıkışıyor, belirsizlik yükseliyor.",
    5: "🗞️ Haber: Kriz sonrası denge arayışı. İstikrar mı, getiri mi? Portföy kararları belirleyici.",
    6: "🗞️ Haber: Toparlanma. Geçmiş kararlarınızın etkisi netleşiyor."
}

# =========================
# SESSION STATE
# =========================
if "seed" not in st.session_state:
    st.session_state.seed = 20260209

if "players" not in st.session_state:
    st.session_state.players = {}

def migrate_player(pl):
    # Eski sürümlere uyum (KeyError önler)
    if "scenario_ok" not in pl: pl["scenario_ok"] = False
    if "turn" not in pl: pl["turn"] = 1
    if "wealth" not in pl: pl["wealth"] = CFG["START_CAP"]
    if "log" not in pl: pl["log"] = []
    if "counterfactual_gain" not in pl: pl["counterfactual_gain"] = 0.0
    return pl

def get_player(name: str):
    if name not in st.session_state.players:
        st.session_state.players[name] = {
            "scenario_ok": False,
            "turn": 1,
            "wealth": CFG["START_CAP"],
            "log": [],
            "counterfactual_gain": 0.0
        }
    st.session_state.players[name] = migrate_player(st.session_state.players[name])
    return st.session_state.players[name]

# =========================
# RNG ve "DURUM" ÜRETİMİ
# (Eğiticilik için: Aynı turda farklı seçeneklerin
#  "karşılaştırması" aynı temel duruma dayanır.)
# =========================
def rng_for(name: str, turn: int):
    return np.random.default_rng(st.session_state.seed + turn * 10_000 + (hash(name) % 10_000))

def draw_state(rng: np.random.Generator, turn: int):
    """Bir tur için ekonomik 'durumu' üretir:
    - Direct başarı/başarısızlık
    - Banka brüt getiri (komisyon öncesi)
    - Likidite şoku (olursa Direct'e ceza)
    - Kriz (tur 4)
    """
    crisis = (turn == CFG["CRISIS_TURN"])

    direct_success = (rng.random() < CFG["P_SUCCESS"])
    direct_base = CFG["R_SUCCESS"] if direct_success else CFG["R_FAILURE"]

    bank_vol = CFG["BANK_VOL"] + (CFG["CRISIS_VOL_BONUS"] if crisis else 0.0)
    bank_gross = rng.normal(CFG["BANK_EXPECTED"], bank_vol)  # fee öncesi

    p_liq = CFG["P_LIQ"] + (CFG["CRISIS_LIQ_BONUS"] if crisis else 0.0)
    liq = (rng.random() < p_liq)

    return {
        "crisis": crisis,
        "direct_success": direct_success,
        "direct_base": direct_base,
        "bank_gross": bank_gross,
        "liq": liq
    }

def option_return(choice: str, state: dict, turn: int):
    """Seçeneğe göre getiriyi bileşenleriyle hesaplar."""
    crisis = state["crisis"]
    liq = state["liq"]

    base_r = fee_r = liq_pen_r = crisis_r = 0.0

    if choice == "Direct Investment":
        base_r = state["direct_base"]
        if liq:
            liq_pen_r = -CFG["LIQ_COST"]
        if crisis:
            crisis_r = -CFG["CRISIS_HIT_DIRECT"]

    elif choice == "Deposit":
        base_r = CFG["R_DEPOSIT"]
        if crisis:
            crisis_r = -CFG["DEPOSIT_CRISIS_HIT"]

    else:  # Banka
        base_r = state["bank_gross"]
        fee_r = -CFG["BANK_FEE"]
        if crisis:
            crisis_r = -CFG["CRISIS_HIT_BANK"]

    total_r = base_r + fee_r + liq_pen_r + crisis_r

    return total_r, {
        "Temel getiri": base_r,
        "Aracılık maliyeti (spread/komisyon)": fee_r,
        "Likidite ihtiyacı maliyeti": liq_pen_r,
        "Makro kriz etkisi": crisis_r,
        "TOPLAM": total_r
    }

def score(pl):
    # Zarar tur sayısı = toplam getiri < 0 olan turlar
    loss_turns = 0
    for rec in pl["log"]:
        if rec.get("TotalReturn", 0) < 0:
            loss_turns += 1
    return pl["wealth"] - CFG["LOSS_PENALTY"] * loss_turns

def var5(pl):
    if not pl["log"]:
        return 0.0
    arr = np.array([rec["TotalReturn"] for rec in pl["log"]], dtype=float)
    return float(np.percentile(arr, 5))

# =========================
# UI: Başlık + Eğitmen mini paneli
# =========================
st.title("🎮 1. Hafta Oyunu: Neden Finansal Piyasalar ve Kurumlarla İlgilenmekteyiz?")

topA, topB, topC = st.columns([1, 1, 2])
with topA:
    if st.button("🧹 Oyunu Sıfırla"):
        st.session_state.clear()
        st.success("Sıfırlandı.")
        st.rerun()
with topB:
    st.caption("Seed (ders için sabit):")
    new_seed = st.number_input(" ", value=int(st.session_state.seed), step=1, label_visibility="collapsed")
    if new_seed != st.session_state.seed:
        st.session_state.seed = int(new_seed)
        st.info("Seed güncellendi (gelecek turların sonuç dizisi değişir).")
with topC:
    st.caption("Not: Kod güncellemesi sonrası hata olursa 'Oyunu Sıfırla'ya basın.")

left, right = st.columns([2.2, 1])

# =========================
# SOL: Oyun alanı
# =========================
with left:
    name = st.text_input("Oyuncu Adı (takma isim)", placeholder="örn. T3_Ayşe / Mehmet / Takım-4")
    if not name:
        st.stop()

    pl = get_player(name)

    # Senaryo kapısı (zorunlu okuma)
    if not pl["scenario_ok"]:
        st.subheader("📌 Oyun Senaryosu (1 dakika)")
        st.markdown(
            """
### 🌍 Finansal Sistem Olmadan Bir Ekonomi

Bu oyunda yeni kurulmuş bir ekonomide faaliyet gösteriyorsunuz.

- **Başlangıç sermayeniz:** 1.000.000 TL  
- **Süre:** 6 tur  
- Ekonomide **belirsizlik** var.  
- Zaman zaman **likidite ihtiyacı** doğabilir (yatırımı zararına bozma).  
- **4. turda makro bir kriz** yaşanacaktır.

**Tur 1–2:** Finansal kurum yok → yalnızca **Direct Investment** (tekil risk)  
**Tur 3+:** **Mevduat** ve **Banka aracılığıyla yatırım** devreye girer (maliyet/spread karşılığında istikrar)

🎯 Amaç:  
**Finansal kurumlar sadece maliyet mi üretir, yoksa risk ve likiditeyi yöneterek istikrar mı sağlar?**
            """
        )
        if st.button("✅ Senaryoyu okudum, oyuna başla"):
            pl["scenario_ok"] = True
            st.rerun()
        st.stop()

    # Tur bilgisi
    turn = int(pl["turn"])
    if turn > CFG["N_TURNS"]:
        st.success("✅ Oyun bitti. Sağdaki panelden 'finansın katkısı' ve lider tablosunu inceleyin.")
    else:
        st.subheader(f"Tur {turn} / {CFG['N_TURNS']}")
        st.write(NEWS.get(turn, ""))

        # Küçük durum çubuğu
        progress = (turn - 1) / CFG["N_TURNS"]
        st.progress(progress)

        st.metric("Mevcut Servet (TL)", f"{pl['wealth']:,.0f}".replace(",", "."))

        # Seçenekler (tur 1-2 kısıt)
        options = ["Direct Investment"]
        if turn >= 3:
            options = ["Direct Investment", "Deposit", "Intermediated Investment (Banka)"]

        choice = st.radio("Seçiminiz:", options, horizontal=True)

        with st.expander("Seçenekler (net özet)", expanded=False):
            st.markdown(
                f"""
- **Direct Investment:** Yüksek risk; başarılıysa yüksek getiri, başarısızsa sert kayıp.  
  Likidite ihtiyacı gelirse ekstra maliyet: **-%{CFG['LIQ_COST']*100:.0f}** (zararına bozdurma).

- **Deposit (Mevduat):** Daha istikrarlı, daha likit; getiri sınırlı (**%{CFG['R_DEPOSIT']*100:.0f}**).  
  Krizde küçük negatif etki olabilir (güvenli liman ama tamamen risksiz değil).

- **Intermediated Investment (Banka):** Aracılık maliyeti (spread/komisyon): **%{CFG['BANK_FEE']*100:.0f}**.  
  Karşılığında getiriler genelde daha istikrarlı olur (risk yönetimi + aracılık).
                """
            )

        if st.button("✅ Kararı Onayla ve Sonucu Gör"):
            rng = rng_for(name, turn)
            state = draw_state(rng, turn)

            # Bu tur tüm seçeneklerin getirileri (aynı durum üzerinden)
            all_choices = ["Direct Investment", "Deposit", "Intermediated Investment (Banka)"] if turn >= 3 else ["Direct Investment"]
            alt_returns = {}
            alt_components = {}
            for ch in all_choices:
                r, comp = option_return(ch, state, turn)
                alt_returns[ch] = r
                alt_components[ch] = comp

            # Seçilen seçenek
            total_r = alt_returns[choice]
            comp_dict = alt_components[choice]

            # Servet güncelle
            old_w = float(pl["wealth"])
            new_w = old_w * (1.0 + float(total_r))
            pl["wealth"] = new_w

            # Karşı-olgusal (finansın katkısı): Aynı turda "Direct" ile fark
            direct_w = old_w * (1.0 + float(alt_returns["Direct Investment"]))
            gain_vs_direct = max(0.0, new_w - direct_w)
            pl["counterfactual_gain"] += gain_vs_direct

            # Log
            pl["log"].append({
                "Turn": turn,
                "Choice": choice,
                "TotalReturn": float(total_r),
                "Wealth": float(new_w),
                "Crisis": bool(state["crisis"]),
                "LiquidityShock": bool(state["liq"]),
                "DirectSuccess": bool(state["direct_success"]),
                "DirectIfWealth": float(direct_w),
                "GainVsDirect": float(gain_vs_direct),
                "Comp_Temel": float(comp_dict["Temel getiri"]),
                "Comp_Fee": float(comp_dict["Aracılık maliyeti (spread/komisyon)"]),
                "Comp_Liq": float(comp_dict["Likidite ihtiyacı maliyeti"]),
                "Comp_Crisis": float(comp_dict["Makro kriz etkisi"]),
            })

            st.success(f"Toplam Getiri: %{total_r*100:.2f} | Yeni Servet: {new_w:,.0f} TL".replace(",", "."))

            # Durum açıklaması (çok net)
            st.markdown("### Bu tur ekonomide ne oldu?")
            bullet = []
            bullet.append("Makro kriz var." if state["crisis"] else "Makro kriz yok.")
            bullet.append("Likidite ihtiyacı (acil nakit) oluştu." if state["liq"] else "Likidite ihtiyacı oluşmadı.")
            bullet.append("Direct yatırım 'başarılı' senaryodaydı." if state["direct_success"] else "Direct yatırım 'başarısız' senaryodaydı.")
            st.write("- " + "\n- ".join(bullet))

            # Bileşenler tablosu
            st.markdown("### Getiri nasıl oluştu? (bileşenler)")
            comp_df = pd.DataFrame(
                [{"Bileşen": k, "Etki (%)": v * 100} for k, v in comp_dict.items()]
            )
            st.dataframe(comp_df, use_container_width=True, hide_index=True)

            # Karşılaştırma paneli: aynı turda tüm seçeneklerin sonucu
            st.markdown("### Aynı turda diğer seçeneklerle kıyas (finansın katkısı burada görünür)")
            compare = []
            for ch, r in alt_returns.items():
                w = old_w * (1.0 + float(r))
                compare.append({"Seçenek": ch, "Getiri (%)": float(r) * 100, "Tur Sonu Servet (TL)": w})
            cmp_df = pd.DataFrame(compare).sort_values("Tur Sonu Servet (TL)", ascending=False)
            st.dataframe(cmp_df, use_container_width=True, hide_index=True)

            st.caption(
                "Eğitici mesaj: Banka/mevduat seçeneği çoğu zaman 'en yüksek getiri' için değil, "
                "'kötü senaryolarda düşüşü sınırlamak' ve 'likidite maliyetini azaltmak' için tercih edilir."
            )

            # Tur ilerlet
            pl["turn"] = turn + 1
            st.rerun()

    # Kişisel geçmiş + grafik
    if pl["log"]:
        st.markdown("## Tur Geçmişi (Kişisel)")
        df = pd.DataFrame(pl["log"])
        df_show = df[["Turn","Choice","TotalReturn","Wealth","Crisis","LiquidityShock","GainVsDirect"]].copy()
        df_show["Getiri (%)"] = df_show["TotalReturn"] * 100
        df_show["Servet (TL)"] = df_show["Wealth"]
        df_show["Direct'e göre kazanım (TL)"] = df_show["GainVsDirect"]
        st.dataframe(df_show[["Turn","Choice","Getiri (%)","Crisis","LiquidityShock","Servet (TL)","Direct'e göre kazanım (TL)"]],
                     use_container_width=True, hide_index=True)

        st.markdown("### Servet Zaman Serisi")
        chart_df = df[["Turn","Wealth"]].copy()
        chart_df = chart_df.rename(columns={"Turn":"Tur", "Wealth":"Servet"})
        st.line_chart(chart_df.set_index("Tur"))

# =========================
# SAĞ: Öğrenme paneli + sınıf özeti + lider
# =========================
with right:
    if "players" in st.session_state and len(st.session_state.players) > 0:
        # name yoksa stop olmuştu; burada güvenli olsun
        if "name" in locals() and name:
            pl = get_player(name)

            st.subheader("🎓 Öğrenme Paneli")
            st.metric("VaR %5 (Getiri)", f"{var5(pl)*100:.2f}%")
            st.metric("Skor", f"{score(pl):,.0f}".replace(",", "."))
            st.metric("Finansın katkısı (birikimli, Direct'e göre)", f"{pl['counterfactual_gain']:,.0f} TL".replace(",", "."))

            st.caption(
                "Bu 'katkı' göstergesi şunu ölçer: Aynı turda Direct seçseydiniz oluşacak servete göre, "
                "mevduat/banka seçimlerinizin ne kadar 'koruma' sağladığını (öğretici amaçla) toplar."
            )

        st.divider()
        st.subheader("📊 Sınıf Özeti (bu turda ne seçiliyor?)")
        # Her oyuncunun mevcut turunu tahmini: oyuncu kaç tur oynadıysa sonraki turda sayılır
        # Basit yaklaşım: son log tur + 1 = current turn
        dist = {}
        for pname, p in st.session_state.players.items():
            p = migrate_player(p)
            if p["log"]:
                current_t = min(p["log"][-1]["Turn"] + 1, CFG["N_TURNS"])
            else:
                current_t = 1
            # oyuncu bitirdiyse sayma
            if current_t > CFG["N_TURNS"]:
                continue
            dist.setdefault(current_t, {"Direct Investment":0, "Deposit":0, "Intermediated Investment (Banka)":0, "Players":0})
            dist[current_t]["Players"] += 1
            # o tur için seçim varsa say
            choices_in_turn = [rec["Choice"] for rec in p["log"] if rec["Turn"] == current_t]
            if choices_in_turn:
                dist[current_t][choices_in_turn[0]] += 1

        if dist:
            # En çok oyuncunun olduğu turu göster
            target_turn = sorted(dist.keys(), key=lambda t: dist[t]["Players"], reverse=True)[0]
            d = dist[target_turn]
            st.caption(f"En yoğun tur: Tur {target_turn} (aktif oyuncu: {d['Players']})")
            class_df = pd.DataFrame([{
                "Tur": target_turn,
                "Direct Investment": d["Direct Investment"],
                "Deposit": d["Deposit"],
                "Intermediated Investment (Banka)": d["Intermediated Investment (Banka)"],
            }])
            st.dataframe(class_df, use_container_width=True, hide_index=True)
        else:
            st.caption("Henüz yeterli veri yok.")

        st.divider()
        st.subheader("🏆 Lider Tablosu")
        rows = []
        for pname, p in st.session_state.players.items():
            p = migrate_player(p)
            # zarar tur sayısı
            loss_turns = 0
            rets = []
            for rec in p["log"]:
                rets.append(rec["TotalReturn"])
                if rec["TotalReturn"] < 0:
                    loss_turns += 1
            rows.append({
                "Oyuncu": pname,
                "Oynanan Tur": len(p["log"]),
                "Servet (TL)": p["wealth"],
                "Zarar Tur": loss_turns,
                "VaR %5": (np.percentile(np.array(rets), 5) if rets else 0.0),
                "Skor": score(p),
            })

        lb = pd.DataFrame(rows).sort_values("Skor", ascending=False)
        lb["Servet (TL)"] = lb["Servet (TL)"].round(0)
        lb["VaR %5"] = (lb["VaR %5"]*100).round(2).astype(str) + "%"
        lb["Skor"] = lb["Skor"].round(0)
        st.dataframe(lb, use_container_width=True, hide_index=True)

    else:
        st.caption("Oyuncu yok. Sol taraftan bir isim girip başlayın.")
