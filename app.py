import streamlit as st
import numpy as np
import pandas as pd

st.set_page_config(page_title="1. Hafta Oyunu — Finans Neden Var?", layout="wide")

# =========================
# KONFİGÜRASYON
# =========================
CFG = {
    "MONTHS": 12,
    "NO_INSTITUTIONS_UNTIL": 3,   # 1-3: kurum yok, 4+ kurum var

    # Enflasyon (nakit erimesi) — aylık
    "INFLATION_M": 0.020,  # %2

    # Kurum yokken "evde nakit" riski (kayıp/çalınma)
    "CASH_LOSS_PROB": 0.05,   # %5 ihtimal
    "CASH_LOSS_SEV": 0.10,    # olursa %10 kayıp

    # Vadesiz (çok düşük getiri)
    "DD_RATE_M": 0.002,       # %0.2/ay

    # Vadeli (daha yüksek, likidite kısıtı simüle edilir)
    "TD_RATE_M": 0.010,       # %1/ay
    "TD_EARLY_WITHDRAW_PENALTY": 0.015,  # vadeli bozulursa -%1.5 ceza

    # Hisse senedi (aylık beklenen + volatilite)
    "EQ_MU": 0.012,
    "EQ_SIG": 0.055,

    # Kripto (yüksek volatilite)
    "CR_MU": 0.020,
    "CR_SIG": 0.120,

    # Kıymetli metal
    "PM_MU": 0.008,
    "PM_SIG": 0.030,

    # Döviz (kur hareketi)
    "FX_MU": 0.010,
    "FX_SIG": 0.040,

    # Makro kriz ayı (haber + şok)
    "CRISIS_MONTH": 6,
    "CRISIS_EQ_HIT": -0.10,   # hisseye ek darbe
    "CRISIS_CR_HIT": -0.18,   # kriptoya ek darbe
    "CRISIS_FX_BOOST": +0.06, # dövize ek pozitif şok
    "CRISIS_PM_BOOST": +0.03, # metale ek pozitif

    # Skor: "yaşam sürdürülebilirliği" için ceza
    "NEG_CASHFLOW_PENALTY": 150_000.0,  # gideri karşılayamazsa ceza
}

ASSET_LABELS = {
    "cash": "Nakit (elde)",
    "dd": "Vadesiz Mevduat",
    "td": "Vadeli Mevduat",
    "eq": "Hisse Senedi",
    "cr": "Kripto Para",
    "pm": "Kıymetli Metaller",
    "fx": "Döviz",
}

# =========================
# SESSION STATE
# =========================
if "seed" not in st.session_state:
    st.session_state.seed = 20260209

if "players" not in st.session_state:
    st.session_state.players = {}

def migrate_player(pl):
    if "scenario_ok" not in pl: pl["scenario_ok"] = False
    if "month" not in pl: pl["month"] = 1
    if "income" not in pl: pl["income"] = None
    if "fixed_exp" not in pl: pl["fixed_exp"] = None
    if "wealth" not in pl: pl["wealth"] = 0.0
    if "holdings" not in pl:
        pl["holdings"] = {k: 0.0 for k in ASSET_LABELS.keys()}
    if "log" not in pl: pl["log"] = []
    if "penalty" not in pl: pl["penalty"] = 0.0
    return pl

def get_player(name: str):
    if name not in st.session_state.players:
        st.session_state.players[name] = {
            "scenario_ok": False,
            "month": 1,
            "income": None,
            "fixed_exp": None,
            "wealth": 0.0,
            "holdings": {k: 0.0 for k in ASSET_LABELS.keys()},
            "log": [],
            "penalty": 0.0,
        }
    st.session_state.players[name] = migrate_player(st.session_state.players[name])
    return st.session_state.players[name]

def rng_for(name: str, month: int):
    return np.random.default_rng(st.session_state.seed + month * 10_000 + (hash(name) % 10_000))

def institutions_available(month: int):
    return month > CFG["NO_INSTITUTIONS_UNTIL"]

