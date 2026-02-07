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

    # Kredi faizi (aylık) - bankacılık açılınca borç mümkündür
    "LOAN_RATE": 0.025,  # %2.5 / ay
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

def can_borrow(month: int) -> bool:
    return month >= 4  # banka ve sonrası

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
            "finished": False,
            "defaulted": False,
            "income": None,
            "fixed": None,
            "debt": 0.0,
            "holdings": {k: 0.0 for k in ASSETS},
            "log": []
        }
    for k in ASSETS:
        st.session_state.players[name]["holdings"].setdefault(k, 0.0)
    st.session_state.players[name].setdefault("debt", 0.0)
    st.session_state.players[name].setdefault("finished", False)
    st.session_state.players[name].setdefault("defaulted", False)
    return st.session_state.players[name]

def total_investments(p):
    return float(sum(v for k, v in p["holdings"].items() if k != "cash"))

def net_wealth(p):
    return float(p["holdings"]["cash"] + total_investments(p) - float(p["debt"]))

def rng_for(name, month):
    return np.random.default_rng((hash(name) % 10000) + month * 1000 + st.session_state.seed)

# =========================
# UI
# =========================
st.title("🎮 Finansal Piyasalar Neden Var? (1. Hafta Oyunu)")
st.caption(
    "Kural: Gider+Harcama nakit+geliri aşarsa (Ay 4+) otomatik borçlanırsınız. "
    "Ay 1–3'te borç yok: ödeme aksarsa temerrüt. Ay sonunda (Ay 4+) borç geri ödemesi yapılabilir."
)

top1, top2 = st.columns([1, 3])
with top1:
    if st.button("🧹 Oyunu Sıfırla"):
        st.session_state.clear()
        st.success("Sıfırlandı.")
        st.rerun()
with top2:
    st.caption("Not: Ürün aşamaları ve enflasyon sabit kurallarla ilerler (ders içi karşılaştırma için).")

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
    if fixed > income:
        st.warning("Sabit gider geliri aşıyor. (Ay 1–3 borç yok → temerrüt riski artar.)")
    if st.button("Başla"):
        p["income"] = float(income)
        p["fixed"] = float(fixed)
        st.rerun()
    st.stop()

# Oyun bittiyse
if p.get("finished", False):
    if p.get("defaulted", False):
        st.error("⛔ Oyun bitti: Kurum yokken ödeme aksadı (temerrüt).")
    else:
        st.success("✅ Oyun bitti (12. ay tamamlandı).")

    st.metric("Toplam Nakit", f"{p['holdings']['cash']:,.0f} TL".replace(",", "."))
    st.metric("Toplam Yatırım", f"{total_investments(p):,.0f} TL".replace(",", "."))
    st.metric("Toplam Borç", f"{p['debt']:,.0f} TL".replace(",", "."))
    st.metric("Toplam Servet (Net)", f"{net_wealth(p):,.0f} TL".replace(",", "."))

    if p["log"]:
        st.divider()
        st.subheader("📒 Geçmiş (Sade Özet)")
        df = pd.DataFrame(p["log"]).copy()
        simple_df = df[[
            "Ay","Aşama","Gelir(TL)","ToplamGider(TL)","Tasarruf(TL)","YatırımaGiden(TL)",
            "EnflasyonOranı(%)","EnflasyonTutarı(TL)",
            "BorçÖdeme(TL)",
            "DönemSonuNakit(TL)","DönemSonuYatırım(TL)","DönemSonuBorç(TL)","ToplamServet(TL)"
        ]].copy()
        money_cols = [c for c in simple_df.columns if "(TL)" in c]
        for c in money_cols:
            simple_df[c] = simple_df[c].astype(float).round(0)
        simple_df["EnflasyonOranı(%)"] = simple_df["EnflasyonOranı(%)"].astype(float).round(2)
        st.dataframe(simple_df, use_container_width=True, hide_index=True)
        st.subheader("📈 Toplam Servet (Net) Zaman Serisi")
        st.line_chart(df.set_index("Ay")["ToplamServet(TL)"])
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
    st.info("Aşama 1 (Ay 1–3): Finansal kurum yok → borç yok.")
