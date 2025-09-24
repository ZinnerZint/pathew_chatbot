import streamlit as st
from chatbot import get_answer

# ---------- Page setup ----------
st.set_page_config(page_title="Pathew Chatbot", page_icon="🌴", layout="centered")
st.markdown(
    "<h1 style='margin-bottom:0'>😊 AI Chatbot แนะนำสถานที่ในอำเภอปะทิว</h1>",
    unsafe_allow_html=True,
)
st.caption("พิมพ์ถามได้เลย เช่น: *ร้านอาหารราคาถูกแถวบางสน*, *มีปั๊มน้ำมันใกล้ๆ ไหม*")

# ---------- Avatar: ใช้อีโมจิแทนไฟล์รูป ----------
USER_AVATAR = "🧑🏻‍💻"
BOT_AVATAR = "🤖"

# ---------- Session state ----------
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "สวัสดีครับ! อยากหาอะไรในปะทิวบอกผมได้เลย 😊"}
    ]

# ---------- Quick suggestions ----------
with st.container():
    cols = st.columns(3)
    if cols[0].button("คาเฟ่ บางสน"):
        st.session_state.messages.append({"role": "user", "content": "คาเฟ่ บางสน"})
    if cols[1].button("ปั๊มน้ำมัน ดอนยาง"):
        st.session_state.messages.append({"role": "user", "content": "ปั๊มน้ำมัน ดอนยาง"})
    if cols[2].button("ร้านอาหาร ถูก"):
        st.session_state.messages.append({"role": "user", "content": "ร้านอาหาร ราคาถูก"})

# ---------- Render history ----------
for msg in st.session_state.messages:
    avatar = USER_AVATAR if msg["role"] == "user" else BOT_AVATAR
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

# ---------- Chat input ----------
user_input = st.chat_input("พิมพ์คำถามเกี่ยวกับสถานที่ในปะทิวได้เลย…")

def render_places(places):
    """แสดงผลลัพธ์เป็นการ์ด + ลิงก์เปิดแผนที่"""
    for p in places:
        name = p.get("name", "-")
        tambon = p.get("tambon", "-")
        cat = p.get("category", "-")
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
                st.markdown(f"**ตำบล:** {tambon}  |  **ประเภท:** {cat}")
                if map_link:
                    st.markdown(f"[🗺️ เปิดแผนที่]({map_link})")

def run_turn(text: str):
    # ผู้ใช้
    st.session_state.messages.append({"role": "user", "content": text})
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(text)

    # บอท
    reply_text, places = get_answer(text)
    with st.chat_message("assistant", avatar=BOT_AVATAR):
        st.markdown(reply_text)
        if places:
            render_places(places)
    st.session_state.messages.append({"role": "assistant", "content": reply_text})

# จากปุ่มลัดด้านบน (ถ้ามี)
if len(st.session_state.messages) >= 2 and st.session_state.messages[-1]["role"] == "user" \
   and (st.session_state.messages[-2]["role"] != "assistant"):
    # เพิ่งเพิ่มจากปุ่มลัด → ทำ turn ให้เสร็จ
    run_turn(st.session_state.messages[-1]["content"])

# จากช่องพิมพ์ปกติ
if user_input:
    run_turn(user_input)
