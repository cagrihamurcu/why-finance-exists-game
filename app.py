# Hırsızlık banner'ı (10 saniye sonra kaybolur + tek sefer + sesli)
if st.session_state.theft_banner:
    loss = float(st.session_state.theft_banner["loss"])
    remain = float(st.session_state.theft_banner["remain"])

    # HTML id (eşsiz olsun)
    banner_id = f"theft_banner_{st.session_state.seed}"

    # Basit "beep" sesi (data URI). İsterseniz daha sonra farklı bir sesle değiştirilebilir.
    # Bu base64 kısa bir uyarı wav'ıdır.
    beep_wav_base64 = (
        "UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA="
    )

    components.html(
        f"""
        <div id="{banner_id}" style="
            padding:18px;border-radius:16px;border:4px solid #8b0000;
            background:linear-gradient(90deg,#ffe6e6,#fff1f1);
            font-size:22px;line-height:1.5;margin:8px 0 14px 0;">
            <div style="font-size:28px;font-weight:800;margin-bottom:6px;">
                🚨🚨🚨 NAKİT HIRSIZLIĞI — ACİL UYARI 🚨🚨🚨
            </div>
            <div><b>NAKİT ÇALINDI!</b></div>
            <div><b>Kayıp:</b> {fmt_tl(loss)}</div>
            <div><b>Kalan Nakit:</b> {fmt_tl(remain)}</div>
            <div style="font-size:15px;margin-top:8px;">
                (Bu risk yalnızca <b>nakitte</b> geçerlidir. Bankadaki mevduat bu riskten etkilenmez.)
            </div>
        </div>

        <audio autoplay>
          <source src="data:audio/wav;base64,{beep_wav_base64}" type="audio/wav">
        </audio>

        <script>
          setTimeout(function(){{
            var el = document.getElementById("{banner_id}");
            if(el) el.style.display = "none";
          }}, 10000);
        </script>
        """,
        height=180,
    )

    # Bir daha görünmesin (tek sefer)
    st.session_state.theft_banner = None
