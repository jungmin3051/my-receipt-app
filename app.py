import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import re
from PIL import Image, ImageOps
import pytesseract
import io
import numpy as np
import cv2
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Side, Font

st.set_page_config(page_title="영수증 정리기", layout="centered")

# 1. 구글 시트 연결 (DB & 명부 통합)
# 주의: Streamlit Cloud 설정(Secrets)에 시트 URL이 등록되어 있어야 합니다.
conn = st.connection("gsheets", type=GSheetsConnection)

# 2. 데이터 불러오기 (에러 방지를 위해 빈 데이터프레임 처리)
try:
    staff_df = conn.read(worksheet="Staff")
except:
    staff_df = pd.DataFrame(columns=["성명", "직책", "법인카드번호"])

try:
    receipt_df = conn.read(worksheet="Sheet1")
except:
    receipt_df = pd.DataFrame(columns=["제출자", "날짜", "식당명", "금액", "비고"])

if 'ocr_cache' not in st.session_state: st.session_state.ocr_cache = {}
if 'temp_data' not in st.session_state: st.session_state.temp_data = {}

st.title("📑 법인카드 영수증 자동 정리")

# --- [사이드바] 1. 신규 직원 등록 섹션 ---
st.sidebar.header("👤 사용자 설정")
with st.sidebar.expander("신규 직원 등록 (처음 한 번만)"):
    new_name = st.text_input("성함", key="new_n")
    new_rank = st.text_input("직책", key="new_r")
    new_card = st.text_input("법인카드번호", key="new_c")
    if st.button("명부에 등록하기"):
        if new_name and new_rank and new_card:
            new_staff = pd.DataFrame([{"성명": new_name, "직책": new_rank, "법인카드번호": new_card}])
            updated_staff = pd.concat([staff_df, new_staff], ignore_index=True)
            conn.update(worksheet="Staff", data=updated_staff)
            st.success("등록 완료! 페이지를 새로고침(F5) 해주세요.")
            st.rerun()
        else:
            st.error("모든 정보를 입력해주세요.")

# --- [사이드바] 2. 직원 선택 ---
user_list = ["선택하세요"] + staff_df["성명"].tolist()
selected_user = st.sidebar.selectbox("사용자 선택", user_list)

if selected_user != "선택하세요":
    user_info = staff_df[staff_df["성명"] == selected_user].iloc[0]
    st.sidebar.info(f"**{user_info['직책']} {selected_user}**님\n\n카드: {user_info['법인카드번호']}")
    
    report_date = st.sidebar.date_input("대상 월 선택", value=datetime.now())
    selected_month = report_date.strftime('%m').lstrip('0')

    # --- 메인: 영수증 처리 ---
    uploaded_files = st.file_uploader("영수증 사진들을 올려주세요", accept_multiple_files=True)

    if uploaded_files:
        for idx, uploaded_file in enumerate(uploaded_files):
            file_key = uploaded_file.name
            
            if file_key not in st.session_state.ocr_cache:
                # 사진 회전 및 전처리
                raw_img = Image.open(uploaded_file)
                img = ImageOps.exif_transpose(raw_img)
                img_array = np.array(img.convert('RGB'))
                gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
                blur = cv2.GaussianBlur(gray, (3,3), 0)
                thresh = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
                
                # OCR 실행
                custom_config = r'--oem 3 --psm 6 -l kor+eng'
                st.session_state.ocr_cache[file_key] = pytesseract.image_to_string(thresh, config=custom_config)
                st.session_state.temp_data[file_key + "_img"] = img
            
            raw_text = st.session_state.ocr_cache[file_key]
            
            # 데이터 추출 로직
            date_match = re.search(r'(\d{4})[-/.](\d{2})[-/.](\d{2})', raw_text)
            try:
                default_date = datetime.strptime(date_match.group(0).replace('.','-').replace('/','-'), '%Y-%m-%d') if date_match else datetime.now()
            except: default_date = datetime.now()
            
            clean_text = raw_text.replace(' ', '')
            price_match = re.search(r'(?:TOTAL|AMOUNT|합계|결제|금액)[:]?\s*([\d,.]+)', clean_text, re.I)
            extracted_price = int(price_match.group(1).replace(',', '').split('.')[0]) if price_match else 0

            with st.form(key=f"form_{file_key}"):
                st.image(st.session_state.temp_data[file_key + "_img"], width=300)
                c1, c2 = st.columns(2)
                with c1: d_val = st.date_input("날짜", default_date, key=f"d_{idx}")
                with c2: s_val = st.text_input("식당명", "식당입력", key=f"s_{idx}")
                p1, p2 = st.columns(2)
                with p1: pr_val = st.number_input("금액", value=extracted_price, key=f"p_{idx}")
                with p2: r_val = st.text_input("비고", "", key=f"r_{idx}")
                
                if st.form_submit_button("서버에 저장하기"):
                    # 구글 시트에 데이터 누적 저장
                    new_receipt = pd.DataFrame([{
                        "제출자": selected_user,
                        "날짜": d_val.strftime('%Y-%m-%d'),
                        "식당명": s_val,
                        "금액": pr_val,
                        "비고": r_val
                    }])
                    updated_receipts = pd.concat([receipt_df, new_receipt], ignore_index=True)
                    conn.update(worksheet="Sheet1", data=updated_receipts)
                    
                    # 로컬 세션에도 임시 저장 (PDF용)
                    st.session_state.temp_data[file_key] = {
                        "날짜": d_val.strftime('%y-%m-%d'), "식당명": s_val, 
                        "금액": pr_val, "비고": r_val, "img": st.session_state.temp_data[file_key + "_img"]
                    }
                    st.success(f"**{s_val}** 저장 완료!", icon=":material/cloud_done:")

        # 저장된 데이터가 있으면 엑셀/PDF 다운로드 버튼 노출
        saved_items = [v for k, v in st.session_state.temp_data.items() if isinstance(v, dict)]
        if saved_items:
            st.divider()
            col1, col2 = st.columns(2)
            # (여기에 이전과 동일한 엑셀/PDF 생성 로직 추가)
            st.info("정리가 완료되었습니다. 위 버튼으로 파일을 다운로드하세요.")
else:
    st.warning("왼쪽 사이드바에서 성함을 선택하거나 신규 등록을 진행해주세요.")
