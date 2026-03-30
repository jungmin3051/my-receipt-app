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

# --- 1. 설정 (선임님 구글 정보) ---
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

# --- 3. 함수 정의 ---
def get_data(sheet_name):
    return conn.read(spreadsheet=SHEET_URL, worksheet=sheet_name, ttl=0)

def process_and_upload(image, filename):
    image = ImageOps.exif_transpose(image)
    image.thumbnail((1000, 1000))
    img_byte_arr = io.BytesIO()
    image.convert("RGB").save(img_byte_arr, format='JPEG', quality=75)
    img_byte_arr.seek(0)
    file_metadata = {'name': filename, 'parents': [DRIVE_FOLDER_ID]}
    media = MediaIoBaseUpload(img_byte_arr, mimetype='image/jpeg')
    file = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
    drive_service.permissions().create(fileId=file.get('id'), body={'type': 'anyone', 'role': 'viewer'}).execute()
    return file.get('webViewLink')

# 세션 초기화
if 'user_info' not in st.session_state: st.session_state.user_info = None
if 'temp_list' not in st.session_state: st.session_state.temp_list = []
if 'ocr_cache' not in st.session_state: st.session_state.ocr_cache = {}

st.title("💳 법인카드 영수증 제출 시스템")

# --- 4. 로그인 / 회원가입 화면 ---
if st.session_state.user_info is None:
    tab1, tab2 = st.tabs(["🔒 로그인", "📝 신규 등록"])
    
    with tab1:
        staff_df = get_data("Staff")
        l_name = st.text_input("성함 (한정민)")
        l_pw = st.text_input("비밀번호 (3051)", type="password")
        if st.button("로그인 하기"):
            staff_df['성명'] = staff_df['성명'].astype(str).str.strip()
            staff_df['비밀번호'] = staff_df['비밀번호'].astype(str).str.strip()
            user_match = staff_df[(staff_df["성명"] == l_name.strip()) & (staff_df["비밀번호"] == str(l_pw).strip())]
            if not user_match.empty:
                st.session_state.user_info = user_match.iloc[0].to_dict()
                st.rerun()
            else:
                st.error("정보가 일치하지 않습니다.")

    with tab2:
        st.subheader("새 사용자를 등록하세요.")
        r_name = st.text_input("성함 (신규)", key="reg_name")
        r_pos = st.text_input("직책 (예: 선임)", key="reg_pos")
        r_card = st.text_input("법인카드 번호", key="reg_card")
        r_pw = st.text_input("비밀번호 (숫자 4자리)", max_chars=4, key="reg_pw")
        
        if st.button("등록 완료"):
            if r_name and r_pw:
                new_row = pd.DataFrame([{"성명": r_name, "직책": r_pos, "법인카드번호": r_card, "비밀번호": str(r_pw)}])
                existing_df = get_data("Staff")
                updated_df = pd.concat([existing_df, new_row], ignore_index=True)
                conn.update(spreadsheet=SHEET_URL, worksheet="Staff", data=updated_df)
                st.success("등록되었습니다! 로그인 탭에서 로그인해 주세요.")
            else:
                st.warning("이름과 비밀번호를 입력해 주세요.")

# --- 5. 영수증 처리 기능 (로그인 시 노출) ---
else:
    user = st.session_state.user_info
    st.sidebar.success(f"✅ {user['성명']}님 접속 중")
    if st.sidebar.button("로그아웃"):
        st.session_state.user_info = None
        st.rerun()

    uploaded_files = st.file_uploader("영수증 사진 업로드", accept_multiple_files=True)

    if uploaded_files:
        for idx, file in enumerate(uploaded_files):
            if file.name not in st.session_state.ocr_cache:
                with st.spinner(f'{file.name} 분석 중...'):
                    img = Image.open(file)
                    url = process_and_upload(img, f"{user['성명']}_{datetime.now().strftime('%m%d')}_{file.name}")
                    
                    # OCR 처리
                    arr = np.array(img.convert('RGB'))
                    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
                    txt = pytesseract.image_to_string(gray, config=r'--oem 3 --psm 6 -l kor+eng')
                    price_match = re.search(r'(?:합계|결제|금액)[:]?\s*([\d,.]+)', txt.replace(' ', ''))
                    price = int(price_match.group(1).replace(',', '').split('.')[0]) if price_match else 0
                    st.session_state.ocr_cache[file.name] = {"url": url, "price": price, "img": img}

            res = st.session_state.ocr_cache[file.name]
            with st.expander(f"📷 {file.name} 내역 확인", expanded=True):
                c1, c2 = st.columns([1, 2])
                with c1: st.image(res["img"])
                with c2:
                    s_name = st.text_input("식당명", key=f"s_{idx}")
                    p_val = st.number_input("금액", value=res["price"], key=f"p_{idx}")
                    if st.button("목록 추가", key=f"b_{idx}"):
                        st.session_state.temp_list.append({
                            "제출자": user['성명'], "날짜": datetime.now().strftime('%Y-%m-%d'),
                            "식당명": s_name, "금액": p_val, "사진링크": res["url"]
                        })
                        st.toast("목록에 추가되었습니다.")

    if st.session_state.temp_list:
        st.divider()
        st.subheader("📋 제출 대기 목록")
        st.table(pd.DataFrame(st.session_state.temp_list))
        if st.button("🚀 구글 시트로 전송"):
            main_db = get_data("Sheet1")
            new_df = pd.DataFrame(st.session_state.temp_list)
            updated_db = pd.concat([main_db, new_df], ignore_index=True)
            conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated_db)
            st.session_state.temp_list = []
            st.session_state.ocr_cache = {}
            st.success("제출 완료!")
            st.rerun()
