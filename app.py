import streamlit as st
import numpy as np
import pandas as pd

st.set_page_config(page_title="Finans Neden Var?", layout="wide")

# =========================
# KİLİTLİ BAŞLANGIÇ DEĞERLERİ
# =========================
DEFAULT_MONTHLY_INCOME = 60000
START_FIXED_COST = 30000  # Ay1 sabit gider

# =========================
# AYARLAR
# =========================
CFG = {
    "MONTHS": 12,

    # Enflasyon: %20 ile başlar, her ay +%5 artar
    "INFL_START": 0.20,
    "INFL_STEP": 0.05,

    # Nakit hırsızlık (rastgele turlar): banka öncesi daha yüksek
    "CASH_THEFT_PROB_STAGE1": 0.12,  # Ay 1-3
    "CASH_THEFT_PROB_STAGE2": 0.05,  # Ay 4-12
    "CASH_THEFT_SEV_MIN": 0.10,
    "CASH_THEFT_SEV_MAX": 0.35,

    # Banka riski (çok düşük olasılık)
    "BANK_INCIDENT_PROB": 0.02,  # her banka/ay için olay olasılığı

    # Mevduat baz faizleri (aylık) -> bankalar bunu ufak oynar
    "DD_RATE_BASE": 0.0025,  # vadesiz
    "TD_RATE_BASE": 0.0100,  # vadeli

    # Banka faiz aralığı (trade-off için)
    "TD_RATE_MIN": 0.0070,   # %0.70 aylık
    "TD_RATE_MAX": 0.0140,   # %1.40 aylık

    # Güvence aralığı (trade-off için)
    "GUAR_MIN": 0.70,
    "GUAR_MAX": 0.99,

    # Riskli varlıklar (aylık)
    "EQ_MU": 0.015,
    "EQ_SIG": 0.060,
    "CR_MU": 0.020,
    "CR_SIG": 0.120,
    "PM_MU": 0.008,
    "PM_SIG": 0.030,
    "FX_MU": 0.010,
    "FX_SIG": 0.040,

    # Kriz ayı
    "CRISIS_MONTH": 6,
    "CRISIS_EQ": -0.12,
    "CRISIS_CR": -0.20,
    "CRISIS_PM": +0.04,
    "CRISIS_FX": +0.07,

    # Kredi faizi (aylık)
    "LOAN_RATE": 0.025,
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
# YARDIMCI FONKSİYONLAR
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
    return float(CFG["INFL_START"] + CFG["INFL_STEP"] * (month - 1))

def fmt_tl(x: float) -> str:
    return f"{x:,.0f} TL".replace(",", ".")

def fmt_pct(x: float) -> str:
    return f"{x*100:.0f}%"

def rng_for_global(month: int):
    # herkes aynı bankaları görsün diye oyuncudan bağımsız RNG
    return np.random.default_rng(st.session_state.seed + month * 999)

def rng_for_player(name: str, month: int):
    return np.random.default_rng((hash(name) % 10000) + month * 1000 + st.session_state.seed)

def bank_count_for_month(month: int) -> int:
    # Ay4:2 banka, Ay5:3 banka, ...
    if month < 4:
        return 0
    return min(2 + (month - 4), 8)

def banks_for_month(month: int):
    """
    Ay 4+ bankalar her ay artar.
    Trade-off: Vadeli faiz yükseldikçe güvence ortalamada düşer.
    """
    n = bank_count_for_month(month)
    if n == 0:
        return []

    r = rng_for_global(month)

    # 1) Önce TD faizleri üret (dağılım), sonra sırala
    td_rates = r.uniform(CFG["TD_RATE_MIN"], CFG["TD_RATE_MAX"], size=n)
    td_sorted_idx = np.argsort(td_rates)  # düşükten yükseğe

    banks = [None] * n

    for rank, idx in enumerate(td_sorted_idx):
        td = float(td_rates[idx])

        # rank: 0 en düşük faiz, n-1 en yüksek faiz
        # 2) Trade-off: yüksek faiz => düşük güvence
        # lineer çekirdek + noise
        x = rank / max(n - 1, 1)  # 0..1
        base_guar = CFG["GUAR_MAX"] - x * (CFG["GUAR_MAX"] - CFG["GUAR_MIN"])
        noise = float(r.normal(0, 0.015))  # küçük sapma
        guarantee = float(np.clip(base_guar + noise, CFG["GUAR_MIN"], CFG["GUAR_MAX"]))

        # 3) Vadesiz faiz: TD ile zayıf ilişki (çok küçük) + noise
        dd = float(CFG["DD_RATE_BASE"] + (td - CFG["TD_RATE_BASE"]) * 0.10 + r.normal(0, 0.00025))
        dd = float(max(0.0, dd))

        banks[idx] = {
            "Bank": f"Banka {idx + 1}",
            "TD_Rate": td,
            "DD_Rate": dd,
            "Guarantee": guarantee
        }

    return banks

def banks_df(month: int) -> pd.DataFrame:
    b = banks_for_month(month)
    if not b:
        return pd.DataFrame()
    df = pd.DataFrame(b)
    df["Vadeli Faiz (Aylık)"] = df["TD_Rate"].map(lambda x: f"{x*100:.2f}%")
    df["Vadesiz Faiz (Aylık)"] = df["DD_Rate"].map(lambda x: f"{x*100:.2f}%")
    df["Güvence Oranı"] = df["Guarantee"].map(lambda x: f"{x*100:.0f}%")
    # Öğrenci için "trade-off" vurgusu: faiz sırasına göre göster
    df2 = df.copy().sort_values("TD_Rate", ascending=False)
    return df2[["Bank", "Vadeli Faiz (Aylık)", "Vadesiz Faiz (Aylık)", "Güvence Oranı"]]

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
            "dd_accounts": {},  # bank -> balance
            "td_accounts": {},  # bank -> balance
            "log": [],
            "income_fixed": float(DEFAULT_MONTHLY_INCOME),
            "fixed_current": float(START_FIXED_COST),
            "last_event": None,
        }
    p = st.session_state.players[name]
    for k in ASSETS:
        p["holdings"].setdefault(k, 0.0)
    p.setdefault("dd_accounts", {})
    p.setdefault("td_accounts", {})
    p.setdefault("log", [])
    p.setdefault("last_event", None)
    return p

