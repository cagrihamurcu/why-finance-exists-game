import streamlit as st
import numpy as np
import pandas as pd

st.set_page_config(page_title="Finans Neden Var?", layout="wide")

# =========================
# AYARLAR
# =========================
CFG = {
    "MONTHS": 12,

    # ENFLASYON (aylık)
    "INFLATION_M": 0.020,  # %2 / ay

    # Kurum yokken elde nakit riski
    "CASH_LOSS_PROB": 0.05,
    "CASH_LOSS_SEV": 0.10,

    # Mevduat (aylık)
    "DD_RATE": 0.003,   # vadesiz
    "TD_RATE": 0.010,   # vadeli

    # Riskli varlıklar (aylık)
    "EQ_MU": 0.015,
    "EQ_SIG": 0.060,

    "CR_MU": 0.020,
    "CR_SIG": 0.120,

    "PM_MU": 0.008,
    "PM_SIG": 0.030,

    "FX_MU": 0.010,
    "FX_SIG": 0.040,

    # Makro kriz ayı
    "CRISIS_MONTH": 6,
    "CRISIS_EQ": -0.12,
    "CRISIS_CR": -0.20,
    "CRISIS_PM": +0.04,
    "CRISIS_FX": +0.07,
}

ASSETS = {
    "cash": "Nakit",
    "dd": "Vadesiz Mevduat",
    "td": "Vadeli Mevduat",
    "fx": "Döviz",
    "pm": "Kıymetli Metal",
    "eq": "Hisse Senedi",
    "cr": "Kripto",
}

# =========================
# AŞAMALI ÜRÜN AÇILIMI
# =========================
def open_assets_by_month(month: int):
    """
    Ay 1-3 : kurum yok -> sadece cash
    Ay 4-5 : bankacılık -> dd, td
    Ay 6-7 : korunma -> fx, pm (+ dd, td)
    Ay 8-12: piyasa -> eq, cr (+ hepsi)
    """
    if month <= 3:
        return ["cash"]
    if month <= 5:
        return ["cash", "dd", "td"]
    if month <= 7:
        return ["cash", "dd", "td", "fx", "pm"]
    return ["cash", "dd", "td", "fx", "pm", "eq", "cr"]

def stage_label(month: int):
    if month <= 3: return "1-KurumYok"
    if month <= 5: return "2-Banka"
    if month <= 7: return "3-Korunma"
    return "4-Piyasa"

# =========================
# SESSION
# =========================
if "seed" not in st.session_state:
    st.session_state.seed = 20260209

if "players" not in st.session_state:
    st.session_state.players = {}

def get_player(name):
    if name not in st.session_state.players:
        st.session_state.players[name] = {
            "month": 1,
            "income": None,
            "fixed": None,
            "holdings": {k: 0.0 for k in ASSETS},
            "log": []
        }
    for k in ASSETS:
        st.session_state.players[name]["holdings"].setdefault(k, 0.0)
    return st.session_state.players[name]

def total_wealth(p):
    return float(sum(p["holdings"].values()))

def rng_for(name, month):
    return np.random.default_rng((hash(name) % 10000) + month * 1000 + st.session_state.seed)

# =========================
# UI
# =========================
st.title("🎮 Finansal Piyasalar Neden Var? (1. Hafta Oyunu)")
st.caption("Bu sürümde tasarruf, her ay net olarak: Tasarruf = Gelir − (Sabit Gider + Ek Harcama). Geçmiş nakit tasarrufa karışmaz.")

top1, top2 = st.columns([1, 3])
with top1:
    if st.button("🧹 Oyunu Sıfırla"):
        st.session_state.clear()
        st.success("Sıfırlandı.")
        st.rerun()
with top2:
    st.caption("Not: Enflasyon oranı ve ürün aşamaları sabit kurallarla ilerler (ders içi karşılaştırma için).")

name = st.text_input("Oyuncu Adı")
if not name:
    st.stop()

p = get_player(name)

