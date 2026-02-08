import streamlit as st
import numpy as np
import pandas as pd

st.set_page_config(page_title="Borsa Uygulamaları - 1. Hafta Oyunu", layout="wide")

# =========================
# SABİT (ÖĞRENCİ DEĞİŞTİREMEZ)
# =========================
DEFAULT_MONTHLY_INCOME = 60000
START_FIXED_COST = 30000
START_EXTRA_COST = 5000  # Ek harcama sabit başlar (oyuncu giremez/değiştiremez)

# =========================
# OYUN PARAMETRELERİ
# =========================
CFG = {
    "MONTHS": 12,

    # Fiyatlar Genel Düzeyi (FGD) – Ay bazlı değişim adımı (%1-%5 arası, +/-)
    "PGL_MIN_STEP": 0.01,
    "PGL_MAX_STEP": 0.05,
    "PGL_FLOOR": 0.01,  # ekranda gösterilen FGD seviyesi bandı (%1-%5)
    "PGL_CAP": 0.05,

    "LOAN_ACTIVE_FROM_MONTH": 4,

    # Nakit hırsızlığı
    "CASH_THEFT_PROB_STAGE1": 0.12,
    "CASH_THEFT_PROB_STAGE2": 0.05,
    "CASH_THEFT_SEV_MIN": 0.10,
    "CASH_THEFT_SEV_MAX": 0.35,

    "BANK_INCIDENT_PROB": 0.02,

    # Banka faiz/güvence
    "TD_RATE_MIN": 0.0070,
    "TD_RATE_MAX": 0.0140,
    "GUAR_MIN": 0.70,
    "GUAR_MAX": 0.99,

    # Kredi faizi
    "LOAN_RATE_BASE": 0.018,
    "LOAN_RATE_ADD": 0.030,
    "LOAN_RATE_NOISE": 0.002,
    "LOAN_MAX_MULT_INCOME": 3.0,

    # Vadeli bozma cezası / işlem komisyonu
    "EARLY_BREAK_PENALTY": 0.01,
    "TX_FEE": 0.005,

    # Spread
    "SPREAD": {"fx": 0.010, "pm": 0.012, "eq": 0.020, "cr": 0.050},

    # Riskli varlık getirileri (aylık)
    "EQ_MU": 0.015, "EQ_SIG": 0.060,
    "CR_MU": 0.020, "CR_SIG": 0.120,
    "PM_MU": 0.008, "PM_SIG": 0.030,
    "FX_MU": 0.010, "FX_SIG": 0.040,

    # Kriz ayı
    "CRISIS_MONTH": 6,
    "CRISIS_EQ": -0.12,
    "CRISIS_CR": -0.20,
    "CRISIS_PM": +0.04,
    "CRISIS_FX": +0.07,
}

ASSETS = {
    "cash": "Nakit",
    "dd": "Vadesiz Mevduat (Faiz Yok)",
    "td": "Vadeli Mevduat (Faiz Var)",
    "fx": "Döviz",
    "pm": "Kıymetli Metal",
    "eq": "Hisse Senedi",
    "cr": "Kripto",
}

RISK_ASSETS = ["fx", "pm", "eq", "cr"]
DEPOSIT_ASSETS = ["dd", "td"]

# =========================
# YARDIMCI
# =========================
def fmt_tl(x: float) -> str:
    return f"{x:,.0f} TL".replace(",", ".")

def fmt_pct(x: float) -> str:
    return f"{x*100:.1f}%"

def can_borrow(month: int) -> bool:
    return month >= int(CFG["LOAN_ACTIVE_FROM_MONTH"])

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

def rng_for_global(month: int):
    return np.random.default_rng(st.session_state.seed + month * 999)

def rng_for_player(name: str, month: int):
    return np.random.default_rng((hash(name) % 10000) + month * 1000 + st.session_state.seed)

def random_pgl_step(rng: np.random.Generator) -> float:
    return float(rng.uniform(CFG["PGL_MIN_STEP"], CFG["PGL_MAX_STEP"]))

def next_pgl(prev_pgl: float, rng: np.random.Generator):
    step = random_pgl_step(rng)
    sign = -1.0 if rng.random() < 0.5 else 1.0
    signed_delta = float(sign * step)

    new_pgl = float(prev_pgl + signed_delta)
    new_pgl = float(np.clip(new_pgl, CFG["PGL_FLOOR"], CFG["PGL_CAP"]))
    realized_delta = float(new_pgl - prev_pgl)  # giderlere uygulanacak +/- değişim
    return new_pgl, realized_delta

def bank_count_for_month(month: int) -> int:
    if month < 4:
        return 0
    return min(2 + (month - 4), 8)

def banks_for_month(month: int):
    n = bank_count_for_month(month)
    if n == 0:
        return []

    # ay bazlı bankaları sabitle
    if month in st.session_state.bank_state:
        bmap = st.session_state.bank_state[month]
        out = []
        for i in range(n):
            name = f"Banka {i+1}"
            out.append({"Bank": name, **bmap[name]})
        return out

    r = rng_for_global(month)

    td_min, td_max = float(CFG["TD_RATE_MIN"]), float(CFG["TD_RATE_MAX"])
    gmin, gmax = float(CFG["GUAR_MIN"]), float(CFG["GUAR_MAX"])

    TD_STEP = 0.0015
    G_STEP  = 0.010
    prev = st.session_state.bank_state.get(month - 1)

    bmap_this = {}
    for i in range(n):
        bname = f"Banka {i+1}"

        if prev and bname in prev:
            td_prev = float(prev[bname]["TD_Rate"])
            g_prev  = float(prev[bname]["Guarantee"])
            td = td_prev + float(r.normal(0, TD_STEP))
            guar = g_prev + float(r.normal(0, G_STEP))
            td = float(np.clip(td, td_min, td_max))
            guar = float(np.clip(guar, gmin, gmax))
        else:
            td = float(r.uniform(td_min, td_max))
            x = (td - td_min) / max(td_max - td_min, 1e-9)
            base_guar = gmax - x * (gmax - gmin)
            guar = float(np.clip(base_guar + float(r.normal(0, 0.015)), gmin, gmax))

        loan_rate = float(np.clip(
            float(CFG["LOAN_RATE_BASE"]) + (1.0 - guar) * float(CFG["LOAN_RATE_ADD"]) + float(r.normal(0, float(CFG["LOAN_RATE_NOISE"]))),
            0.010, 0.060
        ))

        bmap_this[bname] = {"TD_Rate": td, "Guarantee": guar, "Loan_Rate": loan_rate}

    st.session_state.bank_state[month] = bmap_this

    out = []
    for i in range(n):
        name = f"Banka {i+1}"
        out.append({"Bank": name, **bmap_this[name]})
    return out