def dd_total(p: dict) -> float:
    return float(sum(p.get("dd_accounts", {}).values()))

def td_total(p: dict) -> float:
    return float(sum(p.get("td_accounts", {}).values()))

def total_investments(p: dict) -> float:
    other = float(sum(v for k, v in p["holdings"].items() if k != "cash"))
    return float(other + dd_total(p) + td_total(p))

def net_wealth(p: dict) -> float:
    return float(p["holdings"]["cash"] + total_investments(p) - float(p.get("debt", 0.0)))

# =========================
# UI - ÜST
# =========================
st.title("🎮 Finansal Piyasalar Neden Var? (1. Hafta Oyunu)")
st.caption(
    "Kurallar: Ay 1–3 borç yok (açık → temerrüt). Ay 4+ kredi var (açık otomatik kredi). "
    "Enflasyon sabit gideri artırır. Nakit bazı turlarda rastgele çalınabilir. "
    "Ay 4+ bankalar devreye girer; her ay banka sayısı artar. Bankaların vadeli/vadesiz faizleri ve güvence oranı farklıdır. "
    "Trade-off: Daha yüksek vadeli faiz, ortalamada daha düşük güvence demektir. "
    "Oyun 12 ay sürer."
)

c1, c2 = st.columns([1, 3])
with c1:
    if st.button("🧹 Oyunu Sıfırla"):
        st.session_state.clear()
        st.rerun()
with c2:
    st.caption("Gelir ve başlangıç sabit gideri standarttır; oyuncu değiştiremez.")

name = st.text_input("Oyuncu Adı")
if not name:
    st.stop()

p = get_player(name)

