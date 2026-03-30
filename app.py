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
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseUpload

# 0. 기본 설정
st.set_page_config(page_title="영수증 관리 시스템", layout="centered")

# --- 1. 설정 ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1x419Jb6laxcObm4z2nFU_W65Cx-4AxmAjwmE8ouFmjk/edit?usp=sharing"
DRIVE_FOLDER_ID = "1eja2vLLsUeDZhwgU7HVPadb2FhxyCFgr"

# --- 2. 서비스 연결 ---
try:
    creds_dict = st.secrets["connections"]["gsheets"]
    credentials = service_account.Credentials.from_service_account_info(creds_dict)
    drive_service = build('drive', 'v3', credentials=credentials)
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"연결 오류: {e}")

# --- 3. 데이터 로드 함수 (캐시 무효화 추가) ---
def get_data(sheet_name):
    # ttl=0을 주어서 항상 최신 시트를 읽어오도록 합니다.
    return conn.read(spreadsheet=SHEET_URL, worksheet=sheet_name, ttl=0)

# 세션 초기화
if 'user_info' not in st.session_state: st.session_state.user_info = None
if 'temp_list' not in st.session_state: st.session_state.temp_list = []

st.title("💳 법인카드 영수증 제출 시스템")

# --- 4. 로그인 / 회원가입 로직 ---
if st.session_state.user_info is None:
    tab1, tab2 = st.tabs(["🔒 로그인", "📝 신규 등록"])
    
    with tab1:
        staff_df = get_data("Staff")
        l_name = st.text_input("성함")
        l_pw = st.text_input("비밀번호 (4자리)", type="password")
        if st.button("로그인"):
            # 이름과 비밀번호가 일치하는지 확인
            user_match = staff_df[(staff_df["성명"] == l_name) & (staff_df["비밀번호"].astype(str) == str(l_pw))]
            if not user_match.empty:
                st.session_state.user_info = user_match.iloc[0].to_dict()
                st.rerun()
            else:
                st.error("일치하는 정보가 없습니다. 이름과 비밀번호를 확인하세요.")

    with tab2:
        r_name = st.text_input("성함 (신규)")
        r_pos = st.text_input("직책 (선임/책임 등)")
        r_card = st.text_input("법인카드 번호")
        r_pw = st.text_input("비밀번호 숫자 4자리", max_chars=4)
        if st.button("등록하기"):
            new_data = pd.DataFrame([{"성명": r_name, "직책": r_pos, "법인카드번호": r_card, "비밀번호": r_pw}])
            old_data = get_data("Staff")
            updated_data = pd.concat([old_data, new_data], ignore_index=True)
            conn.update(spreadsheet=SHEET_URL, worksheet="Staff", data=updated_data)
            st.success("등록 완료! 로그인 탭에서 로그인해 주세요.")

# --- 5. 영수증 업로드 (로그인 성공 시에만 보임) ---
else:
    user = st.session_state.user_info
    st.sidebar.success(f"✅ {user['성명']} {user['직책']}님")
    if st.sidebar.button("로그아웃"):
        st.session_state.user_info = None
        st.rerun()

    uploaded_file = st.file_uploader("영수증 사진 업로드")
    if uploaded_file:
        st.write("사진 분석 중...")
        # (이후 영수증 처리 로직...)
