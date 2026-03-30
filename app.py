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
    # GSheets 연결
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"연결 오류: {e}")

# 세션 초기화
if 'user_info' not in st.session_state: st.session_state.user_info = None
if 'temp_list' not in st.session_state: st.session_state.temp_list = []

st.title("💳 법인카드 영수증 제출 시스템")

# --- 3. 데이터 로드 (에러 방지용 안전 장치 추가) ---
def get_staff_data():
    try:
        # ttl=0으로 설정하여 캐시 문제 방지
        df = conn.read(spreadsheet=SHEET_URL, worksheet="Staff", ttl=0)
        return df
    except Exception as e:
        # 시트를 못 읽어올 경우 빈 표라도 반환해서 에러 방지
        return pd.DataFrame(columns=["성명", "직책", "법인카드번호", "비밀번호"])

# --- 4. 로그인 / 회원가입 로직 ---
if st.session_state.user_info is None:
    tab1, tab2 = st.tabs(["🔒 로그인", "📝 신규 등록"])
    
    with tab1:
        staff_df = get_staff_data()
        l_name = st.text_input("성함 (시트에 적힌 그대로)")
        l_pw = st.text_input("비밀번호 (숫자 4자리)", type="password")
        
        if st.button("로그인"):
            if not staff_df.empty:
                # 데이터 타입 통일 (전부 문자로 바꿔서 비교)
                staff_df['성명'] = staff_df['성명'].astype(str).str.strip()
                staff_df['비밀번호'] = staff_df['비밀번호'].astype(str).str.strip()
                
                user_match = staff_df[(staff_df["성명"] == l_name.strip()) & (staff_df["비밀번호"] == str(l_pw).strip())]
                
                if not user_match.empty:
                    st.session_state.user_info = user_match.iloc[0].to_dict()
                    st.success("로그인 성공!")
                    st.rerun()
                else:
                    st.error("일치하는 정보가 없습니다. 이름과 비밀번호를 확인하세요.")
            else:
                st.error("시트에서 데이터를 가져올 수 없습니다. 'Staff' 탭을 확인해 주세요.")

    with tab2:
        st.info("처음 사용하시는 경우 정보를 입력하고 등록해 주세요.")
        r_name = st.text_input("성함 (신규)")
        r_pos = st.text_input("직책 (예: 선임)")
        r_card = st.text_input("법인카드 번호")
        r_pw = st.text_input("비밀번호 (숫자 4자리만)", max_chars=4)
        
        if st.button("등록하기"):
            if r_name and r_pw:
                new_row = pd.DataFrame([{"성명": r_name, "직책": r_pos, "법인카드번호": r_card, "비밀번호": str(r_pw)}])
                existing_df = get_staff_data()
                updated_df = pd.concat([existing_df, new_row], ignore_index=True)
                conn.update(spreadsheet=SHEET_URL, worksheet="Staff", data=updated_df)
                st.success("등록 완료! 이제 로그인 탭에서 로그인을 시도하세요.")
            else:
                st.warning("이름과 비밀번호는 필수 입력입니다.")

# --- 5. 영수증 업로드 (로그인 완료 후) ---
else:
    user = st.session_state.user_info
    st.sidebar.success(f"✅ {user['성명']} {user['직책']}님 로그인 중")
    if st.sidebar.button("로그아웃"):
        st.session_state.user_info = None
        st.rerun()
    
    st.write("📸 영수증 사진을 올려주세요.")
    # 영수증 처리 로직 계속...
