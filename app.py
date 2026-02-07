import streamlit as st
import numpy as np
import pandas as pd

st.set_page_config(page_title="1. Hafta Oyunu — Finans Neden Var?", layout="wide")

CFG = {
    "MONTHS": 12,
    "NO_INSTITUTIONS_UNTIL": 3,

    "INFLATION_M": 0.020,

    "CASH_LOSS_PROB": 0.05,
    "CASH_LOSS_SEV": 0.10,

    "DD_RATE_M": 0.002,
    "TD_RATE_M": 0.010,
    "TD_EARLY_WITHDRAW_PENALTY": 0.015,

    "EQ_MU": 0.012,
    "EQ_SIG": 0.055,

    "CR_MU": 0.020,
    "CR_SIG": 0.120,

    "PM_MU": 0.008,
    "PM_SIG": 0.030,

    "FX_MU": 0.010,
    "FX_SIG": 0.040,

    "CRISIS_MONTH": 6,
    "CRISIS_EQ_HIT": -0.10,
    "CRISIS_CR_HIT": -0.18,
    "CRISIS_FX_BOOST": +0.06,
    "CRISIS_PM_BOOST": +0.03,

    "NEG_CASHFLOW_PENALTY": 150_000.0,
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
    if "holdings" not in pl: pl["holdings"] = {k: 0.0 for k in ASSET_LABELS.keys()}
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

def apply_returns(holdings: dict, name: str, month: int):
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
            "eq_r": eq_r, "cr_r": cr_r, "pm_r": pm_r, "fx_r": fx_r,
            "infl": infl,
            "cash_loss": cash_loss, "cash_loss_amt": cash_loss_amt,
        }
    else:
        shocks = {
            "crisis": crisis,
            "infl": infl,
            "cash_loss": cash_loss, "cash_loss_amt": cash_loss_amt,
        }

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
st.caption("Gelir → Gider → Tasarruf → Yatırım akışı: kurumlar yokken kısıt ve maliyet, kurumlar varken ürün çeşitliliği ve risk yönetimi.")

top1, top2 = st.columns([1, 3])
with top1:
    if st.button("🧹 Oyunu Sıfırla"):
        st.session_state.clear()
        st.success("Sıfırlandı.")
        st.rerun()
with top2:
    st.caption("Kod güncellemesi sonrası sorun olursa 'Oyunu Sıfırla'ya basın.")

left, right = st.columns([2.2, 1])