def available_assets(month: int):
    if not institutions_available(month):
        return ["cash"]  # sadece elde nakit
    # Kullanıcıya nakit yüzdesi girdirmiyoruz; kalan otomatik nakit
    return ["dd", "td", "eq", "cr", "pm", "fx"]

def apply_returns(holdings: dict, name: str, month: int):
    """Ay sonunda varlık getirilerini uygular, şokları döndürür."""
    rng = rng_for(name, month)
    crisis = (month == CFG["CRISIS_MONTH"])

    infl = -CFG["INFLATION_M"]

    cash_loss = False
    cash_loss_amt = 0.0
    if not institutions_available(month):
        if rng.random() < CFG["CASH_LOSS_PROB"] and holdings["cash"] > 0:
            cash_loss = True
            cash_loss_amt = holdings["cash"] * CFG["CASH_LOSS_SEV"]
            holdings["cash"] -= cash_loss_amt

    if institutions_available(month):
        holdings["dd"] *= (1.0 + CFG["DD_RATE_M"])
        holdings["td"] *= (1.0 + CFG["TD_RATE_M"])

        eq_r = rng.normal(CFG["EQ_MU"], CFG["EQ_SIG"])
        cr_r = rng.normal(CFG["CR_MU"], CFG["CR_SIG"])
        pm_r = rng.normal(CFG["PM_MU"], CFG["PM_SIG"])
        fx_r = rng.normal(CFG["FX_MU"], CFG["FX_SIG"])

        if crisis:
            eq_r += CFG["CRISIS_EQ_HIT"]
            cr_r += CFG["CRISIS_CR_HIT"]
            fx_r += CFG["CRISIS_FX_BOOST"]
            pm_r += CFG["CRISIS_PM_BOOST"]

        holdings["eq"] *= (1.0 + eq_r)
        holdings["cr"] *= (1.0 + cr_r)
        holdings["pm"] *= (1.0 + pm_r)
        holdings["fx"] *= (1.0 + fx_r)

        shocks = {
            "crisis": crisis,
            "eq_r": eq_r,
            "cr_r": cr_r,
            "pm_r": pm_r,
            "fx_r": fx_r,
            "infl": infl,
            "cash_loss": cash_loss,
            "cash_loss_amt": cash_loss_amt,
        }
    else:
        shocks = {
            "crisis": crisis,
            "infl": infl,
            "cash_loss": cash_loss,
            "cash_loss_amt": cash_loss_amt,
        }

    # Nakit için enflasyon aşınması
    if holdings["cash"] > 0:
        holdings["cash"] *= (1.0 + infl)

    return shocks

def total_wealth(holdings: dict):
    return float(sum(holdings.values()))

def score(pl):
    return pl["wealth"] - pl["penalty"]

# =========================
# UI
# =========================
st.title("🎮 1. Hafta: Neden Finansal Piyasalar ve Kurumlarla İlgilenmekteyiz?")
st.caption("Gelir → Gider → Tasarruf → Yatırım akışı ile finansal kurumların (ürün çeşitliliği, risk yönetimi, likidite) katkısını deneyimlersiniz.")

top1, top2 = st.columns([1, 3])
with top1:
    if st.button("🧹 Oyunu Sıfırla"):
        st.session_state.clear()
        st.success("Sıfırlandı.")
        st.rerun()
with top2:
    st.caption("Kod güncellemesi sonrası hata olursa önce 'Oyunu Sıfırla'ya basın.")

left, right = st.columns([2.2, 1])