# =========================
# BAŞLANGIÇ
# =========================
if p["income"] is None:
    st.subheader("Başlangıç Bilgileri")
    income = st.number_input("Aylık Gelir", 20000, 500000, 60000, 5000)
    fixed = st.number_input("Sabit Gider", 10000, 400000, 30000, 5000)
    if st.button("Başla"):
        p["income"] = float(income)
        p["fixed"] = float(fixed)
        st.rerun()
    st.stop()

# =========================
# AY PANELİ
# =========================
month = int(p["month"])
opened = open_assets_by_month(month)
investable = [k for k in opened if k != "cash"]

st.subheader(f"📅 Ay {month} / {CFG['MONTHS']}")
st.progress((month - 1) / CFG["MONTHS"])

if month <= 3:
    st.info("Aşama 1 (Ay 1–3): Finansal kurum yok → sadece Nakit. (Enflasyon + nakit kaybı riski)")
elif month <= 5:
    st.success("Aşama 2 (Ay 4–5): Bankacılık devrede → Vadesiz/Vadeli açıldı.")
elif month <= 7:
    st.success("Aşama 3 (Ay 6–7): Korunma araçları devrede → Döviz/Metal açıldı.")
else:
    st.success("Aşama 4 (Ay 8–12): Piyasa araçları devrede → Hisse/Kripto açıldı.")

if month == CFG["CRISIS_MONTH"]:
    st.warning("🚨 Makro kriz ayı: bazı varlıklar sert tepki verir.")

st.metric("Toplam Servet", f"{total_wealth(p):,.0f} TL".replace(",", "."))

# Mevcut varlıklar (tümü)
st.write("### Mevcut Varlıklarınız (TL)")
cur = pd.DataFrame([{"Varlık": ASSETS[k], "Tutar (TL)": p["holdings"][k]} for k in ASSETS])
st.dataframe(cur, use_container_width=True, hide_index=True)

# =========================
# 1) BÜTÇE
# =========================
st.divider()
st.subheader("1) Bu Ay Bütçe (Tasarruf = Gelir − Gider)")

income = p["income"]
fixed = p["fixed"]
extra = st.number_input("Ek Harcama", 0, int(income), 5000, 1000)

total_exp = float(fixed) + float(extra)
saving = max(float(income) - total_exp, 0.0)  # <-- NET TASARRUF TANIMI

st.write(f"Gelir: **{income:,.0f} TL**".replace(",", "."))
st.write(f"Toplam gider: **{total_exp:,.0f} TL** (Sabit + Ek)".replace(",", "."))
st.write(f"Bu ay tasarruf (net): **{saving:,.0f} TL**".replace(",", "."))

# Not: tasarruf kadar para "bu ay" nakde eklenir.
# Gelir ve giderleri nakit akışı olarak simüle etmek için:
# - Gelir nakde eklenir
# - Gider nakitten düşülür
# Bu ayın net tasarrufu nakitte artışa yol açar, ama tasarruf tutarı tanım olarak netten gelir.

# Ay başı durumunu loglamak için kopya
start_holdings = dict(p["holdings"])
start_total = total_wealth(p)

# Nakit akışı (gelir ve gider)
p["holdings"]["cash"] += float(income)
p["holdings"]["cash"] -= total_exp

cashflow_shortfall = 0.0
if p["holdings"]["cash"] < 0:
    cashflow_shortfall = -p["holdings"]["cash"]
    st.error(f"Nakit açığı! (Eksik: {cashflow_shortfall:,.0f} TL)".replace(",", "."))
    p["holdings"]["cash"] = 0.0

# =========================
# 2) YATIRIM KARARI (SADECE BU AYIN TASARRUFU)
# =========================
st.divider()
st.subheader("2) Bu Ayın Tasarrufunu Yatırıma Dönüştür")

alloc = {}
alloc_sum = 0.0
alloc_adj = {}

if saving <= 0:
    st.caption("Bu ay tasarruf yok → yatırım yapılamaz.")
elif not investable:
    st.caption("Bu ay yatırım ürünü yok → tasarruf nakitte kalır.")
