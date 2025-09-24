import streamlit as st
from chatbot import get_answer
from config import MAPS_API_KEY
from urllib.parse import quote
import json

# ---------- ใช้ JS ดึงพิกัดจาก browser ----------
from streamlit_javascript import st_javascript

# ---------- Page setup ----------
st.set_page_config(page_title="Pathew Chatbot", page_icon="🌴", layout="centered")
st.markdown(
    "<h1 style='margin-bottom:0'>🌴 AI Chatbot แนะนำสถานที่ในอำเภอปะทิว</h1>",
    unsafe_allow_html=True,
)
st.caption("ถามได้เลย เช่น: *ร้านอาหารราคาถูกแถวบางสน*, *มีปั๊มน้ำมันใกล้ๆ ไหม*")

# ---------- Colored avatars ----------
svg_user = """<svg xmlns='http://www.w3.org/2000/svg' width='40' height='40'>
  <circle cx='20' cy='20' r='18' fill='#3B82F6'/>
</svg>"""
svg_bot = """<svg xmlns='http://www.w3.org/2000/svg' width='40' height='40'>
  <circle cx='20' cy='20' r='18' fill='#F59E0B'/>
</svg>"""
avatar_user = f"data:image/svg+xml;utf8,{quote(svg_user)}"
avatar_bot = f"data:image/svg+xml;utf8,{quote(svg_bot)}"

# ---------- Session state ----------
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "สวัสดีครับ! อยากหาอะไรในอำเภอปะทิวบอกผมได้เลย"}
    ]

# ---------- ลองดึงพิกัดผู้ใช้ผ่าน JS ----------
user_location = st_javascript("navigator.geolocation.getCurrentPosition((pos) => pos.coords);")

if user_location:
    st.session_state["user_lat"] = user_location.get("latitude")
    st.session_state["user_lng"] = user_location.get("longitude")

# ---------- Render history ----------
for msg in st.session_state.messages:
    avatar = avatar_user if msg["role"] == "user" else avatar_bot
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

# ---------- Chat input ----------
user_input = st.chat_input("พิมพ์คำถามเกี่ยวกับสถานที่ในปะทิวได้เลย…")

if user_input:
    # -------- User message --------
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user", avatar=avatar_user):
        st.markdown(user_input)

    # -------- Bot response --------
    reply_text, places = get_answer(user_input)

    # ถ้ายังไม่เจอ และเรามีพิกัดผู้ใช้ → บอกผู้ใช้ว่าใช้ตำแหน่งได้
    if not places and "user_lat" in st.session_state:
        lat, lng = st.session_state["user_lat"], st.session_state["user_lng"]
        reply_text += f"\n\n📍 ตรวจพบว่าคุณอยู่ใกล้พิกัด {lat:.5f}, {lng:.5f} ต้องการให้ผมหาสถานที่ใกล้คุณที่สุดไหม?"

    with st.chat_message("assistant", avatar=avatar_bot):
        st.markdown(reply_text)

        if places:
            for p in places:
                name = p.get("name", "-")
                desc = (p.get("description") or "").strip()
                lat, lng = p.get("latitude"), p.get("longitude")
                map_link = f"https://www.google.com/maps?q={lat},{lng}" if lat and lng else None

                with st.container(border=True):
                    cols = st.columns([1, 2])
                    with cols[0]:
                        shown = False

                        # ----- แสดงหลายรูป robust -----
                        images_raw = p.get("image_urls") or "[]"
                        try:
                            images = json.loads(images_raw) if isinstance(images_raw, str) else images_raw
                        except Exception:
                            images = []

                        urls = [u for u in images if isinstance(u, str) and u.startswith("http")]

                        if urls:
                            st.image(urls[0], use_container_width=True)
                            shown = True

                            thumbs = urls[1:]
                            if thumbs:
                                for i in range(0, len(thumbs), 4):
                                    row = thumbs[i:i+4]
                                    tcols = st.columns(len(row))
                                    for tcol, u in zip(tcols, row):
                                        with tcol:
                                            st.image(u, use_container_width=True)

                        # ถ้าไม่มี image_urls แต่ยังมี image_url เดิม
                        img = p.get("image_url")
                        if (not shown) and isinstance(img, str) and img.startswith("http"):
                            st.image(img, use_container_width=True)
                            shown = True

                        # ถ้าไม่มีรูป → ใช้ Static Maps
                        if (not shown) and lat and lng and MAPS_API_KEY:
                            static_map = (
                                "https://maps.googleapis.com/maps/api/staticmap"
                                f"?center={lat},{lng}&zoom=15&size=640x400&maptype=roadmap"
                                f"&markers=color:red%7C{lat},{lng}&key={MAPS_API_KEY}"
                            )
                            st.image(static_map, use_container_width=True)
                            shown = True

                        if not shown:
                            st.markdown("🖼️ ไม่มีรูป")

                    with cols[1]:
                        st.markdown(f"**{name}**  \n{desc or '—'}")
                        st.markdown(
                            f"**ตำบล:** {p.get('tambon','-')}  |  **ประเภท:** {p.get('category','-')}"
                        )
                        if map_link:
                            st.markdown(f"[🗺️ เปิดแผนที่]({map_link})")

    st.session_state.messages.append({"role": "assistant", "content": reply_text})
