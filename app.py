import json
import re
from urllib.parse import quote, urlparse, parse_qs

import streamlit as st
from chatbot import get_answer
from config import MAPS_API_KEY

try:
    from streamlit_javascript import st_javascript
except Exception:
    st_javascript = None


# ---------- Page setup ----------
st.set_page_config(page_title="Pathew Chatbot", page_icon="🌴", layout="centered")
st.markdown(
    "<h1 style='margin-bottom:0'>🌴 AI Chatbot แนะนำสถานที่ในอำเภอปะทิว</h1>",
    unsafe_allow_html=True,
)
st.caption(
    "ตัวอย่าง: ก๋วยเตี๋ยว, คาเฟ่, ยิม, ร้านซ่อมรถ, ปั๊มน้ำมัน, วัด, หาด ฯลฯ • "
    "พิมพ์ “ไม่เอาตลาด” หรือ “ตลาดปิดหมดแล้ว” ได้"
)

# ---------- Avatars ----------
svg_user = """<svg xmlns='http://www.w3.org/2000/svg' width='40' height='40'><circle cx='20' cy='20' r='18' fill='#3B82F6'/></svg>"""
svg_bot = """<svg xmlns='http://www.w3.org/2000/svg' width='40' height='40'><circle cx='20' cy='20' r='18' fill='#F59E0B'/></svg>"""
avatar_user = f"data:image/svg+xml;utf8,{quote(svg_user)}"
avatar_bot = f"data:image/svg+xml;utf8,{quote(svg_bot)}"


# ---------- Helpers ----------
def safe_rerun():
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass


def extract_google_drive_file_id(url: str):
    """ดึง file id ออกจากลิงก์ Google Drive หลายรูปแบบ"""
    if not url or not isinstance(url, str):
        return None

    # แบบ /file/d/FILE_ID/view
    m = re.search(r"/file/d/([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)

    # แบบ open?id=FILE_ID
    if "open?id=" in url:
        try:
            parsed = urlparse(url)
            q = parse_qs(parsed.query)
            file_ids = q.get("id")
            if file_ids:
                return file_ids[0]
        except Exception:
            pass

    # แบบ uc?id=FILE_ID
    if "uc?id=" in url:
        try:
            parsed = urlparse(url)
            q = parse_qs(parsed.query)
            file_ids = q.get("id")
            if file_ids:
                return file_ids[0]
        except Exception:
            pass

    return None


def fix_image_url(url: str):
    """
    แปลงลิงก์รูปให้โหลดง่ายขึ้น โดยเฉพาะ
    - Google Drive
    - lh3.google
    """
    if not url or not isinstance(url, str):
        return None

    url = url.strip()
    if not url:
        return None

    # Google Drive หลายรูปแบบ
    if "drive.google.com" in url:
        file_id = extract_google_drive_file_id(url)
        if file_id:
            return f"https://drive.google.com/uc?export=view&id={file_id}"
        return url

    # lh3.google / googleusercontent
    if "lh3.google" in url or "googleusercontent.com" in url:
        # ถ้ายังไม่มีพารามิเตอร์ขนาด ให้เติม =s1200 เพื่อให้เรียกรูปง่ายขึ้น
        if "=" not in url.split("/")[-1]:
            return f"{url}=s1200"
        return url

    return url


def parse_image_urls(raw_value):
    """แปลง image_urls ที่อาจเป็น JSON string / list / ค่าเดี่ยว ให้เป็น list[str]"""
    if not raw_value:
        return []

    if isinstance(raw_value, list):
        return [fix_image_url(u) for u in raw_value if isinstance(u, str) and u.strip()]

    if isinstance(raw_value, str):
        txt = raw_value.strip()
        if not txt:
            return []

        # ถ้าเป็น JSON list
        try:
            data = json.loads(txt)
            if isinstance(data, list):
                return [fix_image_url(u) for u in data if isinstance(u, str) and u.strip()]
        except Exception:
            pass

        # ถ้าเป็น string URL เดี่ยว
        return [fix_image_url(txt)]

    return []


def get_best_image_candidates(place: dict):
    """รวม image_urls + image_url ออกมาเป็นลิสต์เรียงลำดับ"""
    urls = []

    image_urls = parse_image_urls(place.get("image_urls"))
    urls.extend(image_urls)

    image_url = place.get("image_url")
    if isinstance(image_url, str) and image_url.strip():
        fixed = fix_image_url(image_url)
        if fixed and fixed not in urls:
            urls.append(fixed)

    # คัดเฉพาะลิงก์ http/https
    clean = []
    for u in urls:
        if isinstance(u, str) and u.startswith(("http://", "https://")):
            clean.append(u)

    return clean


def build_static_map_url(lat, lng):
    """สร้าง Google Static Map URL"""
    if not lat or not lng or not MAPS_API_KEY:
        return None

    return (
        "https://maps.googleapis.com/maps/api/staticmap"
        f"?center={lat},{lng}"
        f"&zoom=15"
        f"&size=800x500"
        f"&maptype=roadmap"
        f"&markers=color:red%7C{lat},{lng}"
        f"&key={MAPS_API_KEY}"
    )


def try_show_image(url: str, caption: str = None):
    """
    พยายามแสดงรูปแบบไม่ให้แอปพัง
    Streamlit ส่วนใหญ่จะ render ให้แม้ URL บางตัวมี redirect
    """
    if not url:
        return False

    try:
        st.image(url, use_container_width=True, caption=caption)
        return True
    except Exception:
        return False


# ---------- Session state ----------
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "สวัสดีครับ! อยากหาสถานที่ในอำเภอปะทิวบอกผมได้เลย"}
    ]

