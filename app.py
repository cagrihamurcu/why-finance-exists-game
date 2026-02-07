# =========================
# GEÇMİŞ: SADE VERSİYON
# =========================
if p["log"]:
    st.divider()
    st.subheader("📒 Geçmiş (Sade Özet)")

    df = pd.DataFrame(p["log"]).copy()

    # Bu ay servet değişimi hesapla
    df["Servet_Değişimi(TL)"] = df["Servet_Bitiş(TL)"] - df["Servet_Başlangıç(TL)"]

    # Sade sütun seçimi
    simple_df = df[[
        "Ay",
        "Aşama",
        "Gelir(TL)",
        "ToplamGider(TL)",
        "Tasarruf(TL)",
        "EnflasyonOranı(%)",
        "EnflasyonTutarı(TL)",
        "Servet_Değişimi(TL)",
        "Servet_Bitiş(TL)"
    ]].copy()

    # Yuvarlama
    money_cols = [
        "Gelir(TL)",
        "ToplamGider(TL)",
        "Tasarruf(TL)",
        "EnflasyonTutarı(TL)",
        "Servet_Değişimi(TL)",
        "Servet_Bitiş(TL)"
    ]

    for c in money_cols:
        simple_df[c] = simple_df[c].round(0)

    simple_df["EnflasyonOranı(%)"] = simple_df["EnflasyonOranı(%)"].round(2)

    st.dataframe(simple_df, use_container_width=True, hide_index=True)

    st.subheader("📈 Servet Zaman Serisi")
    st.line_chart(simple_df.set_index("Ay")["Servet_Bitiş(TL)"])
