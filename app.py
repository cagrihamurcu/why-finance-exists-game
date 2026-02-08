import streamlit as st
import streamlit.components.v1 as components
import numpy as np
import pandas as pd

st.set_page_config(page_title="Finansal Sistem Oyunu", layout="wide")

# ======================
# SABİT PARAMETRELER
# ======================
MONTHS = 12
DEFAULT_INCOME = 60000
START_FIXED_COST = 30000

TX_FEE = 0.005
EARLY_BREAK = 0.01

# ======================
# SESSION STATE
# ======================
if "players" not in st.session_state:
    st.session_state.players = {}

if "seed" not in st.session_state:
    st.session_state.seed = 42

if "theft_banner" not in st.session_state:
    st.session_state.theft_banner = None

# ======================
# FORMAT
# ======================
def tl(x: float) -> str:
    return f"{x:,.0f} TL".replace(",", ".")

# ======================
# OYUNCU OLUŞTUR
# ======================
def get_player(name: str) -> dict:
    if name not in st.session_state.players:
        rng = np.random.default_rng((hash(name) % 10000) + st.session_state.seed)

        # ✅ En az 3 kez hırsızlık garantili aylar (1..12)
        theft_months = sorted(
            rng.choice(np.arange(1, MONTHS + 1), size=3, replace=False).tolist()
        )

        st.session_state.players[name] = {
            "month": 1,
            "cash": 0.0,

            # Basit versiyon: mevduat/piyasa yok (istersen sonra ekleriz)
            "dd": {},   # vadesiz
            "td": {},   # vadeli

            "debt": 0.0,
            "debt_rate": 0.03,  # aylık

            "income": float(DEFAULT_INCOME),   # ✅ sabit, öğrenci değiştiremez
            "fixed": float(START_FIXED_COST),  # ✅ enflasyonla artacak
            "infl": 0.20,                      # ✅ başlangıç

            "theft_months": theft_months,
            "log": []
        }
    return st.session_state.players[name]

# ======================
# HIRSIZLIK MESAJI (EKRAN ÜSTÜ)
# ======================
if st.session_state.theft_banner:
    loss = float(st.session_state.theft_banner["loss"])
    remain = float(st.session_state.theft_banner["remain"])
    banner_id = f"alertbox_{np.random.randint(1_000_000)}"

    components.html(
        f"""
        <div id="{banner_id}" style="
            padding:20px;
            background:#ff0000;
            color:white;
            font-size:24px;
            font-weight:900;
            border-radius:15px;
            border:4px solid #b30000;
            box-shadow:0 10px 25px rgba(0,0,0,0.25);
            margin:10px 0 16px 0;">
            🚨 NAKİT HIRSIZLIĞI! 🚨<br>
            Kayıp: {tl(loss)}<br>
            Kalan Nakit: {tl(remain)}
        </div>

        <script>
        setTimeout(function(){{
            var el = document.getElementById("{banner_id}");
            if(el) el.style.display="none";
        }},10000);
        </script>
        """,
        height=160
    )

    # ✅ aynı olay tekrar tekrar görünmesin
    st.session_state.theft_banner = None

# ======================
# ARAYÜZ
# ======================
st.title("🎮 Finansın Neden Var Olduğunu Hisset: Mini Simülasyon (1. Hafta)")

# reset
c1, c2 = st.columns([1, 6])
with c1:
    if st.button("🧹 Sıfırla"):
        st.session_state.clear()
        st.rerun()
with c2:
    st.caption("Gelir sabit, giderler enflasyonla artar. Ay 1–3 bankacılık yok (borç yok). Hırsızlık sadece nakitte olur.")

name = st.text_input("Oyuncu Adı")
if not name:
    st.stop()

p = get_player(name)
month = int(p["month"])

# ======================
# LEADERBOARD
# ======================
st.subheader("🏆 Oyuncu Sıralaması (Net Nakit - Borç)")
rows = []
for pname, pp in st.session_state.players.items():
    net = float(pp["cash"]) - float(pp["debt"])
    rows.append({
        "Oyuncu": pname,
        "Ay": pp["month"],
        "Nakit": round(pp["cash"], 0),
        "Borç": round(pp["debt"], 0),
        "Net": round(net, 0),
    })
lb = pd.DataFrame(rows).sort_values("Net", ascending=False)
st.dataframe(lb, use_container_width=True, hide_index=True, height=220)

st.divider()
st.subheader(f"📅 Ay {month} / {MONTHS}")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Gelir (Sabit)", tl(p["income"]))
col2.metric("Enflasyon (Bu Ay)", f"%{p['infl']*100:.1f}")
col3.metric("Bu Ay Sabit Gider", tl(p["fixed"]))
col4.metric("Borç Mekanizması", "Açık (Banka)" if month >= 4 else "Kapalı (Ay1-3)")

colA, colB = st.columns(2)
colA.metric("Nakit", tl(p["cash"]))
colB.metric("Borç", tl(p["debt"]))

# ======================
# BÜTÇE
# ======================
st.divider()
st.subheader("1) Bütçe Kararı")

# Ay 1-3 borç yok: ek harcama tavanını nakit+gelir - giderle sınırla
available_without_borrow = float(p["cash"]) + float(p["income"])
if month < 4:
    extra_max = max(0.0, available_without_borrow - float(p["fixed"]))
else:
    extra_max = 50000.0

extra = st.number_input("Ek Harcama (TL)", min_value=0.0, max_value=float(extra_max), value=min(5000.0, float(extra_max)), step=1000.0)
total_exp = float(p["fixed"]) + float(extra)