# Son olay mesajı
if p.get("last_event"):
    kind = p["last_event"].get("kind")
    msg = p["last_event"].get("msg", "")
    if kind in ("theft", "bank"):
        st.warning(msg)
    elif kind == "error":
        st.error(msg)
    elif kind == "info":
        st.info(msg)

# =========================
# LEADERBOARD
# =========================
st.subheader("🏆 Oyuncu Sıralaması")
rows = []
for pname, pp in st.session_state.players.items():
    cash = float(pp["holdings"].get("cash", 0.0))
    inv = float(sum(v for k, v in pp["holdings"].items() if k != "cash"))
    inv += float(sum(pp.get("dd_accounts", {}).values()))
    inv += float(sum(pp.get("td_accounts", {}).values()))
    debt = float(pp.get("debt", 0.0))
    net = cash + inv - debt

    status = "Devam"
    if pp.get("finished") and pp.get("defaulted"):
        status = "Temerrüt"
    elif pp.get("finished"):
        status = "Bitti"

    month_done = CFG["MONTHS"] if pp.get("finished") else max(int(pp.get("month", 1)) - 1, 0)
    rows.append({"Sıra": 0, "Oyuncu": pname, "Durum": status, "Ay": month_done,
                 "Servet(Net)": round(net, 0), "Borç": round(debt, 0)})

lb = pd.DataFrame(rows).sort_values(["Servet(Net)", "Borç"], ascending=[False, True]).reset_index(drop=True)
lb["Sıra"] = lb.index + 1
st.dataframe(lb, use_container_width=True, hide_index=True, height=220)

st.divider()

# =========================
# OYUN BİTTİ EKRANI
# =========================
if p.get("finished", False):
    if p.get("defaulted", False):
        st.error("⛔ Oyun bitti: Ay 1–3 döneminde açık oluştu (borç yok) → temerrüt.")
    else:
        st.success("✅ Oyun bitti: 12. ay tamamlandı.")

    a, b, c, d = st.columns(4)
    a.metric("Nakit", fmt_tl(p["holdings"]["cash"]))
    b.metric("Yatırım (Toplam)", fmt_tl(total_investments(p)))
    c.metric("Borç", fmt_tl(p["debt"]))
    d.metric("Servet (Net)", fmt_tl(net_wealth(p)))

    with st.expander("📒 Geçmiş (Sade)", expanded=True):
        if p["log"]:
            df = pd.DataFrame(p["log"]).copy()
            for col in df.columns:
                if "(TL)" in col:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).round(0)
            st.dataframe(df, use_container_width=True, hide_index=True, height=340)
    st.stop()

# =========================
# AY PANELİ
# =========================
month = int(p["month"])
opened = open_assets_by_month(month)
investable = [k for k in opened if k != "cash"]

income = float(p["income_fixed"])
infl = inflation_rate_for_month(month)
fixed_this_month = float(p["fixed_current"])

st.subheader(f"📅 Ay {month} / {CFG['MONTHS']} | Aşama: {stage_label(month)}")
st.progress((month - 1) / CFG["MONTHS"])

if month == CFG["CRISIS_MONTH"]:
    st.warning("🚨 Kriz ayı: bazı varlıklarda ekstra şok var.")

k1, k2, k3 = st.columns(3)
k1.metric("Enflasyon Oranı", fmt_pct(infl))
k2.metric("Gelir (Sabit)", fmt_tl(income))
k3.metric("Bu Ay Sabit Gider", fmt_tl(fixed_this_month))

m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("Nakit", fmt_tl(p["holdings"]["cash"]))
m2.metric("Vadesiz (Toplam)", fmt_tl(dd_total(p)))
m3.metric("Vadeli (Toplam)", fmt_tl(td_total(p)))
m4.metric("Diğer Yatırımlar", fmt_tl(sum(v for k, v in p["holdings"].items() if k != "cash")))
m5.metric("Borç", fmt_tl(p["debt"]))
m6.metric("Servet (Net)", fmt_tl(net_wealth(p)))

