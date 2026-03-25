import streamlit as st
import pandas as pd
from datetime import datetime, time
import re
from PIL import Image
import pytesseract
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader

st.set_page_config(page_title="영수증 정리기", layout="centered")

# 1. 브라우저 새로고침 시 데이터 유지 (사용자 정보)
if 'user_name' not in st.session_state:
    st.session_state.user_name = "한정민"
if 'data_list' not in st.session_state:
    st.session_state.data_list = []

st.title("📑 법인카드 영수증 자동 정리")

# 사이드바 설정
st.session_state.user_name = st.sidebar.text_input("성명", st.session_state.user_name)
report_month = st.sidebar.date_input("대상 월 선택")

uploaded_files = st.file_uploader("영수증 사진들을 올려주세요", accept_multiple_files=True)

if uploaded_files:
    for idx, uploaded_file in enumerate(uploaded_files):
        img = Image.open(uploaded_file)
        try:
            raw_text = pytesseract.image_to_string(img, lang='kor+eng')
            clean_text = raw_text.replace(' ', '')
        except:
            raw_text = ""; clean_text = ""

        # --- [추출 로직: 선임님 맞춤형] ---
        
        # 1. 날짜 추출 (26-03-11 형식으로 변환)
        date_match = re.search(r'(\d{4})[-/.](\d{2})[-/.](\d{2})', raw_text)
        if date_match:
            yy, mm, dd = date_match.group(1)[2:], date_match.group(2), date_match.group(3)
            extracted_date = f"{yy}-{mm}-{dd}"
        else:
            extracted_date = datetime.now().strftime('%y-%m-%d')
        
        # 2. 식사 구분 (03:01~10:00 조식 / 10:01~15:00 중식 / 그외 석식)
        time_match = re.search(r'(\d{2}):(\d{2})', raw_text)
        meal_type = "석식"
        if time_match:
            h, m = map(int, time_match.groups())
            curr_time = time(h, m)
            if time(3, 1) <= curr_time <= time(10, 0): meal_type = "조식"
            elif time(10, 1) <= curr_time <= time(15, 0): meal_type = "중식"
        
        # 3. 금액 추출
        price_match = re.search(r'(?:합계|받을|결제|금액)[:]?([\d,]{3,})', clean_text)
        extracted_price = int(price_match.group(1).replace(',', '')) if price_match else 0
        
        # 4. 식당명 추출
        store_match = re.search(r'(?:상호|매장명|가맹점명)[:]?\s*([^\n\d\(\)/]+)', raw_text)
        if store_match:
            extracted_store = store_match.group(1).strip()
        else:
            lines = [l.strip() for l in raw_text.split('\n') if len(l.strip()) > 2]
            extracted_store = lines[0] if lines else "식당 직접 입력"

        # --- [입력 폼: 선임님이 요청한 순서대로 배치] ---
        with st.form(key=f"form_{uploaded_file.name}_{idx}"):
            st.image(img, width=300)
            
            # 한 줄에 날짜, 식당명, 구분 배치
            c1, c2, c3 = st.columns([1, 1.5, 1])
            with c1: d_val = st.text_input("날짜", extracted_date, key=f"d_{idx}")
            with c2: s_val = st.text_input("식당명", extracted_store, key=f"s_{idx}")
            with c3: m_val = st.selectbox("구분", ["조식", "중식", "석식"], 
                                         index=["조식", "중식", "석식"].index(meal_type), key=f"m_{idx}")
            
            # 한 줄에 금액, 비고 배치
            p1, p2 = st.columns(2)
            with p1: pr_val = st.number_input("금액", value=extracted_price, key=f"p_{idx}")
            with p2: r_val = st.text_input("비고(달러 등)", "", key=f"r_{idx}")
            
            if st.form_submit_button(f"확정"):
                # 선임님 요청 엑셀 순서: 날짜 / 식당명 / 구분 / 금액 / 비고
                st.session_state.data_list.append({
                    "날짜": d_val, "식당명": s_val, "구분": m_val, 
                    "금액": pr_val, "비고": r_val, "img": img
                })
                st.success("추가되었습니다!")

    if st.session_state.data_list:
        df = pd.DataFrame(st.session_state.data_list).drop('img', axis=1)
        df = df.sort_values(by="날짜")
        st.table(df)

        col_ex, col_pdf = st.columns(2)
        with col_ex:
            output_excel = io.BytesIO()
            with pd.ExcelWriter(output_excel, engine='openpyxl') as writer:
                # 5행부터 데이터 시작 (선임님 엑셀 양식)
                df.to_excel(writer, index=False, startrow=4, sheet_name='내역서')
            st.download_button("📈 엑셀 다운로드", output_excel.getvalue(), f"내역서_{st.session_state.user_name}.xlsx")

        with col_pdf:
            pdf_buffer = io.BytesIO()
            c = canvas.Canvas(pdf_buffer, pagesize=A4)
            w, h = A4
            pos = [(50, h/2+20, w/2-60, h/2-100), (w/2+10, h/2+20, w/2-60, h/2-100),
                   (50, 50, w/2-60, h/2-100), (w/2+10, 50, w/2-60, h/2-100)]
            
            for i, item in enumerate(st.session_state.data_list):
                if i > 0 and i % 4 == 0: c.showPage()
                px, py, pw, ph = pos[i % 4]
                img_temp = io.BytesIO()
                item['img'].save(img_temp, format='JPEG')