st.write(f"Toplam Gider: **{tl(total_exp)}**")

if month < 4 and total_exp > available_without_borrow + 1e-9:
    st.error("Ay 1–3: borç yok. Bu bütçe (nakit+gelir) sınırını aşıyor → temerrüt olur. Ek harcamayı azaltın.")

# ======================
# BORÇ ALMA (Ay 4+)
# ======================
st.divider()
st.subheader("2) Bankadan Borç Alma (Ay 4+)")
borrow = 0.0
if month >= 4:
    borrow = st.number_input("Bu ay borç al (TL)", min_value=0.0, max_value=200000.0, value=0.0, step=1000.0)
    st.caption(f"Borç faizi: % {p['debt_rate']*100:.1f} / ay")
else:
    st.caption("Ay 1–3: finansal kurum yok → borç alınamaz.")

# ======================
# BORÇ ÖDEME (Ay 4+ ve borç varsa)
# ======================
st.divider()
st.subheader("3) Borç Ödeme (Ay Sonu)")
repay = 0.0
if month >= 4 and float(p["debt"]) > 0:
    max_pay = min(float(p["cash"]), float(p["debt"]))
    st.caption(f"Bu ay ödeyebileceğiniz maksimum: **{tl(max_pay)}**")
    repay = st.number_input("Bu ay borç öde (TL)", min_value=0.0, max_value=float(max_pay), value=0.0, step=1000.0)
else:
    st.caption("Bu ay borç yok veya borç mekanizması aktif değil.")

# ======================
# AYI TAMAMLA
# ======================
st.divider()
btn = "✅ 12. Ayı Tamamla ve Bitir" if month == MONTHS else "✅ Ayı Tamamla"

if st.button(btn):
    rng = np.random.default_rng((hash(name) % 10000) + month * 1000 + st.session_state.seed)

    theft_loss = 0.0
    borrowed_now = 0.0

    # 1) GELİR
    p["cash"] += float(p["income"])

    # 2) BORÇ EKLE
    if month >= 4 and borrow > 0:
        borrowed_now = float(borrow)
        p["cash"] += borrowed_now
        p["debt"] += borrowed_now

    # 3) GİDER
    p["cash"] -= float(total_exp)

    # 4) Ay 1-3 açık varsa temerrüt (borç yok)
    if month < 4 and p["cash"] < 0:
        p["log"].append({
            "Ay": month,
            "Gelir": p["income"],
            "ToplamGider": total_exp,
            "YeniBorç": borrowed_now,
            "Hırsızlık": 0.0,
            "DönemSonuNakit": 0.0,
            "Borç": p["debt"],
            "Not": "TEMERRÜT (Ay1-3 borç yok)"
        })
        p["cash"] = 0.0
        p["month"] = MONTHS + 1
        st.error("⛔ Ay 1–3 döneminde açık oluştu (borç yok) → TEMERRÜT")
        st.rerun()

    # 5) Ay 4+ açık varsa otomatik borçla kapat
    if month >= 4 and p["cash"] < 0:
        deficit = -p["cash"]
        p["debt"] += deficit
        p["cash"] = 0.0

    # 6) BORÇ FAİZİ (ay sonu)
    if month >= 4 and p["debt"] > 0:
        p["debt"] *= (1.0 + float(p["debt_rate"]))

    # 7) BORÇ ÖDEME (ay sonu)
    if month >= 4 and p["debt"] > 0 and repay > 0:
        pay = min(float(repay), float(p["cash"]), float(p["debt"]))
        p["cash"] -= pay
        p["debt"] -= pay
        if p["debt"] < 1:
            p["debt"] = 0.0

    # 8) HIRSIZLIK (en az 3 ay garantili)
    theft_trigger = (month in p["theft_months"]) and (p["cash"] > 0)
    if theft_trigger:
        sev = float(rng.uniform(0.15, 0.35))
        theft_loss = float(p["cash"]) * sev
        p["cash"] -= theft_loss

        # ✅ ekranda mesaj göster
        st.session_state.theft_banner = {"loss": theft_loss, "remain": p["cash"]}

    # 9) ENFLASYON GÜNCELLE (+/- %1–5)
    step = float(rng.uniform(0.01, 0.05))
    if rng.random() < 0.5:
        p["infl"] = min(0.8, p["infl"] + step)
    else:
        p["infl"] = max(0.0, p["infl"] - step)

    # Sabit gider enflasyonla artsın
    p["fixed"] = float(p["fixed"] * (1.0 + float(p["infl"])))

    # 10) LOG
    p["log"].append({
        "Ay": month,
        "Gelir": p["income"],
        "ToplamGider": total_exp,
        "YeniBorç": borrowed_now,
        "Hırsızlık": theft_loss,
        "DönemSonuNakit": p["cash"],
        "Borç": p["debt"],
        "Not": ""
    })

    # 11) AY İLERLET
    if month >= MONTHS:
        p["month"] = MONTHS + 1
    else:
        p["month"] += 1

    st.rerun()

# ======================
# OYUN BİTTİ Mİ?
# ======================
if p["month"] > MONTHS:
    st.success("✅ Oyun bitti (12 ay tamamlandı veya temerrüt oldu).")

# ======================
# GEÇMİŞ
# ======================
if p["log"]:
    st.divider()
    st.subheader("📒 Geçmiş (Sade)")
    df = pd.DataFrame(p["log"])
    st.dataframe(df, use_container_width=True, hide_index=True, height=360)
