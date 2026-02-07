# =========================
# LİDER TABLOSU (SIRALAMA)
# =========================
st.divider()
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
        "Sıra": 0,  # aşağıda dolduracağız
        "Oyuncu": pname,
        "Durum": status,
        "Ay": month_done,
        "Nakit": round(cash, 0),
        "Yatırım": round(invest, 0),
        "Borç": round(debt, 0),
        "Servet(Net)": round(net, 0),
    })

lb = pd.DataFrame(rows).sort_values(["Servet(Net)", "Borç"], ascending=[False, True]).reset_index(drop=True)
lb["Sıra"] = lb.index + 1

st.dataframe(lb, use_container_width=True, hide_index=True)
