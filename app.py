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

# 1. 브라우저 종료 후에도 데이터 유지 (성명 등)
if 'user_name' not in st.session_state:
    st.session_state.user_name = "한정민"
if 'data_list' not in st.session_state:
    st.session_state.data_list = []

st.title("📑 법인카드 영수증 자동 정리")

# 사이드바 설정 (사용자 정보 유지)
st.session_state.user_name = st.sidebar.text_input("성명", st.session_state.user_name)
report_month = st.sidebar.date_input("대상 월 선택")

uploaded_files = st.file_uploader("영수증 사진들을 올려주세요", accept_multiple_files=True)

if uploaded_files:
    for idx, uploaded_file in enumerate(uploaded_files):
        img = Image.open(uploaded_file)
        try:
            raw_text = pytesseract.image_to_string(img, lang='kor+eng')
            # 텍스트 전처리 (공백 제거 버전도 준비)
            clean_text = raw_text.replace(' ', '')
        except:
            raw_text = ""; clean_text = ""

        # --- [추출 로직 고도화] ---
        
        # 1. 날짜 추출 및 형식 변환 (YYYY-MM-DD -> YY-MM-DD)
        date_match = re.search(r'(\d{4})[-/.](\d{2})[-/.](\d{2})', raw_text)
        if date_match:
            yy = date_match.group(1)[2:]
            mm = date_match.group(2)
            dd = date_match.group(3)
            extracted_date = f"{yy}-{mm}-{dd}"
        else:
            extracted_date = datetime.now().strftime('%y-%m-%d')
        
        # 2. 식사 구분 (선임님 기준: 03:01~10:00 조식 / 10:01~15:00 중식 / 그외 석식)
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
        
        # 4. 식당명 추출 (상호, 매장명 키워드 우선, 없으면 첫 줄 유효 텍스트)
        store_match = re.search(r'(?:상호|매장명|가맹점명)[:]?\s*([^\n\d\(\)/]+)', raw_text)
        if store_match:
            extracted_store = store_match.group(1).strip()
        else:
            # 키워드 없을 시 상단 3줄 중 가장 긴 한글 텍스트 선택
            lines = [l.strip() for l in raw_text.split('\n') if len(l.strip()) > 2]
            extracted_store = lines[0] if lines else "식당 직접 입력"

        # --- [추출 로직 끝] ---

        with st.form(key=f"form_{uploaded_file.name}_{idx}"):
            st.image(img, width=300)
            c1, c2, c3 = st.columns(3)
            with c1: date_val = st.text_input("일자", extracted_date, key=f"d_{idx}")
            with c2: store_val = st.text_input("내용(식당명)", extracted_store, key=f"s_{idx}")
            with c3: meal_val = st.selectbox("구분", ["조식", "중식