elif month <= 5:
    st.success("Aşama 2 (Ay 4–5): Bankacılık devrede → mevduat + borç mümkün.")
elif month <= 7:
    st.success("Aşama 3 (Ay 6–7): Korunma → döviz/metal.")
else:
    st.success("Aşama 4 (Ay 8–12): Piyasa → hisse/kripto.")

if month == CFG["CRISIS_MONTH"]:
    st.warning("🚨 Makro kriz ayı: bazı varlıklar sert tepki verir.")

st.metric("Toplam Nakit", f"{p['holdings']['cash']:,.0f} TL".replace(",", "."))
st.metric("Toplam Yatırım", f"{total_investments(p):,.0f} TL".replace(",", "."))
st.metric("Toplam Borç", f"{p['debt']:,.0f} TL".replace(",", "."))
st.metric("Toplam Servet (Net)", f"{net_wealth(p):,.0f} TL".replace(",", "."))

st.write("### Mevcut Varlıklarınız (TL)")
cur = pd.DataFrame([{"Varlık": ASSETS[k], "Tutar (TL)": p["holdings"][k]} for k in ASSETS])
cur = pd.concat([cur, pd.DataFrame([{"Varlık": "Borç (Kredi)", "Tutar (TL)": -float(p["debt"])}])], ignore_index=True)
st.dataframe(cur, use_container_width=True, hide_index=True)

# =========================
# 1) BÜTÇE (ÖNİZLEME)
# =========================
st.divider()
st.subheader("1) Bu Ay Bütçe (Önizleme)")

income = float(p["income"])
fixed = float(p["fixed"])

available_without_borrow = p["holdings"]["cash"] + income
extra_max = int(max(0.0, available_without_borrow - fixed)) if not can_borrow(month) else int(income * 3)

extra = st.number_input("Ek Harcama", 0, max(0, extra_max), min(5000, max(0, extra_max)), 1000)

total_exp = fixed + float(extra)
saving = max(income - total_exp, 0.0)

st.write(f"Gelir: **{income:,.0f} TL**".replace(",", "."))
st.write(f"Toplam gider: **{total_exp:,.0f} TL**".replace(",", "."))
st.write(f"Bu ay tasarruf (net): **{saving:,.0f} TL**".replace(",", "."))

if not can_borrow(month) and total_exp > available_without_borrow:
    st.error("Ay 1–3'te borç yok. Bu bütçe nakit+geliri aşıyor → temerrüt olur. Ek harcamayı düşürün.")

# =========================
# 2) YATIRIM KARARI (ÖNİZLEME)
# =========================
st.divider()
st.subheader("2) Bu Ayın Tasarrufunu Yatırıma Dönüştür (Önizleme)")

alloc = {}
alloc_sum = 0.0

if saving <= 0:
    st.caption("Bu ay tasarruf yok → yatırım yapılamaz.")
elif not investable:
    st.caption("Bu ay yatırım ürünü yok → tasarruf nakitte kalır.")
else:
    for k in investable:
        c1, c2, c3 = st.columns([2.8, 1.2, 0.6])
        with c1:
            st.write(ASSETS[k])
        with c2:
            alloc[k] = st.number_input(
                f"{k}_pct",
                min_value=0, max_value=100, value=0, step=5,
                label_visibility="collapsed"
            )
        with c3:
            st.write("%")
    alloc_sum = float(sum(alloc.values()))
    st.write(f"Toplam (yatırım ürünleri): **{int(alloc_sum)} %**")
    if alloc_sum > 100:
        st.warning("Toplam 100'ü geçti. Ay sonunda otomatik normalize edilecek.")

# =========================
# 3) BORÇ GERİ ÖDEME (ÖNİZLEME) - SADE
# =========================
st.divider()
st.subheader("3) Borç Geri Ödeme (Ay Sonu)")

