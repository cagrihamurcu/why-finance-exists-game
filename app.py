import streamlit as st
import numpy as np
import pandas as pd

st.set_page_config(page_title="Finans Neden Var?", layout="wide")

# =========================
# SABİT BAŞLANGIÇ DEĞERLERİ (oyuncu değiştiremez)
# =========================
DEFAULT_MONTHLY_INCOME = 60000   # <- buradan değiştirin
DEFAULT_FIXED_BASE = 30000      # <- buradan değiştirin

# =========================
# AYARLAR
# =========================
CFG = {
    "MONTHS": 12,

    # Enflasyon: %20 ile başlar, her ay +%5 artar (oran olarak)
    "INFL_START": 0.20,
    "INFL_STEP": 0.05,

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

    # Kredi faizi (aylık)
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
    return month >= 4

def inflation_rate_for_month(month: int) -> float:
    # Ay1: 0.20, Ay2: 0.25, Ay3: 0.30, ...
    return float(CFG["INFL_START"] + CFG["INFL_STEP"] * (month - 1))

def inflated_fixed_cost(base_fixed: float, month: int) -> float:
    r = inflation_rate_for_month(month)
    return float(base_fixed * (1.0 + r))

# =========================
# SESSION
# =========================
if "seed" not in st.session_state:
    st.session_state.seed = 20260209
if "players" not in st.session_state:
    st.session_state.players = {}

def get_player(name: str) -> dict:
    if name not in st.session_state.players:
        st.session_state.players[name] = {
            "month": 1,
            "finished": False,
            "defaulted": False,
            "debt": 0.0,
            "holdings": {k: 0.0 for k in ASSETS},
            "log": [],
            # kilitli parametreler
            "income_fixed": float(DEFAULT_MONTHLY_INCOME),
            "fixed_base": float(DEFAULT_FIXED_BASE),
        }
    p = st.session_state.players[name]
    p.setdefault("month", 1)
    p.setdefault("finished", False)
    p.setdefault("defaulted", False)
    p.setdefault("debt", 0.0)
    p.setdefault("holdings", {k: 0.0 for k in ASSETS})
    p.setdefault("log", [])
    p.setdefault("income_fixed", float(DEFAULT_MONTHLY_INCOME))
    p.setdefault("fixed_base", float(DEFAULT_FIXED_BASE))
    for k in ASSETS:
        p["holdings"].setdefault(k, 0.0)
    return p

def total_investments(p: dict) -> float:
    return float(sum(v for k, v in p["holdings"].items() if k != "cash"))

def net_wealth(p: dict) -> float:
    return float(p["holdings"]["cash"] + total_investments(p) - float(p.get("debt", 0.0)))

def rng_for(name: str, month: int):
    return np.random.default_rng((hash(name) % 10000) + month * 1000 + st.session_state.seed)

def fmt_tl(x: float) -> str:
    return f"{x:,.0f} TL".replace(",", ".")

def fmt_pct(x: float) -> str:
    return f"{x*100:.0f}%"

# =========================
# UI
# =========================
st.title("🎮 Finansal Piyasalar Neden Var? (1. Hafta Oyunu)")
st.caption(
    "Kurallar: (i) Ay 1–3 borç yok: gider+harcama nakit+geliri aşarsa temerrüt. "
    "(ii) Ay 4+ borç var: açık otomatik krediyle kapanır. "
    "(iii) Ay sonunda (Ay 4+) borç geri ödeme seçeneği vardır. "
    "(iv) Enflasyon bu oyunda nakitten düşmez; sabit gideri artırır. "
    "(v) Oyun 12. ay sonunda biter."
)

c1, c2 = st.columns([1, 3])
with c1:
    if st.button("🧹 Oyunu Sıfırla"):
        st.session_state.clear()
        st.rerun()
with c2:
    st.caption("Gelir ve baz sabit gider sınıf için standarttır; oyuncular değiştiremez.")

name = st.text_input("Oyuncu Adı")
if not name:
    st.stop()

p = get_player(name)

# =========================
# OYUNCU SIRALAMASI
# =========================
st.subheader("🏆 Oyuncu Sıralaması")
rows = []
for pname, pp in st.session_state.players.items():
    cash = float(pp["holdings"].get("cash", 0.0))
    invest = float(sum(v for k, v in pp["holdings"].items() if k != "cash"))
    debt = float(pp.get("debt", 0.0))
    net = float(cash + invest - debt)

    status = "Devam"
    if pp.get("finished", False) and pp.get("defaulted", False):
        status = "Temerrüt"
    elif pp.get("finished", False):
        status = "Bitti"

    month_done = CFG["MONTHS"] if pp.get("finished", False) else max(int(pp.get("month", 1)) - 1, 0)

    rows.append({
        "Sıra": 0,
        "Oyuncu": pname,
        "Durum": status,
        "Ay": month_done,
        "Servet(Net)": round(net, 0),
        "Borç": round(debt, 0),
    })

lb = pd.DataFrame(rows).sort_values(["Servet(Net)", "Borç"], ascending=[False, True]).reset_index(drop=True)
lb["Sıra"] = lb.index + 1
st.dataframe(lb, use_container_width=True, hide_index=True)

st.divider()

# =========================
# OYUN BİTTİ
# =========================
if p.get("finished", False):
    if p.get("defaulted", False):
        st.error("⛔ Oyun bitti: Ay 1–3 döneminde temerrüt.")
    else:
        st.success("✅ Oyun bitti (12. ay tamamlandı).")

    a, b, c, d = st.columns(4)
    a.metric("Nakit", fmt_tl(p["holdings"]["cash"]))
    b.metric("Yatırım", fmt_tl(total_investments(p)))
    c.metric("Borç", fmt_tl(p["debt"]))
    d.metric("Servet (Net)", fmt_tl(net_wealth(p)))

    if p["log"]:
        st.divider()
        st.subheader("📒 Geçmiş (Sade)")
        df = pd.DataFrame(p["log"]).copy()
        cols = [
            "Ay","Aşama","EnflasyonOranı",
            "Gelir(TL)","SabitGider(TL)","EkHarcama(TL)","Tasarruf(TL)",
            "YatırımaGiden(TL)","BorçÖdeme(TL)",
            "DönemSonuNakit(TL)","DönemSonuYatırım(TL)","DönemSonuBorç(TL)",
            "ToplamServet(TL)"
        ]
        for col in cols:
            if col not in df.columns:
                df[col] = 0.0
        view = df[cols].fillna(0).copy()
        for col in cols:
            if "(TL)" in col:
                view[col] = pd.to_numeric(view[col], errors="coerce").fillna(0).round(0)
        st.dataframe(view, use_container_width=True, hide_index=True)
        st.line_chart(view.set_index("Ay")["ToplamServet(TL)"])
    st.stop()

# =========================
# AY PANELİ
# =========================
month = int(p["month"])
opened = open_assets_by_month(month)
investable = [k for k in opened if k != "cash"]

income = float(p["income_fixed"])
fixed_base = float(p["fixed_base"])
infl = inflation_rate_for_month(month)
fixed_this_month = inflated_fixed_cost(fixed_base, month)

st.subheader(f"📅 Ay {month} / {CFG['MONTHS']} | Aşama: {stage_label(month)}")
st.progress((month - 1) / CFG["MONTHS"])

k1, k2, k3 = st.columns(3)
k1.metric("Enflasyon Oranı", fmt_pct(infl))
k2.metric("Baz Sabit Gider", fmt_tl(fixed_base))
k3.metric("Bu Ay Sabit Gider", fmt_tl(fixed_this_month))

if month == CFG["CRISIS_MONTH"]:
    st.warning("🚨 Kriz ayı: bazı varlıklarda ekstra şok var.")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Nakit", fmt_tl(p["holdings"]["cash"]))
m2.metric("Yatırım", fmt_tl(total_investments(p)))
m3.metric("Borç", fmt_tl(p["debt"]))
m4.metric("Servet (Net)", fmt_tl(net_wealth(p)))

# =========================
# 0) GELİR & SABİT GİDER (kilitli bilgi kutusu)
# =========================
st.divider()
st.subheader("0) Kilitli Parametreler (Değiştirilemez)")
cA, cB = st.columns(2)
cA.info(f"Aylık Gelir: **{fmt_tl(income)}**")
cB.info(f"Bu ay uygulanacak sabit gider: **{fmt_tl(fixed_this_month)}** (enflasyon dahil)")

# =========================
# 1) BÜTÇE
# =========================
st.divider()
st.subheader("1) Bütçe (Bu Ay)")

# borç yokken ekstra harcama üst limiti: (nakit+gelir - sabit gider) kadar
available_without_borrow = p["holdings"]["cash"] + income
extra_max = int(max(0.0, available_without_borrow - fixed_this_month)) if not can_borrow(month) else int(income * 3)

extra_default = min(5000, max(0, extra_max))
extra = st.number_input("Ek Harcama", 0, max(0, extra_max), extra_default, 1000)

total_exp = fixed_this_month + float(extra)
saving = max(income - total_exp, 0.0)

st.write(f"Gelir: **{fmt_tl(income)}**")
st.write(f"Sabit gider (enflasyonlu): **{fmt_tl(fixed_this_month)}**")
st.write(f"Ek harcama: **{fmt_tl(extra)}**")
st.write(f"Toplam gider: **{fmt_tl(total_exp)}**")
st.write(f"Tasarruf: **{fmt_tl(saving)}**")

if (not can_borrow(month)) and (total_exp > available_without_borrow):
    st.error("Ay 1–3'te borç yok. Bu bütçe nakit+geliri aşıyor → temerrüt olur. Ek harcamayı düşürün.")

# =========================
# 2) YATIRIM
# =========================
st.divider()
st.subheader("2) Yatırım (Tasarrufu Dağıt)")

alloc = {}
alloc_sum = 0.0

if saving <= 0:
    st.caption("Tasarruf yok → yatırım yok.")
elif not investable:
    st.caption("Bu ay yatırım ürünü yok → tasarruf nakitte kalır.")
else:
    st.caption("Yüzdeleri girin. Toplam 100'ü aşarsa otomatik normalize edilir.")
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
                label_visibility="collapsed",
            )
        with c3:
            st.write("%")
    alloc_sum = float(sum(alloc.values()))
    st.write(f"Toplam: **{int(alloc_sum)}%**")

