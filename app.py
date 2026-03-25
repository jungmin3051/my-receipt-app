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

# 페이지 설정
st.set_page_config(page_title="영수증 정리기", layout="centered")

# --- 1. 구글 시트 연결 설정 ---
# 선임님이 주신 정확한 주소를 코드에 고정합니다.
SHEET_URL = "https://docs.google.com/spreadsheets/d/1x419Jb6laxcObm4z2nFU_W65Cx-4AxmAjwmE8ouFmjk/edit?usp=sharing"

conn = st.connection("gsheets", type=GSheetsConnection)

# --- 2. 데이터 불러오기 ---
try:
    # 명부(Staff) 불러오기
    staff_df = conn.read(spreadsheet=SHEET_URL, worksheet="Staff")
except Exception as e:
    st.error(f"명부를 불러오지 못했습니다. 시트의 'Staff' 탭을 확인하세요: {e}")
    staff_df = pd.DataFrame(columns=["성명", "직책", "법인카드번호"])

try:
    # 영.수증 내역(Sheet1) 불러오기
    receipt_df = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1")
except Exception as e:
    receipt_df = pd.DataFrame(columns=["제출자", "날짜", "식당명", "금액", "비고"])

# 세션 상태 초기화
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
            # 수정한 명부 저장
            conn.update(spreadsheet=SHEET_URL, worksheet="Staff", data=updated_staff)
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
    
    # --- 메인: 영수증 처리 ---
    uploaded_files = st.file_uploader("영수증 사진들을 올려주세요", accept_multiple_files=True)

    if uploaded_files:
        for idx, uploaded_file in enumerate(uploaded_files):
            file_key = uploaded_file.name
            
            if file_key not in st.session_state.ocr_cache:
                # 사진 전처리 및 OCR
                raw_img = Image.open(uploaded_file)
                img = ImageOps.exif_transpose(raw_img)
                img_array = np.array(img.convert('RGB'))
                gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
                blur = cv2.GaussianBlur(gray, (3,3), 0)
                thresh = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
                
                custom_config = r'--oem 3 --psm 6 -l kor+eng'
                st.session_state.ocr_cache[file_key] = pytesseract.image_to_string(thresh, config=custom_config)
                st.session_state.temp_data[file_key + "_img"] = img
            
            raw_text = st.session_state.ocr_cache[file_key]
            
            # 데이터 추출 (날짜, 금액)
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
                    # 구글 시트에 데이터 저장
                    new_receipt = pd.DataFrame([{
                        "제출자": selected_user,
                        "날짜": d_val.strftime('%Y-%m-%d'),
                        "식당명": s_val,
                        "금액": pr_val,
                        "비고": r_val
                    }])
                    # 최신 데이터를 다시 읽어와서 합치기 (동시성 방지)
                    current_receipts = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1")
                    updated_receipts = pd.concat([current_receipts, new_receipt], ignore_index=True)
                    conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated_receipts)
                    
                    st.success(f"**{s_val}** 저장 완료!", icon="✅")
else:
    st.warning("사이드바에서 성함을 선택하거나 신규 등록을 진행해주세요.")
