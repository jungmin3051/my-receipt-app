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

# 데이터 유지 및 중복 방지 (dict 구조로 변경)
if 'user_name' not in st.session_state:
    st.session_state.user_name = "한정민"
if 'data_dict' not in st.session_state:
    st.session_state.data_dict = {} # 파일명을 키로 해서 덮어쓰기 가능하게 함

st.title("📑 법인카드 영수증 자동 정리")

st.session_state.user_name = st.sidebar.text_input("성명", st.session_state.user_name)
report_month = st.sidebar.date_input("대상 월 선택")

# 속도 개선: 파일 업로드 시점에만 OCR 실행
uploaded_files = st.file_uploader("영수증 사진들을 올려주세요", accept_multiple_files=True)

if uploaded_files:
    for idx, uploaded_file in enumerate(uploaded_files):
        # 이미 확정된 데이터가 있는지 확인 (수정 모드 지원)
        file_key = uploaded_file.name
        
        # 속도 최적화: 처음 올릴 때만 OCR 실행
        if file_key not in st.session_state.get('ocr_cache', {}):
            img = Image.open(uploaded_file)
            # lang='kor'만 지정하여 속도 향상
            raw_text = pytesseract.image_to_string(img, lang='kor')
            if 'ocr_cache' not in st.session_state: st.session_state.ocr_cache = {}
            st.session_state.ocr_cache[file_key] = raw_text
        
        raw_text = st.session_state.ocr_cache[file_key]
        clean_text = raw_text.replace(' ', '')

        # 1. 날짜 추출 및 변환
        date_match = re.search(r'(\d{4})[-/.](\d{2})[-/.](\d{2})', raw_text)
        extracted_date = f"{date_match.group(1)[2:]}-{date_match.group(2)}-{date_match.group(3)}" if date_match else datetime.now().strftime('%y-%m-%d')
        
        # 2. 식사 구분 (선임님 기준 시간표)
        time_match = re.search(r'(\d{2}):(\d{2})', raw_text)
        meal_type = "석식"
        if time_match:
            h, m = map(int, time_match.groups())
            if time(3,1) <= time(h,m) <= time(10,0): meal_type = "조식"
            elif time(10,1) <= time(h,m) <= time(15,0): meal_type = "중식"

        # 3. 금액 및 식당명
        price_match = re.search(r'(?:합계|결제|금액)[:]?([\d,]{3,})', clean_text)
        extracted_price = int(price_match.group(1).replace(',', '')) if price_match else 0
        store_match = re.search(r'(?:상호|매장명)[:]?\s*([^\n\d\(\)/]+)', raw_text)
        extracted_store = store_match.group(1).strip() if store_match else raw_text.split('\n')[0][:15]

        with st.form(key=f"form_{file_key}"):
            st.image(Image.open(uploaded_file), width=300)
            c1, c2, c3 = st.columns([1, 1.5, 1])
            with c1: d_val = st.text_input("날짜", extracted_date, key=f"d_{idx}")
            with c2: s_val = st.text_input("식당명", extracted_store, key=f"s_{idx}")
            with c3: m_val = st.selectbox("구분", ["조식", "중식", "석식"], index=["조식", "중식", "석식"].index(meal_type), key=f"m_{idx}")
            
            p1, p2 = st.columns(2)
            with p1: pr_val = st.number_input("금액", value=extracted_price, key=f"p_{idx}")
            with p2: r_val = st.text_input("비고", "", key=f"r_{idx}")
            
            if st.form_submit_button("확정 (다시 누르면 수정됨)"):
                # 기존 데이터가 있으면 덮어쓰기 (중복 삭제 로직)
                st.session_state.data_dict[file_key] = {
                    "날짜": d_val, "식당명": s_val, "구분": m_val, 
                    "금액": pr_val, "비고": r_val, "img": Image.open(uploaded_file)
                }
                st.success("반영되었습니다!")

    if st.session_state.data_dict:
        # 결제일(날짜) 기준 오름차순 정렬 (선임님 요청: 제일 위가 가장 빠른 날짜)
        sorted_data = sorted(st.session_state.data_dict.values(), key=lambda x: x['날짜'])
        df = pd.DataFrame(sorted_data).drop('img', axis=1)
        st.table(df)

        col_ex, col_pdf = st.columns(2)
        with col_ex:
            output_excel = io.BytesIO()
            with pd.ExcelWriter(output_excel, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, startrow=4, sheet_name='내역서')
            st.download_button("📈 엑셀 다운로드", output_excel.getvalue(), f"내역서_{st.session_state.user_name}.xlsx")

        with col_pdf:
            pdf_buffer = io.BytesIO()
            c = canvas.Canvas(pdf_buffer, pagesize=A4)
            w, h = A4
            pos = [(50, h/2+20, w/2-60, h/2-100), (w/2+10, h/2+20, w/2-60, h/2-100),
                   (50, 50, w/2-60, h/2-100), (w/2+10, 50, w/2-60, h/2-100)]
            
            # 정렬된 순서대로 PDF 생성
            for i, item in enumerate
