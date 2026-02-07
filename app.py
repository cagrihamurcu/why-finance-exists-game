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

    # Mevduat
    "DD_RATE": 0.003,   # vadesiz
    "TD_RATE": 0.010,   # vadeli

    # Riskli varlıklar
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
    Ay 6-7 : koruma -> fx, pm (+ dd, td)
    Ay 8-12: piyasa -> eq, cr (+ hepsi)
    """
    if month <= 3:
        return ["cash"]
    if month <= 5:
        return ["cash", "dd", "td"]
    if month <= 7:
        return ["cash", "dd", "td", "fx", "pm"]
    return ["cash", "dd", "td", "fx", "pm", "eq", "cr"]

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
    return st.session_state.players[name]

def total_wealth(p):
    return float(sum(p["holdings"].values()))

def rng_for(name, month):
    return np.random.default_rng((hash(name) % 10000) + month * 1000 + st.session_state.seed)

# =========================
# UI
# =========================
st.title("🎮 Finansal Piyasalar Neden Var? (1. Hafta Oyunu)")
st.caption("Gelir → gider → kalan = tasarruf. Asıl karar: tasarrufu hangi yatırım aracına dönüştüreceksiniz? Ürünler ay ay açılır.")

top1, top2 = st.columns([1, 3])
with top1:
    if st.button("🧹 Oyunu Sıfırla"):
        st.session_state.clear()
        st.success("Sıfırlandı.")
        st.rerun()
with top2:
    st.caption("Not: Sınıfta aynı seed ile çalışmak için seed sabittir. İsterseniz yukarıdan değiştirilebilir yapılır.")

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
st.subheader(f"📅 Ay {month} / {CFG['MONTHS']}")

st.progress((month - 1) / CFG["MONTHS"])

opened = open_assets_by_month(month)

# Aşama mesajı
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

st.metric("Toplam Servet", f"{total_wealth(p):,.0f} TL")

# Mevcut varlıklar
st.write("### Mevcut Varlıklarınız (TL)")
cur = pd.DataFrame(
    [{"Varlık": ASSETS[k], "Tutar (TL)": v} for k, v in p["holdings"].items() if abs(v) > 1e-6]
)
if cur.empty:
    st.caption("Henüz varlık yok.")
else:
    st.dataframe(cur, use_container_width=True, hide_index=True)

# =========================
# BÜTÇE
# =========================
st.divider()
st.subheader("1) Bu Ay Bütçe")

income = p["income"]
fixed = p["fixed"]
extra = st.number_input("Ek Harcama", 0, int(income), 5000, 1000)

# Gelir ekle
p["holdings"]["cash"] += income

# Gider düş
total_exp = fixed + extra
p["holdings"]["cash"] -= total_exp

if p["holdings"]["cash"] < 0:
    st.error("Nakit açığı! Bu, finansal kırılganlığı gösterir (gider > gelir).")
    p["holdings"]["cash"] = 0.0

# Tasarruf = kalan
saving = float(p["holdings"]["cash"])
st.write(f"Bu ay tasarruf edilen tutar (kalan nakit): **{saving:,.0f} TL**")

# =========================
# YATIRIM KARARI
# =========================
st.divider()
st.subheader("2) Tasarrufu Yatırıma Dönüştür (bu ay)")

# Nakit yüzdesi otomatik "kalan" olacak: kullanıcı sadece açılan ürünlere yüzdelik dağıtım girsin
alloc = {}
alloc_sum = 0

investable = [k for k in opened if k != "cash"]  # cash hariç ürünler

if not investable:
    st.caption("Bu ay yatırım ürünü yok → tasarruf nakitte kalacak.")
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

    alloc_sum = sum(alloc.values())
    st.write(f"Toplam (yatırım ürünleri): **{alloc_sum}** %")

    if alloc_sum < 100:
        st.info(f"Kalan **{100-alloc_sum} %** otomatik olarak **Nakit**'te kalacak.")
    elif alloc_sum > 100:
        st.warning("Toplam 100'ü geçti. Oranlar otomatik 100'e ölçeklenecek (normalize).")

# =========================
# AYI ÇALIŞTIR
# =========================
if st.button("✅ Ayı Tamamla"):
    rng = rng_for(name, month)

    # 1) Tasarrufu dağıt (cash'ten diğerlerine aktar)
    if investable and alloc_sum > 0:
        # normalize
        if alloc_sum > 100:
            alloc_adj = {k: (v / alloc_sum) * 100 for k, v in alloc.items()}
        else:
            alloc_adj = dict(alloc)

        # yatırım tutarları
        for k, pct in alloc_adj.items():
            invest_amt = saving * (pct / 100.0)
            p["holdings"][k] += invest_amt
            p["holdings"]["cash"] -= invest_amt

    # 2) Getiriler (ay sonu)
    # Nakit kayıp riski: sadece "kurum yok" aşamasında daha görünür (Ay 1-3)
    cash_loss_amt = 0.0
    if month <= 3:
        if rng.random() < CFG["CASH_LOSS_PROB"] and p["holdings"]["cash"] > 0:
            cash_loss_amt = p["holdings"]["cash"] * CFG["CASH_LOSS_SEV"]
            p["holdings"]["cash"] -= cash_loss_amt

    # Mevduat getirileri (açıldıysa)
    if "dd" in opened:
        p["holdings"]["dd"] *= (1.0 + CFG["DD_RATE"])
    if "td" in opened:
        p["holdings"]["td"] *= (1.0 + CFG["TD_RATE"])

    # Piyasa getirileri (açıldıysa)
    eq_r = cr_r = pm_r = fx_r = np.nan

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

    # 3) Enflasyon etkisi: nakdin satın alma gücü aşınır (öğretici)
    inflation_hit = p["holdings"]["cash"] * CFG["INFLATION_M"]
    p["holdings"]["cash"] *= (1.0 - CFG["INFLATION_M"])

    # 4) Log
    p["log"].append({
        "Ay": month,
        "Aşama": ("1-KurumYok" if month<=3 else "2-Banka" if month<=5 else "3-Korunma" if month<=7 else "4-Piyasa"),
        "Gelir": income,
        "SabitGider": fixed,
        "EkHarcama": float(extra),
        "Tasarruf": saving,
        "NakitKayıp": cash_loss_amt,
        "EnflasyonEtkisi": inflation_hit,
        "HisseGetiri": eq_r,
        "KriptoGetiri": cr_r,
        "MetalGetiri": pm_r,
        "DövizGetiri": fx_r,
        "Servet": total_wealth(p),
    })

    st.success(f"Ay {month} tamamlandı. Yeni servet: {total_wealth(p):,.0f} TL")
    if cash_loss_amt > 0:
        st.warning(f"⚠️ Kurum yokken nakit kaybı: {cash_loss_amt:,.0f} TL")
    st.info(f"Enflasyon nedeniyle nakdin satın alma gücü aşınması (bu ay): ~{inflation_hit:,.0f} TL")

    p["month"] += 1
    st.rerun()

# =========================
# RAPORLAR
# =========================
if p["log"]:
    st.divider()
    st.subheader("📒 Geçmiş (Kişisel)")
    df = pd.DataFrame(p["log"])
    st.dataframe(
        df[["Ay","Aşama","Tasarruf","NakitKayıp","EnflasyonEtkisi","Servet"]],
        use_container_width=True,
        hide_index=True
    )
    st.subheader("📈 Servet Zaman Serisi")
    st.line_chart(df[["Ay","Servet"]].set_index("Ay"))

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
