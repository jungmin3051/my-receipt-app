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

# 0. 페이지 설정
st.set_page_config(page_title="영수증 등록", layout="wide")

# --- 1. 로그인 체크 (권한 가드) ---
if 'user_info' not in st.session_state or st.session_state.user_info is None:
    st.warning("⚠️ 로그인이 필요한 페이지입니다. 메인 페이지(app.py)에서 로그인해 주세요.")
    st.stop()

user = st.session_state.user_info
st.title(f"📸 {user['성명']} {user['직책']}님 영수증 등록")

# --- 2. 설정 ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1x419Jb6laxcObm4z2nFU_W65Cx-4AxmAjwmE8ouFmjk/edit?usp=sharing"
DRIVE_FOLDER_ID = "1eja2vLLsUeDZhwgU7HVPadb2FhxyCFgr"

# --- 3. 서비스 연결 및 함수 ---
try:
    creds_dict = st.secrets["connections"]["gsheets"]
    credentials = service_account.Credentials.from_service_account_info(creds_dict)
    drive_service = build('drive', 'v3', credentials=credentials)
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"연결 오류: {e}")

def process_and_upload(image, filename):
    image = ImageOps.exif_transpose(image)
    image.thumbnail((1000, 1000))
    img_byte_arr = io.BytesIO()
    image.convert("RGB").save(img_byte_arr, format='JPEG', quality=75)
    img_byte_arr.seek(0)
    file_metadata = {'name': filename, 'parents': [DRIVE_FOLDER_ID]}
    media = MediaIoBaseUpload(img_byte_arr, mimetype='image/jpeg')
    file = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
    # 폴더가 공개 설정이면 아래 권한 추가는 생략 가능
    return file.get('webViewLink')

# 세션 초기화
if 'temp_list' not in st.session_state: st.session_state.temp_list = []
if 'ocr_cache' not in st.session_state: st.session_state.ocr_cache = {}

# --- 4. 영수증 업로드 및 처리 ---
uploaded_files = st.file_uploader("영수증 사진 업로드 (여러 장 가능)", accept_multiple_files=True)

if uploaded_files:
    for idx, file in enumerate(uploaded_files):
        if file.name not in st.session_state.ocr_cache:
            with st.spinner(f'{file.name} 분석 중...'):
                img = Image.open(file)
                url = process_and_upload(img, f"{user['성명']}_{datetime.now().strftime('%m%d')}_{file.name}")
                
                # OCR 분석 (금액 추출)
                arr = np.array(img.convert('RGB'))
                gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
                txt = pytesseract.image_to_string(gray, config=r'--oem 3 --psm 6 -l kor+eng')
                price_match = re.search(r'(?:합계|결제|금액)[:]?\s*([\d,.]+)', txt.replace(' ', ''))
                price = int(price_match.group(1).replace(',', '').split('.')[0]) if price_match else 0
                st.session_state.ocr_cache[file.name] = {"url": url, "price": price, "img": img}

        res = st.session_state.ocr_cache[file.name]
        with st.expander(f"📄 {file.name} 내역 확인/수정", expanded=True):
            col1, col2 = st.columns([1, 2])
            with col1: st.image(res["img"])
            with col2:
                s_name = st.text_input("식당/업체명", key=f"s_{idx}")
                p_val = st.number_input("금액 확인", value=res["price"], key=f"p_{idx}")
                if st.button("임시 목록에 추가", key=f"btn_{idx}"):
                    st.session_state.temp_list.append({
                        "제출자": user['성명'], "날짜": datetime.now().strftime('%Y-%m-%d'),
                        "식당명": s_name, "금액": p_val, "사진링크": res["url"]
                    })
                    st.toast("추가 완료!")

# --- 5. 최종 제출 ---
if st.session_state.temp_list:
    st.divider()
    st.subheader("📋 제출 대기 중인 영수증")
    st.table(pd.DataFrame(st.session_state.temp_list))
    if st.button("🚀 구글 시트로 최종 전송"):
        main_db = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)
        new_df = pd.DataFrame(st.session_state.temp_list)
        updated_db = pd.concat([main_db, new_df], ignore_index=True)
        conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated_db)
        st.session_state.temp_list = []
        st.session_state.ocr_cache = {}
        st.success("시트 전송 성공! 수고하셨습니다.")
        st.rerun()