if not can_borrow(month):
    st.caption("Bu aşamada borç/geri ödeme yok (Ay 1–3).")
    repay_pct = 0
else:
    if p["debt"] <= 0:
        st.caption("Şu an borcunuz yok.")
        repay_pct = 0
    else:
        repay_pct = st.slider("Bu ay borcun ne kadarını ödemek istersiniz? (%)", 0, 100, 20, 5)
        st.caption("Not: Ödeme sadece ay sonunda elde kalan nakitten yapılır. Nakit yetmezse otomatik olarak 'nakit kadar' ödenir.")

# =========================
# AYI TAMAMLA
# =========================
btn_label = "✅ Ayı Tamamla" if month < CFG["MONTHS"] else "✅ 12. Ayı Tamamla ve Bitir"
if st.button(btn_label):
    rng = rng_for(name, month)

    # 0) Gelir ekle
    p["holdings"]["cash"] += income

    # 1) Giderleri öde: nakit yetmezse borç/temerrüt
    p["holdings"]["cash"] -= total_exp

    if p["holdings"]["cash"] < 0:
        deficit = -float(p["holdings"]["cash"])

        if not can_borrow(month):
            # kurum yok: borç yok -> temerrüt
            p["holdings"]["cash"] = 0.0
            p["defaulted"] = True
            p["finished"] = True

            # log (temerrütte ay sonu mekanikleri uygulanmasın)
            end_cash = float(p["holdings"]["cash"])
            end_invest = total_investments(p)
            end_debt = float(p["debt"])
            end_total = end_cash + end_invest - end_debt

            p["log"].append({
                "Ay": month,
                "Aşama": stage_label(month),
                "Gelir(TL)": income,
                "ToplamGider(TL)": total_exp,
                "Tasarruf(TL)": saving,
                "YatırımaGiden(TL)": 0.0,
                "EnflasyonOranı(%)": float(CFG["INFLATION_M"]) * 100,
                "EnflasyonTutarı(TL)": 0.0,
                "BorçÖdeme(TL)": 0.0,
                "DönemSonuNakit(TL)": end_cash,
                "DönemSonuYatırım(TL)": end_invest,
                "DönemSonuBorç(TL)": end_debt,
                "ToplamServet(TL)": end_total,
            })
            st.rerun()
        else:
            # banka: otomatik borçlan
            p["debt"] += deficit
            p["holdings"]["cash"] = 0.0

    # 2) Yatırım transferi (tasarruf üzerinden)
    if saving <= 0 or (not investable) or alloc_sum <= 0:
        invested_amount = 0.0
        alloc_adj = {}
    else:
        invested_amount = saving if alloc_sum >= 100 else saving * (alloc_sum / 100.0)
        alloc_adj = dict(alloc)
        if alloc_sum > 100:
            alloc_adj = {k: (v / alloc_sum) * 100 for k, v in alloc.items()}

        for k, pct in alloc_adj.items():
            invest_amt = saving * (pct / 100.0)
            p["holdings"][k] += invest_amt
            p["holdings"]["cash"] -= invest_amt

        # nakit negatife düşerse: bankada borçlan, kurum yoksa temerrüt
        if p["holdings"]["cash"] < 0:
            deficit2 = -float(p["holdings"]["cash"])
            if can_borrow(month):
                p["debt"] += deficit2
                p["holdings"]["cash"] = 0.0
            else:
                p["holdings"]["cash"] = 0.0
                p["defaulted"] = True
                p["finished"] = True
                st.rerun()

    # 3) Kurum yokken nakit kayıp riski (Ay 1-3)
    if month <= 3 and p["holdings"]["cash"] > 0:
        if rng.random() < CFG["CASH_LOSS_PROB"]:
            p["holdings"]["cash"] -= p["holdings"]["cash"] * CFG["CASH_LOSS_SEV"]

    # 4) Getiriler
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

    # 5) Borç faizi (bankacılık varsa)
    if can_borrow(month) and p["debt"] > 0:
        p["debt"] *= (1.0 + float(CFG["LOAN_RATE"]))

    # 6) Enflasyon: nakit aşınması
    infl_rate = float(CFG["INFLATION_M"])
    inflation_amt = p["holdings"]["cash"] * infl_rate
    p["holdings"]["cash"] *= (1.0 - infl_rate)

    # 7) BORÇ GERİ ÖDEME (AY SONU)
    repay_amt = 0.0
    if can_borrow(month) and p["debt"] > 0:
        target = p["debt"] * (float(repay_pct) / 100.0)
        repay_amt = min(float(p["holdings"]["cash"]), float(target))
        p["holdings"]["cash"] -= repay_amt
        p["debt"] -= repay_amt
        if p["debt"] < 0:
            p["debt"] = 0.0

    # 8) Dönem sonu özet
    end_cash = float(p["holdings"]["cash"])
    end_invest = total_investments(p)
    end_debt = float(p["debt"])
    end_total = end_cash + end_invest - end_debt

    # 9) Log
    p["log"].append({
        "Ay": month,
        "Aşama": stage_label(month),
        "Gelir(TL)": income,
        "ToplamGider(TL)": total_exp,
        "Tasarruf(TL)": saving,
        "YatırımaGiden(TL)": invested_amount,
        "EnflasyonOranı(%)": infl_rate * 100,
        "EnflasyonTutarı(TL)": inflation_amt,
        "BorçÖdeme(TL)": repay_amt,
        "DönemSonuNakit(TL)": end_cash,
        "DönemSonuYatırım(TL)": end_invest,
        "DönemSonuBorç(TL)": end_debt,
        "ToplamServet(TL)": end_total,
    })

    # 10) Ay ilerlet / bitir
    if month >= CFG["MONTHS"]:
        p["finished"] = True
    else:
        p["month"] += 1

    st.rerun()