# =========================
# BANKALAR (Ay 4+)
# =========================
if month >= 4:
    st.divider()
    st.subheader("🏦 Bankalar (Bu Ay) — Faiz/Güvence Trade-off")

    b_list = banks_for_month(month)
    bank_map = {b["Bank"]: b for b in b_list}
    bdf = banks_df(month)
    st.dataframe(bdf, use_container_width=True, hide_index=True, height=220)

    banks_names = list(bank_map.keys())
    prev_dd = p.get("last_dd_bank", banks_names[0])
    prev_td = p.get("last_td_bank", banks_names[0])

    cA, cB = st.columns(2)
    with cA:
        selected_dd_bank = st.selectbox(
            "Vadesiz mevduat için bankanı seç",
            banks_names,
            index=banks_names.index(prev_dd) if prev_dd in banks_names else 0
        )
    with cB:
        selected_td_bank = st.selectbox(
            "Vadeli mevduat için bankanı seç",
            banks_names,
            index=banks_names.index(prev_td) if prev_td in banks_names else 0
        )

    p["last_dd_bank"] = selected_dd_bank
    p["last_td_bank"] = selected_td_bank

# =========================
# 1) BÜTÇE
# =========================
st.divider()
st.subheader("1) Bütçe (Bu Ay)")

available_without_borrow = p["holdings"]["cash"] + income
extra_max = int(max(0.0, available_without_borrow - fixed_this_month)) if not can_borrow(month) else int(income * 3)
extra_default = min(5000, max(0, extra_max))
extra = st.number_input("Ek Harcama", 0, max(0, extra_max), extra_default, 1000)

total_exp = fixed_this_month + float(extra)
saving = max(income - total_exp, 0.0)

if (not can_borrow(month)) and (total_exp > available_without_borrow):
    st.error("Ay 1–3'te borç yok. Bu bütçe nakit+geliri aşıyor → temerrüt olur. Ek harcamayı düşürün.")

cash_before_invest = float(p["holdings"]["cash"]) + income - total_exp
cash_before_invest = max(cash_before_invest, 0.0)

# =========================
# 2) YATIRIM HAVUZU
# =========================
st.divider()
st.subheader("2) Yatırım (Tasarrufu + Birikimi Dağıt)")

cash_extra = 0.0
if investable:
    cash_extra = st.number_input(
        "Nakitten Ek Yatırım (TL)",
        min_value=0.0,
        max_value=float(cash_before_invest),
        value=0.0,
        step=1000.0
    )
else:
    st.caption("Bu ay yatırım aracı yok → tasarruf nakitte kalır.")

invest_pool = float(saving + cash_extra)
st.write(f"Toplam yatırım havuzu: **{fmt_tl(invest_pool)}**")

alloc = {}
alloc_sum = 0.0

if invest_pool > 0 and investable:
    st.caption("Yüzdeleri girin. Toplam 100'ü aşarsa otomatik normalize edilir.")
    for k in investable:
        cA, cB, cC = st.columns([2.8, 1.2, 0.6])
        with cA:
            st.write(ASSETS[k])
        with cB:
            alloc[k] = st.number_input(
                f"{k}_pct",
                min_value=0,
                max_value=100,
                value=0,
                step=5,
                label_visibility="collapsed",
            )
        with cC:
            st.write("%")
    alloc_sum = float(sum(alloc.values()))
    st.write(f"Toplam: **{int(alloc_sum)}%**")

# =========================
# 3) BORÇ GERİ ÖDEME
# =========================
st.divider()
st.subheader("3) Borç Geri Ödeme (Ay Sonu)")

repay_pct = 0
if month >= 4 and float(p["debt"]) > 0:
    repay_pct = st.slider("Borcun ne kadarını ödemek istersiniz? (%)", 0, 100, 20, 5)
else:
    st.caption("Bu ay borç yok veya borç mekanizması henüz aktif değil.")

# =========================
# AYI TAMAMLA
# =========================
btn_label = "✅ Ayı Tamamla" if month < CFG["MONTHS"] else "✅ 12. Ayı Tamamla ve Bitir"