else:
    st.caption("Sadece sayı girin. Yan tarafta % görünür. Toplam 100'ü aşarsa otomatik normalize edilir. Kalan otomatik Nakit'te kalır.")
    for k in investable:
        c1, c2, c3 = st.columns([2.8, 1.2, 0.6])
        with c1:
            st.write(ASSETS[k])
        with c2:
            alloc[k] = st.number_input(
                f"{k}_pct",
                min_value=0,
                max_value=100,
                value=0,
                step=5,
                label_visibility="collapsed"
            )
        with c3:
            st.write("%")

    alloc_sum = float(sum(alloc.values()))
    st.write(f"Toplam (yatırım ürünleri): **{int(alloc_sum)} %**")

    if alloc_sum < 100:
        st.info(f"Kalan **{int(100-alloc_sum)} %** otomatik olarak **Nakit**'te kalacak.")
    elif alloc_sum > 100:
        st.warning("Toplam 100'ü geçti. Oranlar otomatik 100'e ölçeklenecek (normalize).")

# =========================
# AYI TAMAMLA
# =========================
if st.button("✅ Ayı Tamamla"):
    rng = rng_for(name, month)

    # --- 1) Bu ayın tasarrufunu dağıt (cash'ten diğerlerine aktar) ---
    # Kritik: sadece SAVING kadar tutar üzerinden yatırım yapıyoruz.
    if saving > 0 and investable and alloc_sum > 0:
        if alloc_sum > 100:
            alloc_adj = {k: (v / alloc_sum) * 100 for k, v in alloc.items()}
        else:
            alloc_adj = dict(alloc)

        for k, pct in alloc_adj.items():
            invest_amt = saving * (pct / 100.0)
            p["holdings"][k] += invest_amt
            p["holdings"]["cash"] -= invest_amt

    # --- 2) Kurum yokken nakit kayıp riski (Ay 1-3) ---
    cash_loss_amt = 0.0
    cash_loss_happened = False
    if month <= 3 and p["holdings"]["cash"] > 0:
        if rng.random() < CFG["CASH_LOSS_PROB"]:
            cash_loss_happened = True
            cash_loss_amt = p["holdings"]["cash"] * CFG["CASH_LOSS_SEV"]
            p["holdings"]["cash"] -= cash_loss_amt

    # --- 3) Ay sonu getiriler ---
    eq_r = cr_r = pm_r = fx_r = np.nan

    if "dd" in opened:
        p["holdings"]["dd"] *= (1.0 + CFG["DD_RATE"])
    if "td" in opened:
        p["holdings"]["td"] *= (1.0 + CFG["TD_RATE"])

    if "eq" in opened:
        eq_r = float(rng.normal(CFG["EQ_MU"], CFG["EQ_SIG"]))
        if month == CFG["CRISIS_MONTH"]:
            eq_r += CFG["CRISIS_EQ"]
        p["holdings"]["eq"] *= (1.0 + eq_r)

    if "cr" in opened:
        cr_r = float(rng.normal(CFG["CR_MU"], CFG["CR_SIG"]))
        if month == CFG["CRISIS_MONTH"]:
            cr_r += CFG["CRISIS_CR"]
        p["holdings"]["cr"] *= (1.0 + cr_r)

    if "pm" in opened:
        pm_r = float(rng.normal(CFG["PM_MU"], CFG["PM_SIG"]))
        if month == CFG["CRISIS_MONTH"]:
            pm_r += CFG["CRISIS_PM"]
        p["holdings"]["pm"] *= (1.0 + pm_r)

    if "fx" in opened:
        fx_r = float(rng.normal(CFG["FX_MU"], CFG["FX_SIG"]))
        if month == CFG["CRISIS_MONTH"]:
            fx_r += CFG["CRISIS_FX"]
        p["holdings"]["fx"] *= (1.0 + fx_r)

    # --- 4) Enflasyon: oran + tutar (nakit aşınması) ---
    infl_rate = float(CFG["INFLATION_M"])
    inflation_amt = p["holdings"]["cash"] * infl_rate
    p["holdings"]["cash"] *= (1.0 - infl_rate)

    # --- 5) Log: TÜM KALEMLER ---
    end_total = total_wealth(p)

    log_row = {
        "Ay": month,
        "Aşama": stage_label(month),

        "Gelir(TL)": income,
        "SabitGider(TL)": fixed,
        "EkHarcama(TL)": float(extra),
        "ToplamGider(TL)": total_exp,
        "NakitAçığı(TL)": cashflow_shortfall,

        "Tasarruf(TL)": saving,

        "EnflasyonOranı(%)": infl_rate * 100,
        "EnflasyonTutarı(TL)": inflation_amt,

        "NakitKayıpOldu": cash_loss_happened,
        "NakitKayıpTutar(TL)": cash_loss_amt,

        # Dağılım yüzdeleri (açık olmayan ürünlerde 0)
        "Dağılım_Vadesiz(%)": float(alloc_adj.get("dd", 0.0)),
        "Dağılım_Vadeli(%)": float(alloc_adj.get("td", 0.0)),
        "Dağılım_Döviz(%)": float(alloc_adj.get("fx", 0.0)),
        "Dağılım_Metal(%)": float(alloc_adj.get("pm", 0.0)),
        "Dağılım_Hisse(%)": float(alloc_adj.get("eq", 0.0)),
        "Dağılım_Kripto(%)": float(alloc_adj.get("cr", 0.0)),

        # Getiriler
        "Getiri_Hisse": eq_r,
        "Getiri_Kripto": cr_r,
        "Getiri_Metal": pm_r,
        "Getiri_Döviz": fx_r,

        # Ay sonu bakiyeleri (tümü)
        "Bakiye_Nakit(TL)": p["holdings"]["cash"],
        "Bakiye_Vadesiz(TL)": p["holdings"]["dd"],
        "Bakiye_Vadeli(TL)": p["holdings"]["td"],
        "Bakiye_Döviz(TL)": p["holdings"]["fx"],
        "Bakiye_Metal(TL)": p["holdings"]["pm"],
        "Bakiye_Hisse(TL)": p["holdings"]["eq"],
        "Bakiye_Kripto(TL)": p["holdings"]["cr"],

        "Servet_Başlangıç(TL)": start_total,
        "Servet_Bitiş(TL)": end_total,
    }

    p["log"].append(log_row)

    st.success(f"Ay {month} tamamlandı. Yeni servet: {end_total:,.0f} TL".replace(",", "."))
    st.info(f"Enflasyon: %{infl_rate*100:.2f} | Nakitten aşınma: {inflation_amt:,.0f} TL".replace(",", "."))
    if cash_loss_happened:
        st.warning(f"⚠️ Kurum yokken nakit kaybı yaşandı: {cash_loss_amt:,.0f} TL".replace(",", "."))

    p["month"] += 1
    st.rerun()

