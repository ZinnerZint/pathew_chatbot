import streamlit as st
from chatbot import get_answer

# ---------- Page setup ----------
st.set_page_config(page_title="Pathew Chatbot", page_icon="🌴", layout="centered")
st.markdown(
    "<h1 style='margin-bottom:0'>🌴 AI Chatbot แนะนำสถานที่ในอำเภอปะทิว</h1>",
    unsafe_allow_html=True,
)
st.caption("ถามได้เลย เช่น: *ร้านอาหารราคาถูกแถวบางสน*, *มีปั๊มน้ำมันใกล้ๆ ไหม*")

# ---------- Session state ----------
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "สวัสดีครับ! อยากหาอะไรในปะทิวบอกผมได้เลย"}
    ]

# ---------- Render history ----------
for msg in st.session_state.messages:
    # ใช้ HTML วงกลมสีแทน avatar
    if msg["role"] == "user":
        avatar = "🔵"  # หรือจะใช้ HTML <span style='color:blue'>●</span>
    else:
        avatar = "🟠"

    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

# ---------- Chat input ----------
user_input = st.chat_input("พิมพ์คำถามเกี่ยวกับสถานที่ในปะทิวได้เลย…")

if user_input:
    # -------- User message --------
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user", avatar="🔵"):
        st.markdown(user_input)

    # -------- Bot response --------
    reply_text, places = get_answer(user_input)
    with st.chat_message("assistant", avatar="🟠"):
        st.markdown(reply_text)

        # แสดงผลลัพธ์เสริมเป็นการ์ด
        if places:
            for p in places:
                name = p.get("name", "-")
                desc = (p.get("description") or "").strip()
                img = p.get("image_url")
                lat, lng = p.get("latitude"), p.get("longitude")
                map_link = f"https://www.google.com/maps?q={lat},{lng}" if lat and lng else None

                with st.container(border=True):
                    cols = st.columns([1, 2])
                    with cols[0]:
                        if isinstance(img, str) and img.startswith("http"):
                            st.image(img, use_container_width=True)
                        else:
                            st.markdown("🖼️ ไม่มีรูป")
                    with cols[1]:
                        st.markdown(f"**{name}**  \n{desc or '—'}")
                        st.markdown(
                            f"**ตำบล:** {p.get('tambon','-')}  |  **ประเภท:** {p.get('category','-')}"
                        )
                        if map_link:
                            st.markdown(f"[🗺️ เปิดแผนที่]({map_link})")

    # เก็บข้อความบอทลง session
    st.session_state.messages.append({"role": "assistant", "content": reply_text})