with left:
    name = st.text_input("Oyuncu Adı (takma isim)", placeholder="örn. T3_Ayşe / Mehmet / Takım-4")
    if not name:
        st.stop()

    pl = get_player(name)

    # Senaryo kapısı
    if not pl["scenario_ok"]:
        st.subheader("📌 Senaryo (kısa)")
        st.markdown(
            f"""
Siz bir ekonomik birimsiniz. Her ay **gelir elde eder**, **gider öder**, kalanla **tasarruf** eder ve **yatırım** kararı verirsiniz.

- Oyun **{CFG['MONTHS']} ay** sürer.
- **Ay 1–{CFG['NO_INSTITUTIONS_UNTIL']}**: Finansal kurum yok → yalnızca **elde nakit** (enflasyon aşınması + kayıp riski).
- **Ay {CFG['NO_INSTITUTIONS_UNTIL']+1}–{CFG['MONTHS']}**: Finansal kurumlar devreye girer → mevduat + piyasa araçları ile yatırım yapabilirsiniz.
- **Ay {CFG['CRISIS_MONTH']}**: Makro kriz → risk artar, varlıklar farklı tepki verir.

🎯 Amaç: Sadece “en yüksek getiri” değil, **sürdürülebilir bütçe + likidite + risk yönetimi** dengesini kurmak.
            """
        )
        if st.button("✅ Okudum, başla"):
            pl["scenario_ok"] = True
            st.rerun()
        st.stop()

    # Başlangıç ayarları (1 kez)
    if pl["income"] is None:
        st.subheader("1) Başlangıç Ayarları (bir kez)")
        st.write("Aylık gelirinizi ve sabit giderinizi belirleyin.")
        income = st.number_input("Aylık Gelir (TL)", min_value=20_000, max_value=500_000, value=60_000, step=5_000)
        fixed = st.number_input("Aylık Sabit Gider (TL) (kira/fatura vb.)", min_value=10_000, max_value=400_000, value=30_000, step=5_000)
        if st.button("✅ Kaydet ve Oyuna Başla"):
            pl["income"] = float(income)
            pl["fixed_exp"] = float(fixed)
            pl["holdings"] = {k: 0.0 for k in ASSET_LABELS.keys()}
            pl["wealth"] = 0.0
            st.rerun()
        st.stop()

    month = int(pl["month"])
    st.subheader(f"📅 Ay {month} / {CFG['MONTHS']}")

    # Haber bandı
    if month <= CFG["NO_INSTITUTIONS_UNTIL"]:
        st.info("📰 Finansal kurum yok: Sadece elde nakit. Enflasyon aşınması + nakit taşıma riski.")
    elif month == CFG["NO_INSTITUTIONS_UNTIL"] + 1:
        st.success("🏦 Finansal kurumlar devrede: Mevduat + piyasa araçları açıldı.")
    elif month == CFG["CRISIS_MONTH"]:
        st.warning("🚨 Makro kriz ayı: Risk artar, varlıklar farklı tepki verir.")
    else:
        st.caption("Bu ay bütçe ve yatırım kararınızı verin.")

    st.progress((month - 1) / CFG["MONTHS"])

    # Mevcut durum
    st.write("### Mevcut Varlık Dağılımınız (TL)")
    h = pl["holdings"]
    cur_df = pd.DataFrame([{"Varlık": ASSET_LABELS[k], "Tutar (TL)": v} for k, v in h.items() if abs(v) > 1e-6])
    if cur_df.empty:
        st.caption("Henüz varlık yok (ilk ay gelirle başlayacaksınız).")
    else:
        st.dataframe(cur_df, use_container_width=True, hide_index=True)

    st.metric("Toplam Servet (TL)", f"{total_wealth(pl['holdings']):,.0f}".replace(",", "."))

    st.divider()
    st.subheader("2) Bu Ay Bütçe Kararı")

    income = pl["income"]
    fixed = pl["fixed_exp"]
    st.write(f"- Aylık geliriniz: **{income:,.0f} TL**".replace(",", "."))
    st.write(f"- Sabit gideriniz: **{fixed:,.0f} TL**".replace(",", "."))

    discretionary = st.number_input("Kendi belirlediğiniz ek harcama (TL)", min_value=0, max_value=int(income), value=5_000, step=1_000)
    saving_rate = st.slider("Bu ay tasarruf oranı (%):", 0, 80, 20, 5)

    st.divider()
    st.subheader("3) Tasarrufu Yatırıma Dağıt (Bu ay)")

    if not institutions_available(month):
        st.caption("Kurum yok → tasarruf otomatik olarak Nakit (elde) kalır.")
        alloc = {}  # boş
        alloc_sum = 0
    else:
        st.caption("Kurumlar var → tasarrufunuzu ürünlere yüzdelik olarak dağıtın. Kalan otomatik Nakit (elde) kalır.")
        assets = available_assets(month)

        alloc = {}
        colA, colB = st.columns(2)
        half = len(assets) // 2
        with colA:
            for k in assets[:half]:
                alloc[k] = st.number_input(f"{ASSET_LABELS[k]} (%)", min_value=0, max_value=100, value=0, step=5)
        with colB:
            for k in assets[half:]:
                alloc[k] = st.number_input(f"{ASSET_LABELS[k]} (%)", min_value=0, max_value=100, value=0, step=5)

        alloc_sum = sum(alloc.values())
        st.write(f"Dağılım toplamı (nakit hariç): **{alloc_sum}%**")

        if alloc_sum < 100:
            st.info(f"Kalan **%{100-alloc_sum:.0f}** otomatik olarak **{ASSET_LABELS['cash']}**'te kalacak.")
        elif alloc_sum > 100:
            st.warning("Dağılım toplamı 100'ü aştı. Oranlar otomatik olarak 100'e ölçeklenecek (normalize).")

    # =========================
    # AYI ÇALIŞTIR
    # =========================
    if st.button("✅ Ayı Çalıştır (Bütçe + Yatırım + Şoklar)"):
        # 1) Gelir ekle (elde nakit)
        pl["holdings"]["cash"] += float(income)

        # 2) Giderleri öde (sabit + discretionary)
        total_exp = float(fixed) + float(discretionary)
        if pl["holdings"]["cash"] >= total_exp:
            pl["holdings"]["cash"] -= total_exp
            cashflow_ok = True
        else:
            cashflow_ok = False
            shortage = total_exp - pl["holdings"]["cash"]
            pl["holdings"]["cash"] = 0.0

            # Kurum varsa varlıklardan zorunlu satış (likit -> daha az likit)
            liquidation_order = ["dd", "fx", "pm", "eq", "cr", "td"]
            if not institutions_available(month):
                liquidation_order = []

            for k in liquidation_order:
                if shortage <= 0:
                    break
                avail = pl["holdings"].get(k, 0.0)
                if avail <= 0:
                    continue
                take = min(avail, shortage)
                pl["holdings"][k] -= take
                shortage -= take

                # vadeli bozma cezası
                if k == "td":
                    pl["penalty"] += take * CFG["TD_EARLY_WITHDRAW_PENALTY"]

            if shortage > 0:
                pl["penalty"] += CFG["NEG_CASHFLOW_PENALTY"]

        # 3) Tasarruf hesapla (harcanmayan nakitten)
        cash_after_exp = pl["holdings"]["cash"]
        save_amt = cash_after_exp * (saving_rate / 100.0)
        pl["holdings"]["cash"] -= save_amt

        # 4) Tasarrufu portföye dağıt (otomatik düzeltme)
        if not institutions_available(month):
            # kurum yok: tasarruf nakitte kalır
            pl["holdings"]["cash"] += save_amt
        else:
            alloc_sum = sum(alloc.values())

            if alloc_sum <= 0:
                # hiç dağıtım yapılmadı: tamamı nakit
                pl["holdings"]["cash"] += save_amt
            else:
                # toplam > 100 ise normalize et
                if alloc_sum > 100:
                    alloc_adj = {k: (pct / alloc_sum) * 100 for k, pct in alloc.items()}
                else:
                    alloc_adj = dict(alloc)

                remaining_pct = max(0.0, 100.0 - sum(alloc_adj.values()))

                for k, pct in alloc_adj.items():
                    pl["holdings"][k] += save_amt * (pct / 100.0)

                if remaining_pct > 0:
                    pl["holdings"]["cash"] += save_amt * (remaining_pct / 100.0)

        # 5) Ay sonu getiriler + şoklar
        shocks = apply_returns(pl["holdings"], name, month)

        # 6) Toplam serveti güncelle
        pl["wealth"] = total_wealth(pl["holdings"])

        # 7) Logla
        rec = {
            "Ay": month,
            "Gelir": income,
            "SabitGider": fixed,
            "EkHarcama": float(discretionary),
            "TasarrufOranı%": saving_rate,
            "TasarrufTutarı": save_amt,
            "NakitAkisiOK": cashflow_ok,
            "CezaToplam": pl["penalty"],
            "Servet": pl["wealth"],
            "Kriz": (month == CFG["CRISIS_MONTH"]),
            "NakitKayıp": shocks.get("cash_loss", False),
            "NakitKayıpTutar": shocks.get("cash_loss_amt", 0.0),
            "HisseGetiri": shocks.get("eq_r", np.nan),
            "KriptoGetiri": shocks.get("cr_r", np.nan),
            "MetalGetiri": shocks.get("pm_r", np.nan),
            "DövizGetiri": shocks.get("fx_r", np.nan),
        }
        pl["log"].append(rec)

        st.success(f"Ay {month} tamamlandı. Güncel servet: {pl['wealth']:,.0f} TL".replace(",", "."))
        if not cashflow_ok:
            st.warning("⚠️ Bu ay nakit akışı problemi yaşadınız (zorunlu satış/ceza). Bu finansın 'likidite' boyutudur.")
        if month == CFG["CRISIS_MONTH"]:
            st.info("📌 Kriz ayı: varlıkların farklı tepkileri 'risk çeşitliliğini' görünür kılar.")

        pl["month"] = month + 1
        st.rerun()

    # Geçmiş
    if pl["log"]:
        st.divider()
        st.subheader("📒 Geçmiş (Kişisel)")
        df = pd.DataFrame(pl["log"])
        df_show = df[["Ay","Gelir","SabitGider","EkHarcama","TasarrufTutarı","NakitAkisiOK","Kriz","Servet","CezaToplam"]].copy()
        st.dataframe(df_show, use_container_width=True, hide_index=True)

        st.subheader("📈 Servet Zaman Serisi")
        chart_df = df[["Ay","Servet"]].copy().set_index("Ay")
        st.line_chart(chart_df)