def banks_df(month: int) -> pd.DataFrame:
    b = banks_for_month(month)
    if not b:
        return pd.DataFrame()
    df = pd.DataFrame(b)
    df["Vadeli Faiz (Aylık)"] = df["TD_Rate"].map(lambda x: f"{x*100:.2f}%")
    df["Güvence Oranı"] = df["Guarantee"].map(lambda x: f"{x*100:.0f}%")
    df["Kredi Faizi (Aylık)"] = df["Loan_Rate"].map(lambda x: f"{x*100:.2f}%")
    return df.sort_values("TD_Rate", ascending=False)[["Bank", "Vadeli Faiz (Aylık)", "Güvence Oranı", "Kredi Faizi (Aylık)"]]

def buy_cost_rate(asset_key: str) -> float:
    fee = float(CFG["TX_FEE"])
    spr = float(CFG["SPREAD"].get(asset_key, 0.0))
    return fee + spr / 2.0

def sell_cost_rate(asset_key: str) -> float:
    fee = float(CFG["TX_FEE"])
    spr = float(CFG["SPREAD"].get(asset_key, 0.0))
    return fee + spr / 2.0

def dd_total(p: dict) -> float:
    return float(sum(p.get("dd_accounts", {}).values()))

def td_total(p: dict) -> float:
    return float(sum(p.get("td_accounts", {}).values()))

def other_investments_total(p: dict) -> float:
    return float(sum(p["holdings"].get(k, 0.0) for k in RISK_ASSETS))

def total_investments(p: dict) -> float:
    return float(dd_total(p) + td_total(p) + other_investments_total(p))

def safe_number_input(label: str, key: str, maxv: float, step: float = 1000.0) -> float:
    maxv = float(max(0.0, maxv))
    if maxv <= 0.0:
        st.caption("Bu kalemde işlem yapılamaz (limit 0).")
        if key in st.session_state:
            st.session_state[key] = 0.0
        return 0.0
    prev = float(st.session_state.get(key, 0.0))
    val = min(max(prev, 0.0), maxv)
    return st.number_input(label, min_value=0.0, max_value=maxv, value=val, step=step, key=key)

# =========================
# 1 AYLIK BORÇ MODELİ
# =========================
def loan_due_amount(p: dict, current_month: int) -> float:
    total = 0.0
    for ln in p.get("loans", []):
        if int(ln["due_month"]) == int(current_month):
            total += float(ln["principal"]) * (1.0 + float(ln["rate"]))
    return float(total)

def loan_outstanding_principal(p: dict) -> float:
    return float(sum(float(ln["principal"]) for ln in p.get("loans", [])))

def remove_due_loans(p: dict, current_month: int):
    p["loans"] = [ln for ln in p.get("loans", []) if int(ln["due_month"]) != int(current_month)]

def total_debt_display(p: dict, current_month: int) -> float:
    due = loan_due_amount(p, current_month)
    future_principal = float(sum(float(ln["principal"]) for ln in p.get("loans", []) if int(ln["due_month"]) > int(current_month)))
    return float(due + future_principal)

def net_wealth(p: dict) -> float:
    return float(p["holdings"]["cash"] + total_investments(p) - float(loan_outstanding_principal(p)))

# =========================
# SESSION STATE
# =========================
if "seed" not in st.session_state:
    st.session_state.seed = 20260209
if "players" not in st.session_state:
    st.session_state.players = {}
if "theft_popup" not in st.session_state:
    st.session_state.theft_popup = None
if "pgl_popup" not in st.session_state:
    st.session_state.pgl_popup = None
if "loan_popup" not in st.session_state:
    st.session_state.loan_popup = None
if "bank_state" not in st.session_state:
    st.session_state.bank_state = {}

def get_player(name: str) -> dict:
    if name not in st.session_state.players:
        theft_rng = np.random.default_rng((hash(name) % 10000) + st.session_state.seed)
        theft_months = sorted(
            theft_rng.choice(np.arange(1, CFG["MONTHS"] + 1), size=3, replace=False).tolist()
        )

        pgl0 = float(np.random.default_rng((hash(name) % 10000) + st.session_state.seed + 777).uniform(
            CFG["PGL_FLOOR"], CFG["PGL_CAP"]
        ))

        st.session_state.players[name] = {
            "month": 1,
            "finished": False,
            "defaulted": False,

            "loans": [],
            "loan_bank": None,

            "holdings": {"cash": 0.0, "fx": 0.0, "pm": 0.0, "eq": 0.0, "cr": 0.0},
            "dd_accounts": {},
            "td_accounts": {},

            "income_fixed": float(DEFAULT_MONTHLY_INCOME),
            "fixed_current": float(START_FIXED_COST),
            "extra_current": float(START_EXTRA_COST),
            "pgl_current": float(pgl0),

            "last_dd_bank": None,
            "last_td_bank": None,

            "theft_months": theft_months,
            "log": [],
        }
    return st.session_state.players[name]