# =========================
# 3) BORÇ GERİ ÖDEME
# =========================
st.divider()
st.subheader("3) Borç Geri Ödeme (Ay Sonu)")

repay_pct = 0
if not can_borrow(month):
    st.caption("Ay 1–3: borç yok → geri ödeme yok.")
else:
    if float(p["debt"]) <= 0:
        st.caption("Borcunuz yok.")
    else:
        repay_pct = st.slider("Borcun ne kadarını ödemek istersiniz? (%)", 0, 100, 20, 5)

# =========================
# AYI TAMAMLA
# =========================
btn_label = "✅ Ayı Tamamla" if month < CFG["MONTHS"] else "✅ 12. Ayı Tamamla ve Bitir"

if st.button(btn_label):
    rng = rng_for(name, month)

    invested_amount = 0.0
    repay_amt = 0.0

    # 0) Gelir ekle
    p["holdings"]["cash"] += income

    # 1) Giderleri öde (enflasyonlu sabit gider + ek harcama)
    p["holdings"]["cash"] -= total_exp

    # açık oluştuysa
    if p["holdings"]["cash"] < 0:
        deficit = -float(p["holdings"]["cash"])
        if not can_borrow(month):
            # temerrüt
            p["holdings"]["cash"] = 0.0
            p["defaulted"] = True
            p["finished"] = True

            end_cash = float(p["holdings"]["cash"])
            end_invest = total_investments(p)
            end_debt = float(p["debt"])
            end_total = end_cash + end_invest - end_debt

            p["log"].append({
                "Ay": month,
                "Aşama": stage_label(month),
                "EnflasyonOranı": infl,
                "Gelir(TL)": income,
                "SabitGider(TL)": fixed_this_month,
                "EkHarcama(TL)": float(extra),
                "Tasarruf(TL)": float(saving),
                "YatırımaGiden(TL)": 0.0,
                "BorçÖdeme(TL)": 0.0,
                "DönemSonuNakit(TL)": end_cash,
                "DönemSonuYatırım(TL)": end_invest,
                "DönemSonuBorç(TL)": end_debt,
                "ToplamServet(TL)": end_total,
            })
            st.rerun()
        else:
            # kredi
            p["debt"] += deficit
            p["holdings"]["cash"] = 0.0

    # 2) Yatırım transferi (tasarruf üzerinden)
    if saving > 0 and investable and alloc_sum > 0:
        invested_amount = saving if alloc_sum >= 100 else saving * (alloc_sum / 100.0)

        alloc_adj = dict(alloc)
        if alloc_sum > 100:
            alloc_adj = {k: (v / alloc_sum) * 100 for k, v in alloc.items()}

        for k, pct in alloc_adj.items():
            invest_amt = saving * (float(pct) / 100.0)
            if invest_amt <= 0:
                continue
            p["holdings"][k] += invest_amt
            p["holdings"]["cash"] -= invest_amt

        # yatırım yüzünden nakit negatife düşerse
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

    # 3) Kurum yokken nakit kayıp riski
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

    # 5) Borç faizi
    if can_borrow(month) and float(p["debt"]) > 0:
        p["debt"] *= (1.0 + float(CFG["LOAN_RATE"]))

    # 6) Borç ödeme (ay sonu)
    if can_borrow(month) and float(p["debt"]) > 0 and repay_pct > 0:
        target = float(p["debt"]) * (float(repay_pct) / 100.0)
        repay_amt = min(float(p["holdings"]["cash"]), target)
        p["holdings"]["cash"] -= repay_amt
        p["debt"] -= repay_amt
        if p["debt"] < 0:
            p["debt"] = 0.0

    # 7) Dönem sonu
    end_cash = float(p["holdings"]["cash"])
    end_invest = total_investments(p)
    end_debt = float(p["debt"])
    end_total = end_cash + end_invest - end_debt

    # 8) Log (enflasyonun gider artırımı görünsün)
    p["log"].append({
        "Ay": month,
        "Aşama": stage_label(month),
        "EnflasyonOranı": infl,
        "Gelir(TL)": income,
        "SabitGider(TL)": fixed_this_month,
        "EkHarcama(TL)": float(extra),
        "Tasarruf(TL)": float(saving),
        "YatırımaGiden(TL)": float(invested_amount),
        "BorçÖdeme(TL)": float(repay_amt),
        "DönemSonuNakit(TL)": end_cash,
        "DönemSonuYatırım(TL)": end_invest,
        "DönemSonuBorç(TL)": end_debt,
        "ToplamServet(TL)": end_total,
    })

    # 9) Ay ilerlet / bitir
    if month >= CFG["MONTHS"]:
        p["finished"] = True
    else:
        p["month"] += 1

    st.rerun()

# =========================
# GEÇMİŞ TABLOSU (OYUN DEVAM EDERKEN)
# =========================
if p["log"]:
    st.divider()
    st.subheader("📒 Geçmiş (Sade)")
    df = pd.DataFrame(p["log"]).copy()
    cols = [
        "Ay","Aşama","EnflasyonOranı",
        "Gelir(TL)","SabitGider(TL)","EkHarcama(TL)","Tasarruf(TL)",
        "YatırımaGiden(TL)","BorçÖdeme(TL)",
        "DönemSonuNakit(TL)","DönemSonuYatırım(TL)","DönemSonuBorç(TL)",
        "ToplamServet(TL)"
    ]
    for col in cols:
        if col not in df.columns:
            df[col] = 0.0
    view = df[cols].fillna(0).copy()
    for col in cols:
        if "(TL)" in col:
            view[col] = pd.to_numeric(view[col], errors="coerce").fillna(0).round(0)
    st.dataframe(view, use_container_width=True, hide_index=True)