with left:
    name = st.text_input("Oyuncu Adı (takma isim)", placeholder="örn. T3_Ayşe / Mehmet / Takım-4")
    if not name:
        st.stop()

    pl = get_player(name)

    if not pl["scenario_ok"]:
        st.subheader("📌 Senaryo (kısa)")
        st.markdown(
            f"""
- Oyun **{CFG['MONTHS']} ay** sürer.  
- **Ay 1–{CFG['NO_INSTITUTIONS_UNTIL']}**: Finansal kurum yok → sadece **nakit** (enflasyon + kayıp riski).  
- **Ay {CFG['NO_INSTITUTIONS_UNTIL']+1}+**: Kurumlar devrede → mevduat + hisse/kripto/metal/döviz.  
- **Ay {CFG['CRISIS_MONTH']}**: Makro kriz.

Her ay: Gelir → gider → tasarruf → yatırım → ay sonu şokları.
            """
        )
        if st.button("✅ Okudum, başla"):
            pl["scenario_ok"] = True
            st.rerun()
        st.stop()

    if pl["income"] is None:
        st.subheader("1) Başlangıç Ayarları (bir kez)")
        income = st.number_input("Aylık Gelir (TL)", min_value=20_000, max_value=500_000, value=60_000, step=5_000)
        fixed = st.number_input("Aylık Sabit Gider (TL)", min_value=10_000, max_value=400_000, value=30_000, step=5_000)
        if st.button("✅ Kaydet ve Oyuna Başla"):
            pl["income"] = float(income)
            pl["fixed_exp"] = float(fixed)
            pl["holdings"] = {k: 0.0 for k in ASSET_LABELS.keys()}
            pl["wealth"] = 0.0
            st.rerun()
        st.stop()

    month = int(pl["month"])
    st.subheader(f"📅 Ay {month} / {CFG['MONTHS']}")
    st.progress((month - 1) / CFG["MONTHS"])

    if month <= CFG["NO_INSTITUTIONS_UNTIL"]:
        st.info("📰 Kurum yok: sadece nakit.")
    elif month == CFG["NO_INSTITUTIONS_UNTIL"] + 1:
        st.success("🏦 Kurumlar devrede: ürünler açıldı.")
    elif month == CFG["CRISIS_MONTH"]:
        st.warning("🚨 Makro kriz ayı.")
    else:
        st.caption("Bu ay bütçe ve yatırım kararınızı verin.")

    st.write("### Mevcut Varlıklarınız (TL)")
    h = pl["holdings"]
    cur_df = pd.DataFrame([{"Varlık": ASSET_LABELS[k], "Tutar (TL)": v} for k, v in h.items() if abs(v) > 1e-6])
    if cur_df.empty:
        st.caption("Henüz varlık yok.")
    else:
        st.dataframe(cur_df, use_container_width=True, hide_index=True)

    st.metric("Toplam Servet (TL)", f"{total_wealth(pl['holdings']):,.0f}".replace(",", "."))

    st.divider()
    st.subheader("2) Bu Ay Bütçe Kararı")
    income = pl["income"]
    fixed = pl["fixed_exp"]
    st.write(f"- Gelir: **{income:,.0f} TL**".replace(",", "."))
    st.write(f"- Sabit gider: **{fixed:,.0f} TL**".replace(",", "."))
    discretionary = st.number_input("Ek harcama (TL)", min_value=0, max_value=int(income), value=5_000, step=1_000)
    saving_rate = st.slider("Tasarruf oranı (%)", 0, 80, 20, 5)

    st.divider()
    st.subheader("3) Tasarrufu Yatırıma Dağıt (Bu ay)")

    alloc = {}
    alloc_sum = 0

    if not institutions_available(month):
        st.caption("Kurum yok → tasarruf otomatik nakitte kalır.")
    else:
        st.caption("Sadece sayı girin. Yan tarafta otomatik % gösterilir. Kalan otomatik Nakit (elde).")
        assets = ["dd", "td", "eq", "cr", "pm", "fx"]

        # Her satır: [etiket] [sayı] [%]
        for k in assets:
            c1, c2, c3 = st.columns([2.5, 1.2, 0.6])
            with c1:
                st.write(ASSET_LABELS[k])
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
        st.write(f"Toplam (nakit hariç): **{alloc_sum}** %")

        if alloc_sum < 100:
            st.info(f"Kalan **{100-alloc_sum} %** otomatik olarak **{ASSET_LABELS['cash']}**'te kalacak.")
        elif alloc_sum > 100:
            st.warning("Toplam 100'ü geçti. Oranlar otomatik olarak 100'e ölçeklenecek (normalize).")

    if st.button("✅ Ayı Çalıştır (Bütçe + Yatırım + Şoklar)"):
        # 1) Gelir -> nakit
        pl["holdings"]["cash"] += float(income)

        # 2) Gider ödeme
        total_exp = float(fixed) + float(discretionary)
        if pl["holdings"]["cash"] >= total_exp:
            pl["holdings"]["cash"] -= total_exp
            cashflow_ok = True
        else:
            cashflow_ok = False
            shortage = total_exp - pl["holdings"]["cash"]
            pl["holdings"]["cash"] = 0.0

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
                if k == "td":
                    pl["penalty"] += take * CFG["TD_EARLY_WITHDRAW_PENALTY"]

            if shortage > 0:
                pl["penalty"] += CFG["NEG_CASHFLOW_PENALTY"]

        # 3) Tasarruf
        cash_after_exp = pl["holdings"]["cash"]
        save_amt = cash_after_exp * (saving_rate / 100.0)
        pl["holdings"]["cash"] -= save_amt

        # 4) Dağıtım (otomatik kalan nakit + normalize)
        if not institutions_available(month):
            pl["holdings"]["cash"] += save_amt
        else:
            alloc_sum = sum(alloc.values())

            if alloc_sum <= 0:
                pl["holdings"]["cash"] += save_amt
            else:
                # normalize if >100
                if alloc_sum > 100:
                    alloc_adj = {k: (pct / alloc_sum) * 100 for k, pct in alloc.items()}
                else:
                    alloc_adj = dict(alloc)

                remaining_pct = max(0.0, 100.0 - sum(alloc_adj.values()))

                for k, pct in alloc_adj.items():
                    pl["holdings"][k] += save_amt * (pct / 100.0)

                if remaining_pct > 0:
                    pl["holdings"]["cash"] += save_amt * (remaining_pct / 100.0)

        # 5) Getiriler
        shocks = apply_returns(pl["holdings"], name, month)
        pl["wealth"] = total_wealth(pl["holdings"])

        # 6) Log
        pl["log"].append({
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
        })

        st.success(f"Ay {month} tamamlandı. Güncel servet: {pl['wealth']:,.0f} TL".replace(",", "."))
        if not cashflow_ok:
            st.warning("⚠️ Nakit akışı problemi: zorunlu satış/ceza. (Likidite kavramı)")
        if month == CFG["CRISIS_MONTH"]:
            st.info("📌 Kriz: varlıkların farklı tepkileri (risk çeşitliliği)")

        pl["month"] = month + 1
        st.rerun()

    if pl["log"]:
        st.divider()
        st.subheader("📒 Geçmiş (Kişisel)")
        df = pd.DataFrame(pl["log"])
        st.dataframe(df[["Ay","Gelir","SabitGider","EkHarcama","TasarrufTutarı","NakitAkisiOK","Kriz","Servet","CezaToplam"]],
                     use_container_width=True, hide_index=True)
        st.subheader("📈 Servet Zaman Serisi")
        st.line_chart(df[["Ay","Servet"]].set_index("Ay"))

with right:
    st.subheader("🎓 Öğrenme Paneli")
    if "name" in locals() and name:
        pl = get_player(name)
        st.metric("Ay", f"{min(pl['month'], CFG['MONTHS']+1)} / {CFG['MONTHS']}")
        st.metric("Toplam Servet (TL)", f"{pl['wealth']:,.0f}".replace(",", "."))
        st.metric("Toplam Ceza (TL)", f"{pl['penalty']:,.0f}".replace(",", "."))

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