# =========================
# SIDEBAR
# =========================
with st.sidebar:
    st.header("ℹ️ Oyun Bilgisi")
    st.write(
        "- **Gelir sabittir.**\n"
        "- **Fiyatlar Genel Düzeyi** her ay bir **değişim** (artış/azalış) gösterir.\n"
        "- **Sabit giderler** ve **ek harcama**, bu değişime göre **bir sonraki ay** artar ya da azalır.\n"
        "- **4. aydan itibaren** finansal kurumlar devreye girer."
    )
    st.divider()
    if st.button("🧹 Oyunu Sıfırla"):
        st.session_state.clear()
        st.rerun()

st.title("🎮 1. Hafta Oyunu: Neden Finansal Piyasalar ve Kurumlarla İlgileniyoruz?")

# =========================
# POP-UP RENDER (Modal)
# =========================
def _overlay_style():
    st.markdown(
        """
        <style>
        .ovl {
            position: fixed; top: 0; left: 0;
            width: 100vw; height: 100vh;
            background: rgba(0,0,0,0.35);
            z-index: 9999;
            display: flex; align-items: center; justify-content: center;
            padding: 18px;
        }
        .card {
            background: #ffffff;
            border-radius: 18px;
            padding: 18px;
            max-width: 580px;
            width: 100%;
            box-shadow: 0 18px 60px rgba(0,0,0,0.20);
            border: 2px solid rgba(0,0,0,0.06);
        }
        .titleRed { font-size: 22px; font-weight: 900; color:#b30000; margin-bottom: 6px; }
        .titleBlue { font-size: 22px; font-weight: 900; color:#0b4aa2; margin-bottom: 6px; }
        .titleOrange { font-size: 22px; font-weight: 900; color:#9a4b00; margin-bottom: 6px; }
        </style>
        """,
        unsafe_allow_html=True
    )