with right:
    st.subheader("🎓 Öğrenme Paneli")

    if "name" in locals() and name:
        pl = get_player(name)
        st.metric("Ay", f"{min(pl['month'], CFG['MONTHS']+1)} / {CFG['MONTHS']}")
        st.metric("Toplam Servet (TL)", f"{pl['wealth']:,.0f}".replace(",", "."))
        st.metric("Toplam Ceza (TL)", f"{pl['penalty']:,.0f}".replace(",", "."))

        st.divider()
        st.caption("Kurumların katkısı bu oyunda 3 kanaldan görünür:")
        st.write("1) **Ürün çeşitliliği**: risk-getiri seçenekleri açılır.")
        st.write("2) **Likidite yönetimi**: nakit akışı problemi olunca zorunlu satış/ceza mekanizması görünür.")
        st.write("3) **Kriz davranışı**: farklı varlıklar farklı tepki verir (risk dağıtımı).")

    st.divider()
    st.subheader("🏆 Lider Tablosu")
    rows = []
    for pname, p in st.session_state.players.items():
        p = migrate_player(p)
        rows.append({
            "Oyuncu": pname,
            "Ay": min(p["month"]-1, CFG["MONTHS"]),
            "Servet (TL)": p["wealth"],
            "Ceza (TL)": p["penalty"],
            "Skor": score(p),
        })
    if rows:
        lb = pd.DataFrame(rows).sort_values("Skor", ascending=False)
        lb["Servet (TL)"] = lb["Servet (TL)"].round(0)
        lb["Ceza (TL)"] = lb["Ceza (TL)"].round(0)
        lb["Skor"] = lb["Skor"].round(0)
        st.dataframe(lb, use_container_width=True, hide_index=True)
    else:
        st.caption("Henüz oyuncu yok.")
