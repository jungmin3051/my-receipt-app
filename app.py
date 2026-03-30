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
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

st.set_page_config(page_title="영수증 정리기", layout="centered")

# 1. 연결 설정 (ID 고정으로 속도 향상)
SHEET_URL = "https://docs.google.com/spreadsheets/d/1x419Jb6laxcObm4z2nFU_W65Cx-4AxmAjwmE8ouFmjk/edit?usp=sharing"
conn = st.connection("gsheets", type=GSheetsConnection)

# 2. 데이터 초기 로드 (캐시 사용으로 로딩 단축)
@st.cache_data(ttl=60)
def load_data(worksheet):
    return conn.read(spreadsheet=SHEET_URL, worksheet=worksheet)

try:
    staff_df = load_data("Staff")
except:
    staff_df = pd.DataFrame(columns=["성명", "직책", "법인카드번호"])

# 세션 상태 초기화
if 'ocr_cache' not in st.session_state: st.session_state.ocr_cache = {}
if 'temp_data' not in st.session_state: st.session_state.temp_data = []

st.title("📑 법인카드 영수증 자동 정리")

# --- [사이드바] 사용자 설정 ---
st.sidebar.header("👤 사용자 설정")
user_list = ["선택하세요"] + staff_df["성명"].tolist()
selected_user = st.sidebar.selectbox("사용자 선택", user_list)

if selected_user != "선택하세요":
    user_info = staff_df[staff_df["성명"] == selected_user].iloc[0]
    st.sidebar.info(f"**{user_info['직책']} {selected_user}**님\n카드: {user_info['법인카드번호']}")
    
    # --- 메인: 영수증 업로드 ---
    uploaded_files = st.file_uploader("영수증 사진들을 올려주세요", accept_multiple_files=True)

    if uploaded_files:
        for idx, uploaded_file in enumerate(uploaded_files):
            file_key = uploaded_file.name
            
            if file_key not in st.session_state.ocr_cache:
                with st.spinner(f'{file_key} 분석 중...'):
                    raw_img = Image.open(uploaded_file)
                    img = ImageOps.exif_transpose(raw_img)
                    # OCR 최적화: 크기 조정으로 속도 향상
                    img.thumbnail((800, 800)) 
                    img_array = np.array(img.convert('RGB'))
                    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
                    
                    custom_config = r'--oem 3 --psm 6 -l kor+eng'
                    st.session_state.ocr_cache[file_key] = pytesseract.image_to_string(gray, config=custom_config)
                    st.session_state.ocr_cache[file_key + "_img"] = img
            
            raw_text = st.session_state.ocr_cache[file_key]
            
            # 정보 추출
            date_match = re.search(r'(\d{4})[-/.](\d{2})[-/.](\d{2})', raw_text)
            try:
                default_date = datetime.strptime(date_match.group(0).replace('.','-').replace('/','-'), '%Y-%m-%d') if date_match else datetime.now()
            except: default_date = datetime.now()
            
            clean_text = raw_text.replace(' ', '')
            price_match = re.search(r'(?:합계|결제|금액)[:]?\s*([\d,.]+)', clean_text)
            extracted_price = int(price_match.group(1).replace(',', '').split('.')[0]) if price_match else 0

            with st.expander(f"📷 영수증 확인: {file_key}", expanded=True):
                st.image(st.session_state.ocr_cache[file_key + "_img"], width=200)
                c1, c2, c3, c4 = st.columns(4)
                d_val = c1.date_input("날짜", default_date, key=f"d_{idx}")
                s_val = c2.text_input("식당명", "식당입력", key=f"s_{idx}")
                pr_val = c3.number_input("금액", value=extracted_price, key=f"p_{idx}")
                r_val = c4.text_input("비고", "", key=f"r_{idx}")
                
                if st.button("목록에 추가", key=f"btn_{idx}"):
                    st.session_state.temp_data.append({
                        "제출자": selected_user, "날짜": d_val.strftime('%Y-%m-%d'),
                        "식당명": s_val, "금액": pr_val, "비고": r_val
                    })
                    st.toast(f"{s_val} 추가됨!")

    # --- 저장 및 다운로드 섹션 ---
    if st.session_state.temp_data:
        st.divider()
        st.subheader("📋 저장 대기 목록")
        temp_df = pd.DataFrame(st.session_state.temp_data)
        st.table(temp_df)
        
        col1, col2 = st.columns(2)
        
        if col1.button("🚀 시트에 일괄 저장하기 (한 번에!)"):
            with st.spinner('시트 업데이트 중...'):
                current_receipts = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1")
                updated_df = pd.concat([current_receipts, temp_df], ignore_index=True)
                conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated_df)
                st.session_state.temp_data = [] # 초기화
                st.success("모든 영수증이 성공적으로 저장되었습니다!")
                st.rerun()

        # 엑셀 다운로드 기능 복구
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            temp_df.to_excel(writer, index=False, sheet_name='영수증현황')
        
        col2.download_button(
            label="📥 엑셀 파일 다운로드",
            data=output.getvalue(),
            file_name=f"영수증정리_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
else:
    st.warning("왼쪽에서 성함을 선택해 주세요.")
