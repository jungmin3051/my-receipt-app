import streamlit as st
import pandas as pd
from datetime import datetime, time
import re
from PIL import Image, ImageOps
import pytesseract
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Side, Font

st.set_page_config(page_title="영수증 정리기", layout="centered")

# 1. 사용자 정보 및 데이터 저장소 (세션 유지)
if 'user_name' not in st.session_state: st.session_state.user_name = "한정민"
if 'data_dict' not in st.session_state: st.session_state.data_dict = {} 
if 'ocr_cache' not in st.session_state: st.session_state.ocr_cache = {}

st.title("📑 법인카드 영수증 자동 정리")

# 사이드바: 선임님 고정 정보 입력
st.session_state.user_name = st.sidebar.text_input("성명", st.session_state.user_name)
user_rank = st.sidebar.text_input("직책", "선임")
card_num = st.sidebar.text_input("법인카드번호", "4265-8699-8653-1838")
report_date = st.sidebar.date_input("대상 월 선택", value=datetime.now())
selected_month = report_date.strftime('%m').lstrip('0')

uploaded_files = st.file_uploader("영수증 사진들을 올려주세요", accept_multiple_files=True)

if uploaded_files:
    for idx, uploaded_file in enumerate(uploaded_files):
        file_key = uploaded_file.name
        
        # OCR 속도 및 인식률 최적화
        if file_key not in st.session_state.ocr_cache:
            img = Image.open(uploaded_file)
            gray_img = ImageOps.grayscale(img)
            st.session_state.ocr_cache[file_key] = pytesseract.image_to_string(gray_img, lang='kor+eng')
        
        raw_text = st.session_state.ocr_cache[file_key]
        clean_text = raw_text.replace(' ', '')

        # 데이터 추출 (날짜, 시간, 금액, 식당)
        is_dollar = not bool(re.search(r'[ㄱ-ㅎㅏ-ㅣ가-힣]', raw_text))
        date_match = re.search(r'(\d{4})[-/.](\d{2})[-/.](\d{2})', raw_text)
        try:
            default_date = datetime.strptime(date_match.group(0).replace('.','-').replace('/','-'), '%Y-%m-%d') if date_match else datetime.now()
        except: default_date = datetime.now()
        
        price_match = re.search(r'(?:TOTAL|AMOUNT|합계|결제|금액)[:]?\s*([\d,.]+)', clean_text, re.I)
        extracted_price = int(price_match.group(1).replace(',', '').split('.')[0]) if price_match else 0
        lines = [l.strip() for l in raw_text.split('\n') if len(l.strip()) > 2]
        extracted_store = lines[0] if lines else "식당 직접 입력"

        with st.form(key=f"form_{file_key}"):
            st.image(Image.open(uploaded_file), width=300)
            c1, c2, c3 = st.columns([1, 1.5, 1])
            with c1: d_val = st.date_input("날짜", default_date, key=f"d_{idx}")
            with c2: s_val = st.text_input("식당명", extracted_store, key=f"s_{idx}")
            with c3: m_val = st.selectbox("구분", ["조식", "중식", "석식"], key=f"m_{idx}")
            
            p1, p2 = st.columns(2)
            with p1: pr_val = st.number_input("금액", value=extracted_price, key=f"p_{idx}")
            with p2: r_val = st.text_input("비고", "달러 결제" if is_dollar else "", key=f"r_{idx}")
            
            if st.form_submit_button("확정"):
                # 수정 시 덮어쓰기 로직
                st.session_state.data_dict[file_key] = {
                    "날짜": d_val.strftime('%y-%m-%d'), "식당명": s_val, "구분": m_val, 
                    "금액": pr_val, "비고": r_val, "img": Image.open(uploaded_file)
                }
                st.success
