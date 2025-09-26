def get_answer(
    user_input: str,
    user_lat: Optional[float] = None,
    user_lng: Optional[float] = None,
    history: Optional[list] = None,
) -> Tuple[str, List[Dict]]:
    """
    ถ้ามีพิกัด → แนะนำเฉพาะ 'ใกล้ฉัน' (ภายใน 15 กม.)
    ถ้าไม่มีพิกัด → ค้นแบบเดิม (category/tambon/keywords)
    ส่งกลับ: (ข้อความสั้นๆ intro+outro, รายการสถานที่ dict สำหรับการ์ด)
    """
    analysis = analyze_query(user_input, history=history)
    category = analysis.get("category")
    tambon_pred = analysis.get("tambon")
    keywords = analysis.get("keywords")

    # ไม่เดาตำบลเอง ถ้าไม่ได้อยู่ในข้อความผู้ใช้
    tambon = _tambon_if_in_text(user_input, tambon_pred)

    # ----- ค้นหาข้อมูล -----
    if user_lat is not None and user_lng is not None:
        # ใกล้ฉันเท่านั้น
        results = search_places_nearby(
            user_lat, user_lng,
            category=category, tambon=tambon, keywords=keywords,
            limit=10, within_km=15
        )
        intro = "เจอสถานที่ใกล้คุณครับ:"
    else:
        # ค้นแบบทั่วไป
        results = search_places(category=category, tambon=tambon, keywords=keywords, limit=10)
        intro = "เจอที่น่าสนใจให้ครับ:"

    # ----- กรองเพิ่มด้วย keywords แบบเข้ม (ถ้ามี) -----
    if keywords and isinstance(keywords, str):
        kw = [k.strip().lower() for k in keywords.split() if k.strip()]
        if kw:
            def ok(row):
                text = " ".join([
                    str(row.get("name") or ""),
                    str(row.get("description") or ""),
                    str(row.get("highlight") or ""),
                ]).lower()
                return all(k in text for k in kw)
            filtered = list(filter(ok, results))
            if filtered:
                results = filtered

    if not results:
        if user_lat is not None and user_lng is not None:
            return ("ยังไม่พบสถานที่ใกล้คุณในรัศมี 15 กม. ครับ ลองระบุประเภทหรือคีย์เวิร์ดเพิ่มได้นะครับ", [])
        return ("ยังไม่พบสถานที่ที่ตรงกับคำค้นครับ ลองเพิ่มคีย์เวิร์ดหรือตำบล", [])

    # เพิ่ม outro สั้นๆ
    outro = "หวังว่าจะเจอสถานที่ตรงตามที่คุณต้องการนะครับ"
    return (f"{intro}\n\n{outro}", results)