# =========================
# GEÇMİŞ: TÜM KALEMLER
# =========================
if p["log"]:
    st.divider()
    st.subheader("📒 Geçmiş (Tüm Kalemler)")

    df = pd.DataFrame(p["log"])

    # yuvarlama
    money_cols = [c for c in df.columns if "(TL)" in c or "Bakiye_" in c or "Servet_" in c]
    for c in money_cols:
        df[c] = df[c].astype(float).round(2)

    if "EnflasyonOranı(%)" in df.columns:
        df["EnflasyonOranı(%)"] = df["EnflasyonOranı(%)"].round(2)

    pct_cols = [c for c in df.columns if "(%)" in c and c != "EnflasyonOranı(%)"]
    for c in pct_cols:
        df[c] = df[c].round(2)

    st.dataframe(df, use_container_width=True, hide_index=True)

    st.subheader("📈 Servet Zaman Serisi")
    st.line_chart(df[["Ay", "Servet_Bitiş(TL)"]].set_index("Ay"))

# =========================
# LİDER TABLOSU
# =========================
st.divider()
st.subheader("🏆 Lider Tablosu")
rows = []
for pname, pp in st.session_state.players.items():
    rows.append({"Oyuncu": pname, "Ay": pp["month"]-1, "Servet": total_wealth(pp)})
lb = pd.DataFrame(rows).sort_values("Servet", ascending=False)
st.dataframe(lb, use_container_width=True, hide_index=True)
