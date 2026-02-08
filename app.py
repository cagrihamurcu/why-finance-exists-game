import streamlit as st
import numpy as np
import pandas as pd

st.set_page_config(page_title="Borsa Uygulamaları - 1. Hafta Oyunu", layout="wide")

# =========================
# SABİT (ÖĞRENCİ DEĞİŞTİREMEZ)
# =========================
DEFAULT_MONTHLY_INCOME = 60000
START_FIXED_COST = 30000  # 1. ay sabit gider

# =========================
# OYUN PARAMETRELERİ
# =========================
CFG = {
    "MONTHS": 12,

    # ✅ Fiyatlar genel düzeyi: her ay +/- (%1 ile %5 arası adım)
    # ✅ oran her zaman %1–%5 bandında kalır
    "PGL_MIN_STEP": 0.01,
    "PGL_MAX_STEP": 0.05,
    "PGL_FLOOR": 0.01,
    "PGL_CAP": 0.05,

    "LOAN_ACTIVE_FROM_MONTH": 4,

    # Nakit hırsızlığı
    "CASH_THEFT_PROB_STAGE1": 0.12,
    "CASH_THEFT_PROB_STAGE2": 0.05,
    "CASH_THEFT_SEV_MIN": 0.10,
    "CASH_THEFT_SEV_MAX": 0.35,

    # Banka olayı (banka güvence oranına göre kısmi kayıp)
    "BANK_INCIDENT_PROB": 0.02,

    # Vadeli faiz aralığı (aylık)
    "TD_RATE_MIN": 0.0070,
    "TD_RATE_MAX": 0.0140,

    # Güvence aralığı
    "GUAR_MIN": 0.70,
    "GUAR_MAX": 0.99,

    # Banka kredi faizi (aylık)
    "LOAN_RATE_BASE": 0.018,
    "LOAN_RATE_ADD": 0.030,
    "LOAN_RATE_NOISE": 0.002,
    "LOAN_MAX_MULT_INCOME": 3.0,

    # Vadeli bozma cezası
    "EARLY_BREAK_PENALTY": 0.01,

    # İşlem komisyonu
    "TX_FEE": 0.005,

    # Spread (toplam)
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
# YARDIMCI FONKSİYONLAR
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

    realized_delta = float(new_pgl - prev_pgl)
    return new_pgl, realized_delta

def bank_count_for_month(month: int) -> int:
    if month < 4:
        return 0
    return min(2 + (month - 4), 8)

def banks_for_month(month: int):
    n = bank_count_for_month(month)
    if n == 0:
        return []

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

def dd_total(p: dict) -> float:
    return float(sum(p.get("dd_accounts", {}).values()))

def td_total(p: dict) -> float:
    return float(sum(p.get("td_accounts", {}).values()))

def other_investments_total(p: dict) -> float:
    return float(sum(p["holdings"].get(k, 0.0) for k in RISK_ASSETS))

def total_investments(p: dict) -> float:
    return float(dd_total(p) + td_total(p) + other_investments_total(p))

def net_wealth(p: dict) -> float:
    return float(p["holdings"]["cash"] + total_investments(p) - float(p.get("debt", 0.0)))

def dd_breakdown_df(p: dict) -> pd.DataFrame:
    rows = []
    for bank, bal in p.get("dd_accounts", {}).items():
        bal = float(bal)
        if bal > 0:
            rows.append({"Banka": bank, "Vadesiz Bakiye (TL)": round(bal, 0)})
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("Vadesiz Bakiye (TL)", ascending=False)

def td_breakdown_df(p: dict) -> pd.DataFrame:
    rows = []
    for bank, bal in p.get("td_accounts", {}).items():
        bal = float(bal)
        if bal > 0:
            rows.append({"Banka": bank, "Vadeli Bakiye (TL)": round(bal, 0)})
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("Vadeli Bakiye (TL)", ascending=False)

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

def update_weighted_debt_rate(p: dict, add_debt: float, add_rate: float):
    add_debt = float(max(0.0, add_debt))
    if add_debt <= 0:
        return
    old_debt = float(p.get("debt", 0.0))
    old_rate = float(p.get("debt_rate", 0.0))
    new_debt = old_debt + add_debt
    if old_debt <= 0:
        p["debt_rate"] = float(add_rate)
    else:
        p["debt_rate"] = float((old_debt * old_rate + add_debt * add_rate) / new_debt)

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
if "bank_state" not in st.session_state:
    st.session_state.bank_state = {}

def get_player(name: str) -> dict:
    if name not in st.session_state.players:
        theft_rng = np.random.default_rng((hash(name) % 10000) + st.session_state.seed)
        theft_months = sorted(
            theft_rng.choice(np.arange(1, CFG["MONTHS"] + 1), size=3, replace=False).tolist()
        )

        # ✅ Başlangıç PGL: %1–%5 random
        pgl0 = float(np.random.default_rng((hash(name) % 10000) + st.session_state.seed + 777).uniform(
            CFG["PGL_FLOOR"], CFG["PGL_CAP"]
        ))

        st.session_state.players[name] = {
            "month": 1,
            "finished": False,
            "defaulted": False,

            "debt": 0.0,
            "debt_rate": 0.0,
            "loan_bank": None,

            "holdings": {"cash": 0.0, "fx": 0.0, "pm": 0.0, "eq": 0.0, "cr": 0.0},
            "dd_accounts": {},
            "td_accounts": {},

            "income_fixed": float(DEFAULT_MONTHLY_INCOME),
            "fixed_current": float(START_FIXED_COST),
            "pgl_current": float(pgl0),

            "last_dd_bank": None,
            "last_td_bank": None,

            "theft_months": theft_months,
            "log": [],
        }
    return st.session_state.players[name]

# =========================
# SIDEBAR (KISA BİLGİ PANELİ)
# =========================
with st.sidebar:
    st.header("ℹ️ Oyun Bilgisi")
    st.write(
        "- **Gelir sabittir.**\n"
        "- **Fiyatlar Genel Düzeyi** her ay bir **değişim** (artış/azalış) gösterir.\n"
        "- **Sabit giderler**, bu değişime göre **bir sonraki ay** artar ya da azalır.\n"
        "- **4. aydan itibaren** finansal kurumlar (bankalar vb.) devreye girer ve seçenekler genişler."
    )
    st.divider()
    if st.button("🧹 Oyunu Sıfırla"):
        st.session_state.clear()
        st.rerun()

st.title("🎮 1. Hafta Oyunu: Neden Finansal Piyasalar ve Kurumlarla İlgileniyoruz?")

# =========================
# POP-UP CSS
# =========================
def _overlay_style():
    st.markdown(
        """
        <style>
        .ovl {
            position: fixed;
            top: 0; left: 0;
            width: 100vw; height: 100vh;
            background: rgba(0,0,0,0.35);
            z-index: 9999;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 18px;
        }
        .card {
            background: #ffffff;
            border-radius: 18px;
            padding: 18px;
            max-width: 560px;
            width: 100%;
            box-shadow: 0 18px 60px rgba(0,0,0,0.20);
            border: 2px solid rgba(0,0,0,0.06);
        }
        .titleRed { font-size: 22px; font-weight: 900; color:#b30000; margin-bottom: 6px; }
        .titleBlue { font-size: 22px; font-weight: 900; color:#0b4aa2; margin-bottom: 6px; }
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
    step_used = float(pop.get("step_used", 0.0))  # realized delta (signed)
    fixed_prev = float(pop.get("fixed_prev", 0.0))
    fixed_new = float(pop.get("fixed_new", 0.0))

    if step_used > 0:
        msg = "Bu ay **artış adımı (+)** uygulandı → bir sonraki ay sabit giderler **arttı**."
        arrow = "⬆️"
    elif step_used < 0:
        msg = "Bu ay **azalış adımı (−)** uygulandı → bir sonraki ay sabit giderler **azaldı**."
        arrow = "⬇️"
    else:
        msg = "Band sınırına çarptığı için bu ay adım **0** olarak gerçekleşti."
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
                <div style="margin-top:10px;"><b>Fiyatlar Genel Düzeyi:</b> {fmt_pct(pgl_prev)} → <b>{fmt_pct(pgl_new)}</b></div>
                <div><b>Bu Ay Değişim:</b> <b>{step_text}</b></div>
                <div><b>Sabit Gider:</b> {fmt_tl(fixed_prev)} → <b>{fmt_tl(fixed_new)}</b></div>
                <div style="margin-top:10px;">{msg}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        if st.button("Kapat ✖", use_container_width=True, key=f"close_pgl_fallback_{player}_{to_month}"):
            st.session_state.pgl_popup = None
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

# pop-up'ları üstte render et
render_theft_modal()
render_pgl_modal()

# =========================
# OYUN BİTTİ
# =========================
if p.get("finished", False):
    st.subheader("✅ Oyun Sonu")
    if p.get("defaulted", False):
        st.error("⛔ Oyun bitti: Ay 1–3 döneminde açık oluştu (borç yok) → temerrüt.")
    else:
        st.success("✅ Oyun bitti: 12. ay tamamlandı.")

    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Nakit", fmt_tl(p["holdings"]["cash"]))
    a2.metric("Yatırım (Toplam)", fmt_tl(total_investments(p)))
    a3.metric("Borç", fmt_tl(p["debt"]))
    a4.metric("Servet (Net)", fmt_tl(net_wealth(p)))
    st.stop()

# =========================
# AY PANELİ (ÖZET)
# =========================
income = float(p["income_fixed"])
pgl = float(p["pgl_current"])
fixed_this_month = float(p["fixed_current"])

st.markdown(f"### 📅 Ay {month}/{CFG['MONTHS']}  —  Aşama: **{stage_label(month)}**")
st.progress((month - 1) / CFG["MONTHS"])

r1a, r1b, r1c, r1d = st.columns(4)
r1a.metric("Net Servet", fmt_tl(net_wealth(p)))
r1b.metric("Nakit", fmt_tl(p["holdings"]["cash"]))
r1c.metric("Yatırım (Toplam)", fmt_tl(total_investments(p)))
r1d.metric("Borç", fmt_tl(p["debt"]))

r2a, r2b, r2c, r2d = st.columns(4)
r2a.metric("Fiyatlar Genel Düzeyi (Bu Ay)", fmt_pct(pgl))
r2b.metric("Bu Ay Sabit Gider", fmt_tl(fixed_this_month))
r2c.metric("Gelir (Sabit)", fmt_tl(income))
r2d.metric("Borç Mekanizması", "Açık (Banka)" if can_borrow(month) else "Kapalı (Ay1-3)")

# ✅ Sekmeler: Oyun Özeti eklendi
tab_summary, tab_game, tab_banks, tab_log = st.tabs(
    ["📌 Oyun Özeti", "🎯 Karar Ekranı", "🏦 Bankalar & Mevduat", "📒 Geçmiş"]
)

# -------------------------------------------------
# OYUN ÖZETİ + NET SERVET GRAFİĞİ
# -------------------------------------------------
with tab_summary:
    st.subheader("📌 Oyun Özeti")
    st.write(
        "Bu sayfada, oyunun temel mantığını hatırlayıp **toplam servetin (net)** aylar içindeki değişimini görebilirsiniz."
    )

    # Net servet serisi: log varsa logdan; yoksa şu anki durumu tek nokta olarak göster
    if p["log"]:
        df = pd.DataFrame(p["log"]).copy()
        # güvenli kolon adı
        if "ToplamServet(TL)" in df.columns:
            df_plot = df[["Ay", "ToplamServet(TL)"]].sort_values("Ay")
            df_plot = df_plot.rename(columns={"ToplamServet(TL)": "Toplam Servet (Net) - TL"})
        else:
            df_plot = df[["Ay"]].sort_values("Ay")
            df_plot["Toplam Servet (Net) - TL"] = np.nan

        # metrik: başlangıç ve son
        first_val = float(df_plot["Toplam Servet (Net) - TL"].iloc[0])
        last_val = float(df_plot["Toplam Servet (Net) - TL"].iloc[-1])
        delta = last_val - first_val

        cA, cB, cC = st.columns(3)
        cA.metric("Başlangıç (İlk kayıt)", fmt_tl(first_val))
        cB.metric("Son (En güncel kayıt)", fmt_tl(last_val), delta=fmt_tl(delta))
        cC.metric("Kayıtlı Ay Sayısı", str(int(df_plot.shape[0])))

        st.markdown("#### 📈 Toplam Servet (Net) Zaman Serisi")
        st.line_chart(df_plot.set_index("Ay")["Toplam Servet (Net) - TL"])

        with st.expander("📋 Özet Tablo (Ay - Toplam Servet)", expanded=False):
            st.dataframe(df_plot, use_container_width=True, hide_index=True, height=260)

    else:
        # henüz kayıt yok: tek nokta
        current_net = float(net_wealth(p))
        st.info("Henüz geçmiş kaydı yok. İlk ayı tamamlayınca grafik oluşacak.")
        df_plot = pd.DataFrame({"Ay": [0], "Toplam Servet (Net) - TL": [current_net]})
        st.line_chart(df_plot.set_index("Ay")["Toplam Servet (Net) - TL"])

# -------------------------------------------------
# BANKALAR & MEVDUAT
# -------------------------------------------------
with tab_banks:
    st.subheader("🏦 Bankalar ve Mevduat Dökümü")

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
            st.caption(f"Kredi faizi: **{bank_map[p['loan_bank']]['Loan_Rate']*100:.2f}% / ay**")

        st.divider()
        x1, x2 = st.columns(2)
        with x1:
            ddf = dd_breakdown_df(p)
            st.write("**Vadesiz:**")
            st.dataframe(ddf, use_container_width=True, hide_index=True, height=240) if not ddf.empty else st.caption("Yok.")
        with x2:
            tdf = td_breakdown_df(p)
            st.write("**Vadeli:**")
            st.dataframe(tdf, use_container_width=True, hide_index=True, height=240) if not tdf.empty else st.caption("Yok.")

# -------------------------------------------------
# GEÇMİŞ — Kaydırmasız
# -------------------------------------------------
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
                                if "Fiyatlar" in str(k) or "FaizOranı" in str(k):
                                    st.markdown(f"**{k}:** {fmt_pct(float(v))}")
                                else:
                                    st.markdown(f"**{k}:** {fmt_tl(float(v))}")
                            else:
                                st.markdown(f"**{k}:** {v}")

                render_kv(left_items, cols[0])
                render_kv(right_items, cols[1])

# -------------------------------------------------
# KARAR EKRANI
# -------------------------------------------------
with tab_game:
    st.subheader("🎯 Bu Ay Kararları")

    fee = float(CFG["TX_FEE"])

    # 1) BÜTÇE
    available_without_borrow = float(p["holdings"]["cash"]) + income
    extra_max = int(max(0.0, available_without_borrow - fixed_this_month)) if not can_borrow(month) else int(income * 3)
    extra_default = min(5000, max(0, extra_max))
    extra = st.number_input("Ek Harcama", 0, max(0, extra_max), extra_default, 1000, key=f"extra_{name}_{month}")

    total_exp = fixed_this_month + float(extra)
    st.write(f"Toplam gider: **{fmt_tl(total_exp)}**")
    if (not can_borrow(month)) and (total_exp > available_without_borrow):
        st.error("Ay 1–3'te borç yok. Bu bütçe (nakit+gelir) sınırını aşıyor → temerrüt olur.")

    # 1.5) BORÇ
    borrow_amt_input = 0.0
    if can_borrow(month):
        b_list_local = banks_for_month(month)
        bank_map_local = {b["Bank"]: b for b in b_list_local}
        if p.get("loan_bank") is None and bank_map_local:
            p["loan_bank"] = sorted(b_list_local, key=lambda x: x["Loan_Rate"])[0]["Bank"]

        sel_rate = float(bank_map_local[p["loan_bank"]]["Loan_Rate"]) if (bank_map_local and p.get("loan_bank") in bank_map_local) else 0.03
        borrow_max = float(income * CFG["LOAN_MAX_MULT_INCOME"])
        st.caption(f"Kredi faizi: **{sel_rate*100:.2f}% / ay** | Tavan: **{fmt_tl(borrow_max)}**")
        borrow_amt_input = safe_number_input("Bu ay borç (TL)", f"borrow_{name}_{month}", borrow_max, 1000.0)
    else:
        st.caption("Ay 1–3: borç yok.")

    # 2) YATIRIM
    available_for_invest_preview = float(p["holdings"]["cash"]) + income - total_exp + float(borrow_amt_input)
    if not can_borrow(month):
        available_for_invest_preview = max(0.0, available_for_invest_preview)

    st.success(f"💰 Yatırım için MAX nakit: **{fmt_tl(available_for_invest_preview)}**")
    inv_inputs = {}
    max_buy = float(available_for_invest_preview)

    c1, c2 = st.columns(2)
    with c1:
        if "dd" in opened and month >= 4:
            inv_inputs["dd"] = safe_number_input(f"Vadesiz ALIŞ (TL) | Komisyon {fee*100:.2f}%", f"buy_dd_{name}_{month}", max_buy, 1000.0)
        if "td" in opened and month >= 4:
            inv_inputs["td"] = safe_number_input(f"Vadeli ALIŞ (TL) | Komisyon {fee*100:.2f}%", f"buy_td_{name}_{month}", max_buy, 1000.0)
        if "fx" in opened:
            inv_inputs["fx"] = safe_number_input(f"Döviz ALIŞ (TL) | Maliyet {buy_cost_rate('fx')*100:.2f}%", f"buy_fx_{name}_{month}", max_buy, 1000.0)
        if "pm" in opened:
            inv_inputs["pm"] = safe_number_input(f"Metal ALIŞ (TL) | Maliyet {buy_cost_rate('pm')*100:.2f}%", f"buy_pm_{name}_{month}", max_buy, 1000.0)
    with c2:
        if "eq" in opened:
            inv_inputs["eq"] = safe_number_input(f"Hisse ALIŞ (TL) | Maliyet {buy_cost_rate('eq')*100:.2f}%", f"buy_eq_{name}_{month}", max_buy, 1000.0)
        if "cr" in opened:
            inv_inputs["cr"] = safe_number_input(f"Kripto ALIŞ (TL) | Maliyet {buy_cost_rate('cr')*100:.2f}%", f"buy_cr_{name}_{month}", max_buy, 1000.0)

    # ✅ AYI TAMAMLA
    btn_label = "✅ Ayı Tamamla" if month < CFG["MONTHS"] else "✅ 12. Ayı Tamamla ve Bitir"
    if st.button(btn_label, use_container_width=True):
        rng = rng_for_player(name, month)

        theft_loss = 0.0
        td_interest = 0.0
        tx_fee_total = 0.0
        spread_cost_total = 0.0
        early_break_penalty_total = 0.0
        new_borrow_taken = 0.0

        # B) GELİR / GİDER
        p["holdings"]["cash"] += income
        p["holdings"]["cash"] -= total_exp

        # C) İSTEĞE BAĞLI BORÇ
        bank_map_local = {}
        if month >= 4:
            b_list_local = banks_for_month(month)
            bank_map_local = {b["Bank"]: b for b in b_list_local}

        if can_borrow(month) and float(borrow_amt_input) > 0:
            loan_rate = float(bank_map_local[p["loan_bank"]]["Loan_Rate"]) if (bank_map_local and p.get("loan_bank") in bank_map_local) else 0.03
            new_borrow_taken = float(borrow_amt_input)
            p["debt"] += new_borrow_taken
            update_weighted_debt_rate(p, new_borrow_taken, loan_rate)
            p["holdings"]["cash"] += new_borrow_taken

        # D) Açık oluşursa
        if p["holdings"]["cash"] < 0:
            deficit = -float(p["holdings"]["cash"])
            if not can_borrow(month):
                p["holdings"]["cash"] = 0.0
                p["defaulted"] = True
                p["finished"] = True
                st.error("⛔ Ay 1–3 döneminde açık oluştu: TEMERRÜT!")
                st.rerun()
            else:
                loan_rate = float(bank_map_local[p["loan_bank"]]["Loan_Rate"]) if (bank_map_local and p.get("loan_bank") in bank_map_local) else 0.03
                p["debt"] += deficit
                update_weighted_debt_rate(p, deficit, loan_rate)
                p["holdings"]["cash"] = 0.0

        # E) ALIŞLAR
        for k, buy_amt in inv_inputs.items():
            buy_amt = float(buy_amt)
            if buy_amt <= 0:
                continue

            p["holdings"]["cash"] -= buy_amt
            if p["holdings"]["cash"] < 0:
                deficit2 = -float(p["holdings"]["cash"])
                if can_borrow(month):
                    loan_rate = float(bank_map_local[p["loan_bank"]]["Loan_Rate"]) if (bank_map_local and p.get("loan_bank") in bank_map_local) else 0.03
                    p["debt"] += deficit2
                    update_weighted_debt_rate(p, deficit2, loan_rate)
                    p["holdings"]["cash"] = 0.0
                else:
                    p["holdings"]["cash"] = 0.0
                    p["defaulted"] = True
                    p["finished"] = True
                    st.error("⛔ Ay 1–3 döneminde yatırım yüzünden açık oluştu: TEMERRÜT!")
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

        # F) NAKİT HIRSIZLIK
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

        # G) VADELİ FAİZ
        if month >= 4 and bank_map_local:
            for bank, bal in list(p["td_accounts"].items()):
                if float(bal) > 0 and bank in bank_map_local:
                    before = float(bal)
                    rate = float(bank_map_local[bank]["TD_Rate"])
                    after = float(before * (1.0 + rate))
                    p["td_accounts"][bank] = after
                    td_interest += (after - before)

        # H) PİYASA GETİRİLERİ
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

        # I) BORÇ FAİZİ
        if can_borrow(month) and float(p["debt"]) > 0:
            p["debt"] *= (1.0 + float(p.get("debt_rate", 0.03)))

        # J) LOG
        end_cash = float(p["holdings"]["cash"])
        end_inv = float(dd_total(p) + td_total(p) + other_investments_total(p))
        end_debt = float(p["debt"])
        end_total = float(end_cash + end_inv - end_debt)

        p["log"].append({
            "Ay": month,
            "Aşama": stage_label(month),
            "FiyatlarGenelDuzeyi": float(pgl),
            "Gelir(TL)": float(income),
            "SabitGider(TL)": float(fixed_this_month),
            "EkHarcama(TL)": float(extra),
            "YeniBorç(TL)": float(new_borrow_taken),
            "İşlemÜcreti(TL)": float(tx_fee_total),
            "SpreadMaliyeti(TL)": float(spread_cost_total),
            "VadeliBozmaCezası(TL)": float(early_break_penalty_total),
            "VadeliFaizGeliri(TL)": float(td_interest),
            "NakitHırsızlıkKayıp(TL)": float(theft_loss),
            "DönemSonuNakit(TL)": float(end_cash),
            "DönemSonuYatırım(TL)": float(end_inv),
            "DönemSonuBorç(TL)": float(end_debt),
            "ToplamServet(TL)": float(end_total),
        })

        # K) ✅ PGL GÜNCELLE + SABİT GİDERİ
        if month < CFG["MONTHS"]:
            next_rng = rng_for_player(name, month + 1)

            pgl_prev = float(p["pgl_current"])
            fixed_prev = float(p["fixed_current"])

            pgl_next, realized_delta = next_pgl(pgl_prev, next_rng)

            fixed_next = float(fixed_prev * (1.0 + realized_delta))
            fixed_next = float(max(0.0, fixed_next))

            p["pgl_current"] = float(pgl_next)
            p["fixed_current"] = float(fixed_next)

            st.session_state.pgl_popup = {
                "player": str(name),
                "from_month": int(month),
                "to_month": int(month + 1),
                "pgl_prev": float(pgl_prev),
                "pgl_new": float(pgl_next),
                "step_used": float(realized_delta),
                "fixed_prev": float(fixed_prev),
                "fixed_new": float(fixed_next),
            }

        # L) ilerlet / bitir
        if month >= CFG["MONTHS"]:
            p["finished"] = True
        else:
            p["month"] += 1

        st.rerun()