def render_theft_modal():
    pop = st.session_state.get("theft_popup")
    if not pop:
        return
    loss = float(pop.get("loss", 0.0))
    remain = float(pop.get("remain", 0.0))
    m = int(pop.get("month", 0))
    player = str(pop.get("player", ""))

    if hasattr(st, "dialog"):
        @st.dialog("🚨 NAKİT HIRSIZLIĞI!")
        def _dlg():
            st.markdown(
                f"""
                **Oyuncu:** {player}  
                **Ay:** {m}

                **Kayıp:** :red[**{fmt_tl(loss)}**]  
                **Kalan Nakit:** **{fmt_tl(remain)}**

                Bu risk yalnızca **nakitte** geçerlidir.
                """
            )
            if st.button("Kapat ✖", use_container_width=True, key=f"close_theft_{player}_{m}"):
                st.session_state.theft_popup = None
                st.rerun()
        _dlg()
    else:
        _overlay_style()
        st.markdown(
            f"""
            <div class="ovl">
              <div class="card" style="border:4px solid #b30000;background:#fff5f5;">
                <div class="titleRed">🚨 NAKİT HIRSIZLIĞI! 🚨</div>
                <div><b>Oyuncu:</b> {player} &nbsp; | &nbsp; <b>Ay:</b> {m}</div>
                <div style="margin-top:10px;"><b>Kayıp:</b> <span style="color:#b30000;font-weight:900;">{fmt_tl(loss)}</span></div>
                <div><b>Kalan Nakit:</b> <b>{fmt_tl(remain)}</b></div>
                <div style="margin-top:10px;">Bu risk yalnızca <b>nakitte</b> geçerlidir.</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        if st.button("Kapat ✖", use_container_width=True, key=f"close_theft_fallback_{player}_{m}"):
            st.session_state.theft_popup = None
            st.rerun()

def render_pgl_modal():
    pop = st.session_state.get("pgl_popup")
    if not pop:
        return

    player = str(pop.get("player", ""))
    from_month = int(pop.get("from_month", 0))
    to_month = int(pop.get("to_month", 0))
    pgl_prev = float(pop.get("pgl_prev", 0.0))
    pgl_new = float(pop.get("pgl_new", 0.0))
    step_used = float(pop.get("step_used", 0.0))
    fixed_prev = float(pop.get("fixed_prev", 0.0))
    fixed_new = float(pop.get("fixed_new", 0.0))
    extra_prev = float(pop.get("extra_prev", 0.0))
    extra_new = float(pop.get("extra_new", 0.0))

    if step_used > 0:
        msg = "Bu ay **artış (+)** oldu → bir sonraki ay giderler **arttı**."
        arrow = "⬆️"
    elif step_used < 0:
        msg = "Bu ay **azalış (−)** oldu → bir sonraki ay giderler **azaldı**."
        arrow = "⬇️"
    else:
        msg = "Band sınırına çarptığı için bu ay değişim **0** gerçekleşti."
        arrow = "➡️"
    step_text = f"{arrow} {fmt_pct(abs(step_used))}"

    if hasattr(st, "dialog"):
        @st.dialog("📌 Fiyatlar Genel Düzeyi Güncellendi")
        def _dlg():
            st.markdown(
                f"""
                **Oyuncu:** {player}  
                **Geçiş:** Ay {from_month} → Ay {to_month}

                **Fiyatlar Genel Düzeyi:** {fmt_pct(pgl_prev)} → **{fmt_pct(pgl_new)}**  
                **Bu Ay Değişim:** **{step_text}**  

                **Sabit Gider:** {fmt_tl(fixed_prev)} → **{fmt_tl(fixed_new)}**  
                **Ek Harcama:** {fmt_tl(extra_prev)} → **{fmt_tl(extra_new)}**

                {msg}
                """
            )
            if st.button("Kapat ✖", use_container_width=True, key=f"close_pgl_{player}_{to_month}"):
                st.session_state.pgl_popup = None
                st.rerun()
        _dlg()
    else:
        _overlay_style()
        st.markdown(
            f"""
            <div class="ovl">
              <div class="card" style="border:4px solid #0b4aa2;background:#f3f8ff;">
                <div class="titleBlue">📌 Fiyatlar Genel Düzeyi Güncellendi</div>
                <div><b>Oyuncu:</b> {player} &nbsp; | &nbsp; <b>Geçiş:</b> Ay {from_month} → Ay {to_month}</div>
                <div style="margin-top:10px;"><b>FGD:</b> {fmt_pct(pgl_prev)} → <b>{fmt_pct(pgl_new)}</b></div>
                <div><b>Bu Ay Değişim:</b> <b>{step_text}</b></div>
                <div style="margin-top:10px;"><b>Sabit Gider:</b> {fmt_tl(fixed_prev)} → <b>{fmt_tl(fixed_new)}</b></div>
                <div><b>Ek Harcama:</b> {fmt_tl(extra_prev)} → <b>{fmt_tl(extra_new)}</b></div>
                <div style="margin-top:10px;">{msg}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        if st.button("Kapat ✖", use_container_width=True, key=f"close_pgl_fallback_{player}_{to_month}"):
            st.session_state.pgl_popup = None
            st.rerun()

def render_loan_modal():
    pop = st.session_state.get("loan_popup")
    if not pop:
        return
    player = str(pop.get("player", ""))
    m = int(pop.get("month", 0))
    principal = float(pop.get("principal", 0.0))
    rate = float(pop.get("rate", 0.0))
    due = float(pop.get("due", 0.0))

    msg = "Borcunuzu, bir sonraki ay ana para + faizi ile birlikte ödemek zorundasınız!"

    if hasattr(st, "dialog"):
        @st.dialog("⚠️ Borç Uyarısı")
        def _dlg():
            st.markdown(
                f"""
                **Oyuncu:** {player}  
                **Alındığı ay:** {m}

                **Anapara:** **{fmt_tl(principal)}**  
                **Faiz (1 ay):** **{rate*100:.2f}%**  
                **Gelecek ay ödenecek:** **{fmt_tl(due)}**

                **{msg}**
                """
            )
            if st.button("Kapat ✖", use_container_width=True, key=f"close_loan_{player}_{m}"):
                st.session_state.loan_popup = None
                st.rerun()
        _dlg()
    else:
        _overlay_style()
        st.markdown(
            f"""
            <div class="ovl">
              <div class="card" style="border:4px solid #9a4b00;background:#fff7ee;">
                <div class="titleOrange">⚠️ Borç Uyarısı</div>
                <div><b>Oyuncu:</b> {player} &nbsp; | &nbsp; <b>Ay:</b> {m}</div>
                <div style="margin-top:10px;"><b>Anapara:</b> <b>{fmt_tl(principal)}</b></div>
                <div><b>Faiz:</b> <b>{rate*100:.2f}%</b></div>
                <div><b>Gelecek ay ödenecek:</b> <b>{fmt_tl(due)}</b></div>
                <div style="margin-top:10px;font-weight:900;">{msg}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        if st.button("Kapat ✖", use_container_width=True, key=f"close_loan_fallback_{player}_{m}"):
            st.session_state.loan_popup = None
            st.rerun()

# =========================
# OYUNCU ADI
# =========================
name = st.text_input("Oyuncu Adı")
if not name:
    st.stop()

p = get_player(name)
month = int(p["month"])
opened = open_assets_by_month(month)

# popuplar
render_theft_modal()
render_pgl_modal()
render_loan_modal()

# =========================
# OYUN BİTTİ
# =========================
if p.get("finished", False):
    st.subheader("✅ Oyun Sonu")
    if p.get("defaulted", False):
        st.error("⛔ Oyun bitti: Temerrüt oluştu.")
    else:
        st.success("✅ Oyun bitti: 12. ay tamamlandı.")
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Nakit", fmt_tl(p["holdings"]["cash"]))
    a2.metric("Yatırım (Toplam)", fmt_tl(total_investments(p)))
    a3.metric("Borç (Toplam Görünüm)", fmt_tl(total_debt_display(p, month)))
    a4.metric("Servet (Net)", fmt_tl(net_wealth(p)))
    st.stop()

# =========================
# AY PANELİ (ÖZET)
# =========================
income = float(p["income_fixed"])
pgl = float(p["pgl_current"])
fixed_this_month = float(p["fixed_current"])
extra_this_month = float(p["extra_current"])
due_this_month = float(loan_due_amount(p, month))

st.markdown(f"### 📅 Ay {month}/{CFG['MONTHS']}  —  Aşama: **{stage_label(month)}**")
st.progress((month - 1) / CFG["MONTHS"])

r1a, r1b, r1c, r1d = st.columns(4)
r1a.metric("Net Servet", fmt_tl(net_wealth(p)))
r1b.metric("Nakit", fmt_tl(p["holdings"]["cash"]))
r1c.metric("Yatırım (Toplam)", fmt_tl(total_investments(p)))
r1d.metric("Borç (Vade+Anapara)", fmt_tl(total_debt_display(p, month)))

r2a, r2b, r2c, r2d = st.columns(4)
r2a.metric("Fiyatlar Genel Düzeyi (Bu Ay)", fmt_pct(pgl))
r2b.metric("Sabit Gider (Bu Ay)", fmt_tl(fixed_this_month))
r2c.metric("Ek Harcama (Bu Ay)", fmt_tl(extra_this_month))
r2d.metric("Gelir (Sabit)", fmt_tl(income))

r3a, r3b, r3c, r3d = st.columns(4)
r3a.metric("Finansal Kurumlar", "Açık (Ay4+)" if can_borrow(month) else "Kapalı (Ay1-3)")
r3b.metric("Vadesiz Toplam", fmt_tl(dd_total(p)))
r3c.metric("Vadeli Toplam", fmt_tl(td_total(p)))
r3d.metric("Diğer Yatırımlar", fmt_tl(other_investments_total(p)))

if due_this_month > 0:
    st.warning(f"⚠️ Bu ay vadesi gelen 1 aylık borç ödemesi var: **{fmt_tl(due_this_month)}** (Ay sonunda ödenir)")

tab_game, tab_banks, tab_log = st.tabs(["🎯 Karar Ekranı", "🏦 Bankalar & Mevduat", "📒 Geçmiş"])

# =========================
# BANKALAR TAB
# =========================
with tab_banks:
    st.subheader("🏦 Bankalar ve Mevduat")

    if month < 4:
        st.info("Ay 1–3: Bankalar yok.")
    else:
        b_list = banks_for_month(month)
        bank_map = {b["Bank"]: b for b in b_list}
        st.dataframe(banks_df(month), use_container_width=True, hide_index=True, height=280)

        banks_names = list(bank_map.keys())
        if p.get("last_dd_bank") is None:
            p["last_dd_bank"] = banks_names[-1]
        if p.get("last_td_bank") is None:
            p["last_td_bank"] = banks_names[0]
        if p.get("loan_bank") is None:
            best = sorted(b_list, key=lambda x: x["Loan_Rate"])[0]["Bank"]
            p["loan_bank"] = best

        cA, cB, cC = st.columns(3)
        with cA:
            p["last_dd_bank"] = st.selectbox("Vadesiz bankası", banks_names, index=banks_names.index(p["last_dd_bank"]), key=f"sel_dd_{name}_{month}")
        with cB:
            p["last_td_bank"] = st.selectbox("Vadeli bankası", banks_names, index=banks_names.index(p["last_td_bank"]), key=f"sel_td_{name}_{month}")
        with cC:
            p["loan_bank"] = st.selectbox("Kredi bankası", banks_names, index=banks_names.index(p["loan_bank"]), key=f"sel_loan_{name}_{month}")
            st.caption(f"Kredi faizi: **{bank_map[p['loan_bank']]['Loan_Rate']*100:.2f}% / ay** (1 ay vadeli)")

# =========================
# GEÇMİŞ TAB
# =========================
with tab_log:
    st.subheader("📒 Geçmiş (Kaydırmasız)")
    if not p["log"]:
        st.info("Henüz kayıt yok.")
    else:
        for row in reversed(p["log"]):
            ay = row.get("Ay", "-")
            asama = row.get("Aşama", "-")
            with st.expander(f"Ay {ay} — {asama}", expanded=False):
                cols = st.columns(2)
                items = list(row.items())
                half = (len(items) + 1) // 2
                left_items = items[:half]
                right_items = items[half:]

                def render_kv(pairs, col):
                    with col:
                        for k, v in pairs:
                            if isinstance(v, (int, float)):
                                if "Fiyatlar" in str(k):
                                    st.markdown(f"**{k}:** {fmt_pct(float(v))}")
                                else:
                                    st.markdown(f"**{k}:** {fmt_tl(float(v))}")
                            else:
                                st.markdown(f"**{k}:** {v}")

                render_kv(left_items, cols[0])
                render_kv(right_items, cols[1])

# =========================
# KARAR EKRANI TAB
# =========================
with tab_game:
    st.subheader("🎯 Bu Ay Kararları")

    fee = float(CFG["TX_FEE"])
    pen = float(CFG["EARLY_BREAK_PENALTY"])

    # 0) SATIŞ / BOZDURMA
    st.markdown("#### 0) Yatırımı Sat / Mevduatı Çek (Opsiyonel)")
    sell_inputs = {k: 0.0 for k in RISK_ASSETS}
    sell_dd_amt = 0.0
    sell_td_amt = 0.0
    sell_dd_bank = None
    sell_td_bank = None

    colS1, colS2 = st.columns(2)
    with colS1:
        st.write("**Riskli varlık satışı (TL):**")
        for k in RISK_ASSETS:
            if k not in opened:
                continue
            max_sell = float(p["holdings"].get(k, 0.0))
            rate = sell_cost_rate(k)
            st.caption(f"{ASSETS[k]} | Maks: {fmt_tl(max_sell)} | Maliyet: {rate*100:.2f}%")
            sell_amt = safe_number_input(f"{ASSETS[k]} Satış", f"sell_{k}_{name}_{month}", max_sell, 1000.0)
            sell_inputs[k] = float(sell_amt)
            st.caption(f"Net nakit girişi (tahmini): {fmt_tl(float(sell_amt) * (1.0 - rate))}")

    with colS2:
        st.write("**Mevduat çek/boz (TL):**")
        if month < 4:
            st.caption("Ay 1–3: mevduat yok.")
        else:
            dd_banks = [bk for bk, bal in p["dd_accounts"].items() if float(bal) > 0]
            if dd_banks:
                sell_dd_bank = st.selectbox("Vadesizden çekilecek banka", dd_banks, key=f"dd_with_bank_{name}_{month}")
                max_dd = float(p["dd_accounts"].get(sell_dd_bank, 0.0))
                st.caption(f"Vadesiz ({sell_dd_bank}) | Maks: {fmt_tl(max_dd)} | Komisyon: {fee*100:.2f}%")
                sell_dd_amt = safe_number_input("Vadesiz Çekim", f"sell_dd_{name}_{month}", max_dd, 1000.0)
                st.caption(f"Net nakit girişi (tahmini): {fmt_tl(float(sell_dd_amt) * (1.0 - fee))}")
            else:
                st.caption("Vadesiz mevduat yok.")

            td_banks = [bk for bk, bal in p["td_accounts"].items() if float(bal) > 0]
            if td_banks:
                sell_td_bank = st.selectbox("Vadeliden bozulacak banka", td_banks, key=f"td_break_bank_{name}_{month}")
                max_td = float(p["td_accounts"].get(sell_td_bank, 0.0))
                st.caption(f"Vadeli ({sell_td_bank}) | Maks: {fmt_tl(max_td)} | Ceza: {pen*100:.2f}% + Komisyon: {fee*100:.2f}%")
                sell_td_amt = safe_number_input("Vadeli Bozma", f"sell_td_{name}_{month}", max_td, 1000.0)
                st.caption(f"Net nakit girişi (tahmini): {fmt_tl(float(sell_td_amt) * (1.0 - fee - pen))}")
            else:
                st.caption("Vadeli mevduat yok.")

    projected_sell_cash_in = 0.0
    for k, amt in sell_inputs.items():
        amt = float(amt)
        if amt <= 0:
            continue
        projected_sell_cash_in += amt * (1.0 - sell_cost_rate(k))
    if month >= 4 and sell_dd_amt > 0:
        projected_sell_cash_in += float(sell_dd_amt) * (1.0 - fee)
    if month >= 4 and sell_td_amt > 0:
        projected_sell_cash_in += float(sell_td_amt) * (1.0 - fee - pen)

    st.info(f"Satış/bozma ile tahmini net nakit girişi: **{fmt_tl(projected_sell_cash_in)}**")
    st.divider()

    # 1) BÜTÇE (Ek harcama otomatik)
    st.markdown("#### 1) Bütçe (Bu Ay)")
    total_exp = float(fixed_this_month) + float(extra_this_month)
    st.write(f"Sabit gider: **{fmt_tl(fixed_this_month)}**")
    st.write(f"Ek harcama: **{fmt_tl(extra_this_month)}**")
    st.write(f"Toplam gider: **{fmt_tl(total_exp)}**")

    available_without_borrow = float(p["holdings"]["cash"]) + projected_sell_cash_in + income
    if (not can_borrow(month)) and (total_exp > available_without_borrow):
        st.error("Ay 1–3'te borç yok. Bu ay giderler (nakit+gelir) sınırını aşıyor → temerrüt olur.")
    st.divider()

    # 2) BORÇ AL
    st.markdown("#### 2) Bankadan Borç Al (1 ay vadeli) — Opsiyonel")
    borrow_amt_input = 0.0
    if can_borrow(month):
        b_list_local = banks_for_month(month)
        bank_map_local = {b["Bank"]: b for b in b_list_local}

        if p.get("loan_bank") is None and bank_map_local:
            p["loan_bank"] = sorted(b_list_local, key=lambda x: x["Loan_Rate"])[0]["Bank"]

        sel_bank = p.get("loan_bank")
        sel_rate = float(bank_map_local[sel_bank]["Loan_Rate"]) if (bank_map_local and sel_bank in bank_map_local) else 0.03
        borrow_max = float(income * CFG["LOAN_MAX_MULT_INCOME"])
        st.caption(
            f"Seçili banka: **{sel_bank}** | Faiz: **{sel_rate*100:.2f}% / ay** | "
            f"Bu ay borç tavanı: **{fmt_tl(borrow_max)}** | "
            f"Bu borç **Ay {month+1} sonunda** geri ödenmek zorundadır."
        )
        borrow_amt_input = safe_number_input("Bu ay alınacak borç (TL)", f"borrow_{name}_{month}", borrow_max, 1000.0)
    else:
        st.caption("Ay 1–3: bankadan borç alınamaz.")
    st.divider()

    # 3) BORÇ ÖDEME (zorunlu)
    st.markdown("#### 3) Borç Ödeme (Ay Sonu)")
    due_now = float(loan_due_amount(p, month))
    if due_now <= 0:
        st.caption("Bu ay vadesi gelen borç yok.")
    else:
        st.caption(f"Bu ay vadesi gelen toplam ödeme: **{fmt_tl(due_now)}** (anapara + 1 aylık faiz)")
        st.number_input(
            "Bu ay ödemek zorunda olduğunuz tutar (TL)",
            min_value=0.0,
            max_value=float(due_now),
            value=float(due_now),
            step=1000.0,
            key=f"repay_{name}_{month}",
            disabled=True,
        )

    st.divider()

    # 4) ALIŞ
    st.markdown("#### 4) Yatırım Alışı (TL)")
    available_for_invest_preview = float(p["holdings"]["cash"]) + projected_sell_cash_in + income - total_exp + float(borrow_amt_input)
    if not can_borrow(month):
        available_for_invest_preview = max(0.0, available_for_invest_preview)
    st.success(f"💰 Bu ay kullanılabilir tahmini MAX nakit: **{fmt_tl(available_for_invest_preview)}**")

    inv_inputs = {}
    max_buy = float(available_for_invest_preview)

    c1, c2 = st.columns(2)
    with c1:
        if "dd" in opened and month >= 4:
            inv_inputs["dd"] = safe_number_input(
                f"Vadesiz ALIŞ (TL) | Komisyon {float(CFG['TX_FEE'])*100:.2f}%",
                f"buy_dd_{name}_{month}",
                max_buy,
                1000.0,
            )
        if "td" in opened and month >= 4:
            inv_inputs["td"] = safe_number_input(
                f"Vadeli ALIŞ (TL) | Komisyon {float(CFG['TX_FEE'])*100:.2f}%",
                f"buy_td_{name}_{month}",
                max_buy,
                1000.0,
            )
        if "fx" in opened:
            inv_inputs["fx"] = safe_number_input(
                f"Döviz ALIŞ (TL) | Maliyet {buy_cost_rate('fx')*100:.2f}%",
                f"buy_fx_{name}_{month}",
                max_buy,
                1000.0,
            )
        if "pm" in opened:
            inv_inputs["pm"] = safe_number_input(
                f"Metal ALIŞ (TL) | Maliyet {buy_cost_rate('pm')*100:.2f}%",
                f"buy_pm_{name}_{month}",
                max_buy,
                1000.0,
            )
    with c2:
        if "eq" in opened:
            inv_inputs["eq"] = safe_number_input(
                f"Hisse ALIŞ (TL) | Maliyet {buy_cost_rate('eq')*100:.2f}%",
                f"buy_eq_{name}_{month}",
                max_buy,
                1000.0,
            )
        if "cr" in opened:
            inv_inputs["cr"] = safe_number_input(
                f"Kripto ALIŞ (TL) | Maliyet {buy_cost_rate('cr')*100:.2f}%",
                f"buy_cr_{name}_{month}",
                max_buy,
                1000.0,
            )

    st.divider()
    btn_label = "✅ Ayı Tamamla" if month < CFG["MONTHS"] else "✅ 12. Ayı Tamamla ve Bitir"

    if st.button(btn_label, use_container_width=True):
        rng = rng_for_player(name, month)

        theft_loss = 0.0
        bank_loss = 0.0
        td_interest = 0.0
        tx_fee_total = 0.0
        spread_cost_total = 0.0
        early_break_penalty_total = 0.0

        bank_map_local = {}
        if month >= 4:
            b_list_local = banks_for_month(month)
            bank_map_local = {b["Bank"]: b for b in b_list_local}

        # A) satış/bozma
        for k, amt in sell_inputs.items():
            amt = float(amt)
            if amt <= 0:
                continue
            amt = min(amt, float(p["holdings"].get(k, 0.0)))
            rate = sell_cost_rate(k)
            fee_part = amt * fee
            spr_part = amt * (float(CFG["SPREAD"].get(k, 0.0)) / 2.0)
            net_cash = amt * (1.0 - rate)

            p["holdings"][k] -= amt
            p["holdings"]["cash"] += max(net_cash, 0.0)

            tx_fee_total += fee_part
            spread_cost_total += spr_part

        if month >= 4 and sell_dd_amt > 0 and sell_dd_bank:
            bal = float(p["dd_accounts"].get(sell_dd_bank, 0.0))
            amt = float(min(sell_dd_amt, bal))
            fee_part = amt * fee
            net_cash = amt * (1.0 - fee)
            p["dd_accounts"][sell_dd_bank] = bal - amt
            p["holdings"]["cash"] += max(net_cash, 0.0)
            tx_fee_total += fee_part

        if month >= 4 and sell_td_amt > 0 and sell_td_bank:
            bal = float(p["td_accounts"].get(sell_td_bank, 0.0))
            amt = float(min(sell_td_amt, bal))
            pen_part = amt * pen
            fee_part = amt * fee
            net_cash = amt * (1.0 - pen - fee)
            p["td_accounts"][sell_td_bank] = bal - amt
            p["holdings"]["cash"] += max(net_cash, 0.0)
            early_break_penalty_total += pen_part
            tx_fee_total += fee_part

        # B) gelir/gider
        p["holdings"]["cash"] += income
        p["holdings"]["cash"] -= total_exp

        # C) borç al (1 ay vadeli) + pop-up
        new_borrow_taken = 0.0
        if can_borrow(month) and float(borrow_amt_input) > 0:
            sel_bank = p.get("loan_bank")
            loan_rate = float(bank_map_local[sel_bank]["Loan_Rate"]) if (bank_map_local and sel_bank in bank_map_local) else 0.03
            new_borrow_taken = float(borrow_amt_input)

            p["holdings"]["cash"] += new_borrow_taken

            due_amt = float(new_borrow_taken * (1.0 + loan_rate))
            p["loans"].append({
                "principal": float(new_borrow_taken),
                "rate": float(loan_rate),
                "bank": str(sel_bank),
                "taken_month": int(month),
                "due_month": int(month + 1),
            })

            st.session_state.loan_popup = {
                "player": str(name),
                "month": int(month),
                "principal": float(new_borrow_taken),
                "rate": float(loan_rate),
                "due": float(due_amt),
            }

        # D) açık -> temerrüt
        if p["holdings"]["cash"] < 0:
            p["holdings"]["cash"] = 0.0
            p["defaulted"] = True
            p["finished"] = True
            st.error("⛔ Bu ay açık oluştu: TEMERRÜT!")
            st.rerun()

        # E) alışlar
        for k, buy_amt in inv_inputs.items():
            buy_amt = float(buy_amt)
            if buy_amt <= 0:
                continue

            p["holdings"]["cash"] -= buy_amt
            if p["holdings"]["cash"] < 0:
                p["holdings"]["cash"] = 0.0
                p["defaulted"] = True
                p["finished"] = True
                st.error("⛔ Alış işlemleri nakdi aştı: TEMERRÜT!")
                st.rerun()

            if k in DEPOSIT_ASSETS and month >= 4:
                fee_part = buy_amt * fee
                net = buy_amt * (1.0 - fee)
                tx_fee_total += fee_part
                if k == "dd":
                    bank = p.get("last_dd_bank") or "Banka 1"
                    p["dd_accounts"][bank] = float(p["dd_accounts"].get(bank, 0.0) + max(net, 0.0))
                else:
                    bank = p.get("last_td_bank") or "Banka 1"
                    p["td_accounts"][bank] = float(p["td_accounts"].get(bank, 0.0) + max(net, 0.0))
            else:
                spr_half = float(CFG["SPREAD"].get(k, 0.0)) / 2.0
                fee_part = buy_amt * fee
                spr_part = buy_amt * spr_half
                net = buy_amt * (1.0 - (fee + spr_half))
                tx_fee_total += fee_part
                spread_cost_total += spr_part
                p["holdings"][k] += max(net, 0.0)

        # F) hırsızlık
        theft_trigger = False
        if month in p.get("theft_months", []) and float(p["holdings"]["cash"]) > 0:
            theft_trigger = True
        else:
            prob = CFG["CASH_THEFT_PROB_STAGE1"] if month <= 3 else CFG["CASH_THEFT_PROB_STAGE2"]
            if float(p["holdings"]["cash"]) > 0 and rng.random() < prob:
                theft_trigger = True

        if theft_trigger and float(p["holdings"]["cash"]) > 0:
            sev = float(rng.uniform(CFG["CASH_THEFT_SEV_MIN"], CFG["CASH_THEFT_SEV_MAX"]))
            theft_loss = float(p["holdings"]["cash"]) * sev
            p["holdings"]["cash"] -= theft_loss
            st.session_state.theft_popup = {
                "loss": float(theft_loss),
                "remain": float(p["holdings"]["cash"]),
                "month": int(month),
                "player": str(name),
            }

        # G) banka olayı + vadeli faiz
        if month >= 4 and bank_map_local:
            for bank, bal in list(p["dd_accounts"].items()):
                if float(bal) > 0 and bank in bank_map_local and rng.random() < float(CFG["BANK_INCIDENT_PROB"]):
                    guar = float(bank_map_local[bank]["Guarantee"])
                    loss = float(bal * (1.0 - guar))
                    p["dd_accounts"][bank] = float(max(0.0, bal - loss))
                    bank_loss += loss

            for bank, bal in list(p["td_accounts"].items()):
                if float(bal) > 0 and bank in bank_map_local and rng.random() < float(CFG["BANK_INCIDENT_PROB"]):
                    guar = float(bank_map_local[bank]["Guarantee"])
                    loss = float(bal * (1.0 - guar))
                    p["td_accounts"][bank] = float(max(0.0, bal - loss))
                    bank_loss += loss

            for bank, bal in list(p["td_accounts"].items()):
                if float(bal) > 0 and bank in bank_map_local:
                    before = float(bal)
                    rate = float(bank_map_local[bank]["TD_Rate"])
                    after = float(before * (1.0 + rate))
                    p["td_accounts"][bank] = after
                    td_interest += (after - before)

        # H) piyasa getirileri
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

        # I) vadesi gelen borç ödemesi (zorunlu)
        due_now_actual = float(loan_due_amount(p, month))
        repay_done = 0.0
        if due_now_actual > 0:
            if float(p["holdings"]["cash"]) + 1e-9 < due_now_actual:
                p["defaulted"] = True
                p["finished"] = True
                st.error("⛔ Vadesi gelen 1 aylık borç ödenemedi: TEMERRÜT!")
                st.rerun()
            p["holdings"]["cash"] -= due_now_actual
            repay_done = due_now_actual
            remove_due_loans(p, month)

        # J) log
        end_cash = float(p["holdings"]["cash"])
        end_inv = float(total_investments(p))
        end_total_debt_view = float(total_debt_display(p, month))
        end_total = float(end_cash + end_inv - loan_outstanding_principal(p))

        p["log"].append({
            "Ay": int(month),
            "Aşama": stage_label(month),
            "FiyatlarGenelDuzeyi": float(pgl),
            "Gelir(TL)": float(income),
            "SabitGider(TL)": float(fixed_this_month),
            "EkHarcama(TL)": float(extra_this_month),
            "SatışNetNakitGirişi(TL)": float(projected_sell_cash_in),
            "YeniBorç(1ay)(TL)": float(new_borrow_taken),
            "VadesiGelenBorçÖdeme(TL)": float(repay_done),
            "İşlemÜcreti(TL)": float(tx_fee_total),
            "SpreadMaliyeti(TL)": float(spread_cost_total),
            "VadeliBozmaCezası(TL)": float(early_break_penalty_total),
            "VadeliFaizGeliri(TL)": float(td_interest),
            "BankaKayıp(TL)": float(bank_loss),
            "NakitHırsızlıkKayıp(TL)": float(theft_loss),
            "DönemSonuNakit(TL)": float(end_cash),
            "DönemSonuYatırım(TL)": float(end_inv),
            "Borç(Anapara)(TL)": float(loan_outstanding_principal(p)),
            "Borç(Görünüm)(TL)": float(end_total_debt_view),
            "ToplamServet(TL)": float(end_total),
        })

        # K) PGL update (sabit gider + ek harcama etkilenir)
        if month < CFG["MONTHS"]:
            next_rng = rng_for_player(name, month + 1)

            pgl_prev = float(p["pgl_current"])
            fixed_prev = float(p["fixed_current"])
            extra_prev = float(p["extra_current"])

            pgl_next, realized_delta = next_pgl(pgl_prev, next_rng)

            fixed_next = float(max(0.0, fixed_prev * (1.0 + realized_delta)))
            extra_next = float(max(0.0, extra_prev * (1.0 + realized_delta)))

            p["pgl_current"] = float(pgl_next)
            p["fixed_current"] = float(fixed_next)
            p["extra_current"] = float(extra_next)

            st.session_state.pgl_popup = {
                "player": str(name),
                "from_month": int(month),
                "to_month": int(month + 1),
                "pgl_prev": float(pgl_prev),
                "pgl_new": float(pgl_next),
                "step_used": float(realized_delta),
                "fixed_prev": float(fixed_prev),
                "fixed_new": float(fixed_next),
                "extra_prev": float(extra_prev),
                "extra_new": float(extra_next),
            }

        # L) ay ilerlet
        if month >= CFG["MONTHS"]:
            p["finished"] = True
        else:
            p["month"] += 1

        st.rerun()

# =========================
# ✅ SAYFANIN EN SONU: GRAFİK
# =========================
st.divider()
st.subheader("📈 Toplam Servet (Net) — Aylar İçinde Değişim (Grafik)")

if p["log"]:
    df = pd.DataFrame(p["log"]).copy()
    df_plot = df[["Ay", "ToplamServet(TL)"]].sort_values("Ay")
    df_plot = df_plot.rename(columns={"ToplamServet(TL)": "Toplam Servet (Net) - TL"})
    st.line_chart(df_plot.set_index("Ay")["Toplam Servet (Net) - TL"])
else:
    st.info("Grafiğin oluşması için en az 1 ayı tamamlayın.")