if st.button(btn_label):
    rng = rng_for_player(name, month)

    invested_amount = 0.0
    repay_amt = 0.0
    cash_theft_loss = 0.0
    bank_incident_loss = 0.0
    td_interest_income = 0.0
    dd_interest_income = 0.0

    # 0) gelir ekle
    p["holdings"]["cash"] += income

    # 1) giderleri öde
    p["holdings"]["cash"] -= total_exp

    if p["holdings"]["cash"] < 0:
        deficit = -float(p["holdings"]["cash"])
        if month < 4:
            p["holdings"]["cash"] = 0.0
            p["defaulted"] = True
            p["finished"] = True
            p["last_event"] = {"kind": "error", "msg": "⛔ Ay 1–3 döneminde borç yokken açık oluştu: TEMERRÜT!"}
            st.rerun()
        else:
            p["debt"] += deficit
            p["holdings"]["cash"] = 0.0

    # 2) yatırım transferi
    if invest_pool > 0 and investable and alloc_sum > 0:
        invested_amount = invest_pool if alloc_sum >= 100 else invest_pool * (alloc_sum / 100.0)

        alloc_adj = dict(alloc)
        if alloc_sum > 100:
            alloc_adj = {k: (v / alloc_sum) * 100 for k, v in alloc.items()}

        for k, pct in alloc_adj.items():
            invest_amt = invest_pool * (float(pct) / 100.0)
            if invest_amt <= 0:
                continue

            if k == "dd":
                bank = p.get("last_dd_bank", "Banka 1")
                p["dd_accounts"][bank] = float(p["dd_accounts"].get(bank, 0.0) + invest_amt)
            elif k == "td":
                bank = p.get("last_td_bank", "Banka 1")
                p["td_accounts"][bank] = float(p["td_accounts"].get(bank, 0.0) + invest_amt)
            else:
                p["holdings"][k] += invest_amt

            p["holdings"]["cash"] -= invest_amt

        if p["holdings"]["cash"] < 0:
            deficit2 = -float(p["holdings"]["cash"])
            if month >= 4:
                p["debt"] += deficit2
                p["holdings"]["cash"] = 0.0
            else:
                p["holdings"]["cash"] = 0.0
                p["defaulted"] = True
                p["finished"] = True
                p["last_event"] = {"kind": "error", "msg": "⛔ Ay 1–3 döneminde yatırım yüzünden açık oluştu: TEMERRÜT!"}
                st.rerun()

    # 3) Nakit hırsızlık
    theft_prob = CFG["CASH_THEFT_PROB_STAGE1"] if month <= 3 else CFG["CASH_THEFT_PROB_STAGE2"]
    if p["holdings"]["cash"] > 0 and rng.random() < theft_prob:
        sev = float(rng.uniform(CFG["CASH_THEFT_SEV_MIN"], CFG["CASH_THEFT_SEV_MAX"]))
        cash_theft_loss = float(p["holdings"]["cash"]) * sev
        p["holdings"]["cash"] -= cash_theft_loss
        p["last_event"] = {"kind": "theft", "msg": f"🚨 Nakit hırsızlığı! Kayıp: **{fmt_tl(cash_theft_loss)}**"}
    else:
        p["last_event"] = None

    # 4) Banka olayı + faiz (Ay4+)
    if month >= 4:
        b_list = banks_for_month(month)
        bmap = {b["Bank"]: b for b in b_list}

        # Banka olayı: güvence dışı kısım kayıp
        for bank, bal in list(p["dd_accounts"].items()):
            if bal > 0 and bank in bmap and rng.random() < CFG["BANK_INCIDENT_PROB"]:
                guar = float(bmap[bank]["Guarantee"])
                loss = float(bal * (1.0 - guar))
                p["dd_accounts"][bank] = float(max(0.0, bal - loss))
                bank_incident_loss += loss

        for bank, bal in list(p["td_accounts"].items()):
            if bal > 0 and bank in bmap and rng.random() < CFG["BANK_INCIDENT_PROB"]:
                guar = float(bmap[bank]["Guarantee"])
                loss = float(bal * (1.0 - guar))
                p["td_accounts"][bank] = float(max(0.0, bal - loss))
                bank_incident_loss += loss

        if bank_incident_loss > 0:
            p["last_event"] = {"kind": "bank", "msg": f"🏦⚠️ Banka olayı! Mevduat kaybı: **{fmt_tl(bank_incident_loss)}**"}

        # Faiz getirileri (bankaya göre)
        for bank, bal in list(p["dd_accounts"].items()):
            if bal > 0 and bank in bmap:
                before = float(bal)
                rate = float(bmap[bank]["DD_Rate"])
                after = float(before * (1.0 + rate))
                p["dd_accounts"][bank] = after
                dd_interest_income += (after - before)

        for bank, bal in list(p["td_accounts"].items()):
            if bal > 0 and bank in bmap:
                before = float(bal)
                rate = float(bmap[bank]["TD_Rate"])
                after = float(before * (1.0 + rate))
                p["td_accounts"][bank] = after
                td_interest_income += (after - before)

    # 5) Riskli varlık getirileri
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

    # 6) Borç faizi
    if month >= 4 and float(p["debt"]) > 0:
        p["debt"] *= (1.0 + float(CFG["LOAN_RATE"]))

    # 7) Borç geri ödeme
    if month >= 4 and float(p["debt"]) > 0 and repay_pct > 0:
        target = float(p["debt"]) * (float(repay_pct) / 100.0)
        repay_amt = min(float(p["holdings"]["cash"]), target)
        p["holdings"]["cash"] -= repay_amt
        p["debt"] -= repay_amt
        if p["debt"] < 0:
            p["debt"] = 0.0

    # 8) Dönem sonu
    end_cash = float(p["holdings"]["cash"])
    end_inv = total_investments(p)
    end_debt = float(p["debt"])
    end_total = end_cash + end_inv - end_debt

    # 9) Log
    p["log"].append({
        "Ay": month,
        "Aşama": stage_label(month),
        "EnflasyonOranı": infl,
        "Gelir(TL)": income,
        "SabitGider(TL)": fixed_this_month,
        "EkHarcama(TL)": float(extra),
        "Tasarruf(TL)": float(max(income - total_exp, 0.0)),
        "NakittenEkYatırım(TL)": float(cash_extra),
        "ToplamYatırımHavuzu(TL)": float(invest_pool),
        "SeçilenDD_Banka": p.get("last_dd_bank", ""),
        "SeçilenTD_Banka": p.get("last_td_bank", ""),
        "VadesizFaizGeliri(TL)": float(dd_interest_income),
        "VadeliFaizGeliri(TL)": float(td_interest_income),
        "NakitKaybı(TL)": float(cash_theft_loss),
        "BankaKaybı(TL)": float(bank_incident_loss),
        "BorçÖdeme(TL)": float(repay_amt),
        "DönemSonuNakit(TL)": end_cash,
        "DönemSonuYatırım(TL)": end_inv,
        "DönemSonuBorç(TL)": end_debt,
        "ToplamServet(TL)": end_total,
    })

    # 10) Sabit gideri bir sonraki aya taşı (bileşik artış)
    if month < CFG["MONTHS"]:
        next_month = month + 1
        next_infl = inflation_rate_for_month(next_month)
        p["fixed_current"] = float(fixed_this_month * (1.0 + next_infl))

    # 11) Ay ilerlet / bitir
    if month >= CFG["MONTHS"]:
        p["finished"] = True
    else:
        p["month"] += 1

    st.rerun()

# =========================
# GEÇMİŞ TABLO
# =========================
if p["log"]:
    st.divider()
    st.subheader("📒 Geçmiş (Sade)")

    df = pd.DataFrame(p["log"]).copy()
    for col in df.columns:
        if "(TL)" in col:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).round(0)

    with st.expander("Geçmiş Tablosunu Göster/Gizle", expanded=True):
        st.dataframe(df, use_container_width=True, hide_index=True, height=340)
