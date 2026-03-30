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
st.set_page_config(page_title="영수증 정리기 V2", layout="centered")

# --- 1. 설정 정보 (선임님 폴더 ID 적용 완료) ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1x419Jb6laxcObm4z2nFU_W65Cx-4AxmAjwmE8ouFmjk/edit?usp=sharing"
DRIVE_FOLDER_ID = "1eja2vLLsUeDZhwgU7HVPadb2FhxyCFgr" 

# --- 2. 구글 서비스 연결 설정 ---
try:
    creds_dict = st.secrets["connections"]["gsheets"]
    credentials = service_account.Credentials.from_service_account_info(creds_dict)
    drive_service = build('drive', 'v3', credentials=credentials)
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"연결 설정 오류 (Secrets를 확인하세요): {e}")

# --- 3. 이미지 압축 및 업로드 함수 (용량 최적화) ---
def process_and_upload(image, filename):
    image = ImageOps.exif_transpose(image)
    image.thumbnail((1000, 1000))
    gray_img = image.convert("L") # 흑백 전환으로 용량 절감
    
    img_byte_arr = io.BytesIO()
    gray_img.save(img_byte_arr, format='JPEG', quality=75)
    img_byte_arr.seek(0)
    
    file_metadata = {'name': filename, 'parents': [DRIVE_FOLDER_ID]}
    media = MediaIoBaseUpload(img_byte_arr, mimetype='image/jpeg')
    file = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
    
    drive_service.permissions().create(fileId=file.get('id'), body={'type': 'anyone', 'role': 'viewer'}).execute()
    return file.get('webViewLink')

# --- 4. 데이터 로드 ---
@st.cache_data(ttl=60)
def load_staff_data():
    try:
        return conn.read(spreadsheet=SHEET_URL, worksheet="Staff")
    except:
        return pd.DataFrame(columns=["성명", "직책", "법인카드번호"])

staff_df = load_staff_data()

if 'ocr_cache' not in st.session_state: st.session_state.ocr_cache = {}
if 'temp_data' not in st.session_state: st.session_state.temp_data = []

st.title("📑 스마트 법인카드 영수증 정리기")

# --- [사이드바] 사용자 선택 ---
st.sidebar.header("👤 사용자 설정")
user_list = ["선택하세요"] + staff_df["성명"].tolist()
selected_user = st.sidebar.selectbox("사용자 선택", user_list)

if selected_user != "선택하세요":
    user_info = staff_df[staff_df["성명"] == selected_user].iloc[0]
    st.sidebar.info(f"**{user_info['직책']} {selected_user}**님\n카드: {user_info['법인카드번호']}")
    
    # --- 5. 영수증 업로드 및 처리 ---
    uploaded_files = st.file_uploader("영수증 사진들을 올려주세요", accept_multiple_files=True)

    if uploaded_files:
        for idx, uploaded_file in enumerate(uploaded_files):
            file_key = uploaded_file.name
            
            if file_key not in st.session_state.ocr_cache:
                with st.spinner(f'{file_key} 분석 및 압축 중...'):
                    raw_img = Image.open(uploaded_file)
                    img_url = process_and_upload(raw_img, f"{selected_user}_{datetime.now().strftime('%m%d')}_{file_key}")
                    
                    img_array = np.array(raw_img.convert('RGB'))
                    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
                    ocr_text = pytesseract.image_to_string(gray, config=r'--oem 3 --psm 6 -l kor+eng')
                    
                    clean_text = ocr_text.replace(' ', '')
                    price_match = re.search(r'(?:합계|결제|금액)[:]?\s*([\d,.]+)', clean_text)
                    extracted_price = int(price_match.group(1).replace(',', '').split('.')[0]) if price_match else 0
                    
                    st.session_state.ocr_cache[file_key] = {
                        "url": img_url, "text": ocr_text, "img": raw_img, "price": extracted_price
                    }

            res = st.session_state.ocr_cache[file_key]
            
            with st.expander(f"📷 영수증 확인: {file_key}", expanded=True):
                st.image(res["img"], width=250)
                c1, c2, c3 = st.columns(3)
                s_val = c1.text_input("식당명", "식당입력", key=f"s_{idx}")
                pr_val = c2.number_input("금액", value=res["price"], key=f"p_{idx}")
                r_val = c3.text_input("비고", "", key=f"r_{idx}")
                
                if st.button("✅ 목록에 추가", key=f"add_{idx}"):
                    st.session_state.temp_data.append({
                        "제출자": selected_user,
                        "날짜": datetime.now().strftime('%Y-%m-%d'),
                        "식당명": s_val,
                        "금액": pr_val,
                        "비고": r_val,
                        "사진링크": res["url"]
                    })
                    st.toast(f"{s_val} 추가되었습니다!")

    # --- 6. 일괄 저장 및 엑셀 다운로드 ---
    if st.session_state.temp_data:
        st.divider()
        st.subheader("📋 현재 추가된 목록")
        temp_df = pd.DataFrame(st.session_state.temp_data)
        st.dataframe(temp_df)
        
        col1, col2 = st.columns(2)
        
        if col1.button("🚀 구글 시트에 최종 저장"):
            with st.spinner('시트 업데이트 중...'):
                current_db = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1")
                final_df = pd.concat([current_db, temp_df], ignore_index=True)
                conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=final_df)
                st.session_state.temp_data = [] 
                st.success("시트에 저장이 완료되었습니다!")
                st.rerun()

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            temp_df.to_excel(writer, index=False)
        
        col2.download_button(
            label="📥 엑셀 파일 다운로드",
            data=output.getvalue(),
            file_name=f"영수증_{selected_user}_{datetime.now().strftime('%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
else:
    st.warning("왼쪽 사이드바에서 성함을 선택해 주세요.")
