import json
from urllib.parse import quote

import streamlit as st
from chatbot import get_answer
from config import MAPS_API_KEY

# ดึงพิกัดจากเบราว์เซอร์ (ถ้ามีไลบรารี) — ไม่มีก็ไม่พัง
try:
    from streamlit_javascript import st_javascript
except Exception:
    st_javascript = None

# ---------- Page setup ----------
st.set_page_config(page_title="Pathew Chatbot", page_icon="🌴", layout="centered")
st.markdown("<h1 style='margin-bottom:0'>🌴 AI Chatbot แนะนำสถานที่ในอำเภอปะทิว</h1>", unsafe_allow_html=True)
st.caption("บอกความต้องการคุณมาได้เลย เช่น: ตลาด, ยิม/ฟิตเนส, คาเฟ่, ปั๊มน้ำมัน, วัด, จุดชมวิว")

# ---------- Colored avatars ----------
svg_user = """<svg xmlns='http://www.w3.org/2000/svg' width='40' height='40'><circle cx='20' cy='20' r='18' fill='#3B82F6'/></svg>"""
svg_bot  = """<svg xmlns='http://www.w3.org/2000/svg' width='40' height='40'><circle cx='20' cy='20' r='18' fill='#F59E0B'/></svg>"""
avatar_user = f"data:image/svg+xml;utf8,{quote(svg_user)}"
avatar_bot  = f"data:image/svg+xml;utf8,{quote(svg_bot)}"

# ---------- Session state ----------
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "สวัสดีครับ! อยากหาสถานที่ในอำเภอปะทิวบอกผมได้เลย"}
    ]

# ---------- ขอพิกัดผู้ใช้ครั้งแรก (ถ้าอนุญาต) ----------
user_lat = st.session_state.get("user_lat")
user_lng = st.session_state.get("user_lng")
if st_javascript and (user_lat is None or user_lng is None):
    try:
        coords = st_javascript("navigator.geolocation.getCurrentPosition((p) => p.coords);")
        if isinstance(coords, dict):
            lat = coords.get("latitude")
            lng = coords.get("longitude")
            if lat and lng:
                st.session_state["user_lat"] = float(lat)
                st.session_state["user_lng"] = float(lng)
                user_lat, user_lng = float(lat), float(lng)
    except Exception:
        pass  # ผู้ใช้ไม่อนุญาต/เบราว์เซอร์ไม่รองรับ ก็ข้ามไป

# ---------- Render history ----------
for msg in st.session_state.messages:
    avatar = avatar_user if msg["role"] == "user" else avatar_bot
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

# ---------- Chat input ----------
user_input = st.chat_input("พิมพ์คุยอะไรก็ได้ หรือบอกประเภท/ชื่อสถานที่ในปะทิว…")

if user_input:
    # แสดง/เก็บข้อความผู้ใช้
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user", avatar=avatar_user):
        st.markdown(user_input)

    # เรียกบอท — ส่ง history ถ้าฟังก์ชันรองรับ (กันพังหากไป import เวอร์ชันเก่า)
    try:
        reply_text, places = get_answer(
            user_input,
            user_lat=st.session_state.get("user_lat"),
            user_lng=st.session_state.get("user_lng"),
            history=st.session_state.messages[-8:],   # จำบริบท 8 ข้อความล่าสุด
        )
    except TypeError:
        reply_text, places = get_answer(
            user_input,
            user_lat=st.session_state.get("user_lat"),
            user_lng=st.session_state.get("user_lng"),
        )

    # แสดงคำตอบ + การ์ดสถานที่
    with st.chat_message("assistant", avatar=avatar_bot):
        st.markdown(reply_text)

        if places:
            for p in places:
                name = p.get("name", "-")
                desc = (p.get("description") or "").strip()
                hi = (p.get("highlight") or "").strip()
                tambon = p.get("tambon", "-")
                category = p.get("category", "-")
                lat, lng = p.get("latitude"), p.get("longitude")
                map_link = f"https://www.google.com/maps?q={lat},{lng}" if lat and lng else None

                with st.container(border=True):
                    cols = st.columns([1, 2])

                    # ---- ซ้าย: รูป (รองรับแกลเลอรีหลายรูป) ----
                    with cols[0]:
                        shown = False
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

                        # fallback: image_url เดี่ยว
                        if (not shown) and isinstance(p.get("image_url"), str) and p["image_url"].startswith("http"):
                            st.image(p["image_url"], use_container_width=True)
                            shown = True

                        # fallback: Static Maps ถ้ามีพิกัด
                        if (not shown) and lat and lng and MAPS_API_KEY:
                            static_map = (
                                "https://maps.googleapis.com/maps/api/staticmap"
                                f"?center={lat},{lng}&zoom=15&size=640x400&maptype=roadmap"
                                f"&markers=color:red%7C{lat},{lng}&key={MAPS_API_KEY}"
                            )
                            st.image(static_map, use_container_width=True)
                            shown = True

                        if not shown:
                            st.markdown("ไม่มีรูป")

                    # ---- ขวา: รายละเอียด ----
                    with cols[1]:
                        st.markdown(f"**{name}**")
                        st.markdown(desc or "—")
                        if hi:
                            st.markdown(f"**จุดเด่น:** {hi}")
                        st.markdown(f"**ตำบล:** {tambon}  |  **ประเภท:** {category}")
                        if map_link:
                            st.markdown(f"[เปิดแผนที่]({map_link})")

    # เก็บข้อความบอทลงประวัติ (เก็บเฉพาะข้อความ)
    st.session_state.messages.append({"role": "assistant", "content": reply_text})
