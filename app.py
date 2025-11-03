# app.py — แสดงผลแชท + การ์ด + แผนที่
# รองรับ chatbot.py ด้านบนครบทุกโหมด

import json
from urllib.parse import quote
import streamlit as st
from chatbot import get_answer
from config import MAPS_API_KEY

# ---------- Setup ----------
st.set_page_config(page_title="TripTech AI", page_icon="🌴", layout="centered")
st.markdown("<h1>🌴 AI Chatbot แนะนำสถานที่ในอำเภอปะทิว</h1>", unsafe_allow_html=True)
st.caption("พิมพ์ได้เลย เช่น ‘ในชุมโคมีที่เที่ยวที่ไหนบ้าง’ หรือ ‘อยากหาคาเฟ่แถวบางสน’")

# ---------- Avatar ----------
svg_user="<svg xmlns='http://www.w3.org/2000/svg' width='40' height='40'><circle cx='20' cy='20' r='18' fill='#3B82F6'/></svg>"
svg_bot="<svg xmlns='http://www.w3.org/2000/svg' width='40' height='40'><circle cx='20' cy='20' r='18' fill='#F59E0B'/></svg>"
avatar_user=f"data:image/svg+xml;utf8,{quote(svg_user)}"
avatar_bot=f"data:image/svg+xml;utf8,{quote(svg_bot)}"

# ---------- Session ----------
if "messages" not in st.session_state:
    st.session_state.messages=[{"role":"assistant","content":"สวัสดีครับ! ผมช่วยแนะนำสถานที่ในอำเภอปะทิวได้ครับ 😄"}]
if "last_results" not in st.session_state: st.session_state.last_results=[]

# ---------- Render history ----------
for m in st.session_state.messages:
    av=avatar_user if m["role"]=="user" else avatar_bot
    with st.chat_message(m["role"], avatar=av): st.markdown(m["content"])

# ---------- Input ----------
user_input=st.chat_input("พิมพ์คำถามหรือสถานที่ได้เลย...")

def render_place_card(p):
    name=p.get("name","-")
    desc=(p.get("description") or "").strip()
    hi=(p.get("highlight") or "").strip()
    tambon=p.get("tambon","-"); cat=p.get("category","-")
    lat, lng=p.get("latitude"), p.get("longitude")
    link=f"https://www.google.com/maps?q={lat},{lng}" if lat and lng else None
    with st.container(border=True):
        cols=st.columns([1,2])
        with cols[0]:
            img=p.get("image_url")
            if img and img.startswith("http"): st.image(img,use_container_width=True)
            elif lat and lng and MAPS_API_KEY:
                st.image(f"https://maps.googleapis.com/maps/api/staticmap?center={lat},{lng}&zoom=15&size=400x300&markers=color:red%7C{lat},{lng}&key={MAPS_API_KEY}",use_container_width=True)
            else: st.markdown("ไม่มีรูป")
        with cols[1]:
            st.markdown(f"**{name}**")
            st.markdown(desc or "—")
            if hi: st.markdown(f"**จุดเด่น:** {hi}")
            st.markdown(f"ตำบล: {tambon} | ประเภท: {cat}")
            if link: st.markdown(f"[เปิดแผนที่]({link})")

if user_input:
    st.session_state.messages.append({"role":"user","content":user_input})
    with st.chat_message("user", avatar=avatar_user): st.markdown(user_input)

    reply, places = get_answer(user_input, last_results=st.session_state.last_results)
    with st.chat_message("assistant", avatar=avatar_bot):
        st.markdown(reply)
        if places:
            for p in places:
                render_place_card(p)

    st.session_state.messages.append({"role":"assistant","content":reply})
    if places: st.session_state.last_results=places