if "user_lat" not in st.session_state:
    st.session_state.user_lat = None

if "user_lng" not in st.session_state:
    st.session_state.user_lng = None

if "focus_place_id" not in st.session_state:
    st.session_state.focus_place_id = None

if "last_results" not in st.session_state:
    st.session_state.last_results = []

if "banned_categories" not in st.session_state:
    st.session_state.banned_categories = []


# ---------- Geolocation (optional) ----------
user_lat = st.session_state.get("user_lat")
user_lng = st.session_state.get("user_lng")

if st_javascript and (user_lat is None or user_lng is None):
    try:
        coords = st_javascript("navigator.geolocation.getCurrentPosition((p) => p.coords);")
        if isinstance(coords, dict):
            lat = coords.get("latitude")
            lng = coords.get("longitude")
            if lat is not None and lng is not None:
                st.session_state["user_lat"] = float(lat)
                st.session_state["user_lng"] = float(lng)
                user_lat, user_lng = float(lat), float(lng)
    except Exception:
        pass


# ---------- Render history ----------
for msg in st.session_state.messages:
    avatar = avatar_user if msg["role"] == "user" else avatar_bot
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])


# ---------- Chat input ----------
user_input = st.chat_input("พิมพ์คุยอะไรก็ได้ หรือบอกประเภท/ชื่อสถานที่ในปะทิว…")


def _render_place_card(p: dict):
    name = p.get("name", "-")
    desc = (p.get("description") or "").strip()
    hi = (p.get("highlight") or "").strip()
    tambon = p.get("tambon", "-")
    category = p.get("category", "-")
    lat = p.get("latitude")
    lng = p.get("longitude")

    map_link = None
    if lat is not None and lng is not None:
        map_link = f"https://www.google.com/maps?q={lat},{lng}"

    with st.container(border=True):
        cols = st.columns([1, 2])

        with cols[0]:
            shown = False

            # 1) พยายามใช้รูปจริงก่อน
            image_candidates = get_best_image_candidates(p)

            if image_candidates:
                main_img = image_candidates[0]
                shown = try_show_image(main_img)

                # รูปย่อย
                if shown and len(image_candidates) > 1:
                    thumbs = image_candidates[1:5]
                    if thumbs:
                        tcols = st.columns(len(thumbs))
                        for tcol, u in zip(tcols, thumbs):
                            with tcol:
                                try_show_image(u)

            # 2) ถ้าไม่มีรูป หรือรูปไม่ขึ้น ใช้ static map
            if not shown:
                static_map = build_static_map_url(lat, lng)
                if static_map:
                    shown = try_show_image(static_map)

            # 3) ถ้ายังไม่ขึ้นอีก
            if not shown:
                st.markdown("ไม่มีรูป")

        with cols[1]:
            st.markdown(f"**{name}**")
            st.markdown(desc or "—")

            if hi:
                st.markdown(f"**จุดเด่น:** {hi}")

            st.markdown(f"**ตำบล:** {tambon}  |  **ประเภท:** {category}")

            if map_link:
                st.markdown(f"[เปิดแผนที่]({map_link})")

            if "distance_km" in p and p.get("distance_km") is not None:
                try:
                    st.markdown(f"**ระยะทาง:** {float(p['distance_km']):.2f} กม.")
                except Exception:
                    pass

            if "id" in p and st.button("คุยต่อเกี่ยวกับที่นี่", key=f"focus_{p['id']}"):
                st.session_state["focus_place_id"] = p["id"]
                safe_rerun()


if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.chat_message("user", avatar=avatar_user):
        st.markdown(user_input)

    result = get_answer(
        user_input,
        user_lat=st.session_state.get("user_lat"),
        user_lng=st.session_state.get("user_lng"),
        history=st.session_state.messages[-8:],
        focus_place_id=st.session_state.get("focus_place_id"),
        last_results=st.session_state.get("last_results", []),
        banned_categories=st.session_state.get("banned_categories", []),
    )

    if isinstance(result, tuple) and len(result) == 3:
        reply_text, places, banned_out = result
        st.session_state["banned_categories"] = (
            banned_out or st.session_state.get("banned_categories", [])
        )
    else:
        reply_text, places = result
        banned_out = st.session_state.get("banned_categories", [])

    with st.chat_message("assistant", avatar=avatar_bot):
        st.markdown(reply_text)

        if places:
            for p in places:
                _render_place_card(p)

    st.session_state.messages.append({"role": "assistant", "content": reply_text})

    if places:
        st.session_state["last_results"] = places
        if len(places) == 1 and places[0].get("id"):
            st.session_state["focus_place_id"] = places[0]["id"]