# =========================
# GEÇMİŞ TABLOSU (SADE)
# =========================
if p["log"]:
    st.divider()
    st.subheader("📒 Geçmiş (Sade Özet)")

    df = pd.DataFrame(p["log"]).copy()
    simple_df = df[[
        "Ay","Aşama","Gelir(TL)","ToplamGider(TL)","Tasarruf(TL)","YatırımaGiden(TL)",
        "EnflasyonOranı(%)","EnflasyonTutarı(TL)","BorçÖdeme(TL)",
        "DönemSonuNakit(TL)","DönemSonuYatırım(TL)","DönemSonuBorç(TL)","ToplamServet(TL)"
    ]].copy()

    money_cols = [c for c in simple_df.columns if "(TL)" in c]
    for c in money_cols:
        simple_df[c] = simple_df[c].astype(float).round(0)
    simple_df["EnflasyonOranı(%)"] = simple_df["EnflasyonOranı(%)"].astype(float).round(2)

    st.dataframe(simple_df, use_container_width=True, hide_index=True)

    st.subheader("📈 Toplam Servet (Net) Zaman Serisi")
    st.line_chart(df.set_index("Ay")["ToplamServet(TL)"])

# =========================
# LİDER TABLOSU
# =========================
st.divider()
st.subheader("🏆 Lider Tablosu")
rows = []
for pname, pp in st.session_state.players.items():
    ay_sayisi = CFG["MONTHS"] if pp.get("finished", False) else max(pp["month"] - 1, 0)
    rows.append({
        "Oyuncu": pname,
        "Ay": ay_sayisi,
        "Servet(Net)": net_wealth(pp),
        "Borç": float(pp.get("debt", 0.0)),
    })
lb = pd.DataFrame(rows).sort_values("Servet(Net)", ascending=False)
lb["Servet(Net)"] = lb["Servet(Net)"].round(0)
lb["Borç"] = lb["Borç"].round(0)
st.dataframe(lb, use_container_width=True, hide_index=True)
