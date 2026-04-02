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

# 0. 설정
st.set_page_config(page_title="정민 영수증 동기화 매니저", layout="wide")
SHEET_URL = "https://docs.google.com/spreadsheets/d/1x419Jb6laxcObm4z2nFU_W65Cx-4AxmAjwmE8ouFmjk/edit?usp=sharing"
DRIVE_FOLDER_ID = "1eja2vLLsUeDZhwgU7HVPadb2FhxyCFgr"

# --- 연결 설정 ---
@st.cache_resource
def get_drive_service():
    creds_dict = st.secrets["connections"]["gsheets"]
    credentials = service_account.Credentials.from_service_account_info(creds_dict)
    return build('drive', 'v3', credentials=credentials)

drive_service = get_drive_service()
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 사진 처리 (세로 고정 + 압축 + 업로드) ---
def process_and_upload(image, filename):
    image = ImageOps.exif_transpose(image)
    image.thumbnail((1000, 1000))
    img_byte_arr = io.BytesIO()
    image.convert("RGB").save(img_byte_arr, format='JPEG', quality=70)
    img_byte_arr.seek(0)
    file_metadata = {'name': filename, 'parents': [DRIVE_FOLDER_ID]}
    media = MediaIoBaseUpload(img_byte_arr, mimetype='image/jpeg')
    file = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
    drive_service.permissions().create(fileId=file.get('id'), body={'type': 'anyone', 'role': 'viewer'}).execute()
    return file.get('webViewLink')

st.title("💳 영수증 모바일-PC 동기화")

# 1. 영수증 업로드 (모바일에서 주로 사용)
with st.expander("📸 1단계: 영수증 사진 올리기 (모바일 권장)", expanded=True):
    uploaded_files = st.file_uploader("사진을 선택하면 구글 드라이브로 즉시 저장됩니다", accept_multiple_files=True)
    if uploaded_files:
        for idx, file in enumerate(uploaded_files):
            if f"up_{file.name}" not in st.session_state:
                with st.spinner(f'{file.name} 처리 중...'):
                    img = Image.open(file)
                    url = process_and_upload(img, f"한정민_{datetime.now().strftime('%m%d_%H%M')}_{file.name}")
                    # OCR 분석
                    img_p = ImageOps.exif_transpose(img)
                    arr = np.array(img_p.convert('RGB'))
                    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
                    txt = pytesseract.image_to_string(gray, config=r'--oem 3 --psm 6 -l kor+eng')
                    price_match = re.search(r'(?:합계|결제|금액)[:]?\s*([\d,.]+)', txt.replace(' ', ''))
                    price = int(price_match.group(1).replace(',', '').split('.')[0]) if price_match else 0
                    
                    # 즉시 시트에 '임시' 상태로 저장 (동기화의 핵심)
                    temp_df = pd.DataFrame([{"제출자": "한정민", "날짜": datetime.now().strftime('%Y-%m-%d'), 
                                           "식당명": "미입력", "금액": price, "사진링크": url, "상태": "임시"}])
                    current = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)
                    updated = pd.concat([current, temp_df], ignore_index=True)
                    conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated)
                    st.session_state[f"up_{file.name}"] = True
        st.success("✅ 사진이 드라이브에 저장되었습니다. 이제 PC에서 상세 내용을 수정하세요!")

# 2. 내역 수정 (PC에서 주로 사용)
st.divider()
st.subheader("📝 2단계: 내역 수정 및 확정 (PC 권장)")
data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)
# '임시' 상태인 내역만 가져와서 수정하기
edit_df = data[data["상태"] == "임시"].copy()

if not edit_df.empty:
    for i, row in edit_df.iterrows():
        with st.container(border=True):
            col1, col2 = st.columns([1, 3])
            with col1: st.link_button("🖼️ 영수증 보기", row["사진링크"])
            with col2:
                c1, c2, c3 = st.columns(3)
                u_date = c1.date_input("날짜", datetime.strptime(row["날짜"], '%Y-%m-%d'), key=f"d_{i}")
                u_name = c2.text_input("식당명", row["식당명"], key=f"s_{i}")
                u_price = c3.number_input("금액", value=int(row["금액"]), key=f"p_{i}")
                
                if st.button(f"확정 저장", key=f"save_{i}"):
                    data.at[i, "날짜"] = u_date.strftime('%Y-%m-%d')
                    data.at[i, "식당명"] = u_name
                    data.at[i, "금액"] = u_price
                    data.at[i, "상태"] = "완료"
                    conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=data)
                    st.toast(f"{u_name} 확정 완료!")
                    st.rerun()
else:
    st.info("수정할 임시 내역이 없습니다. 사진을 먼저 올려주세요.")

# 3. 최종 다운로드
st.divider()
if st.button("📥 최종 엑셀 파일 생성"):
    final_df = data[data["상태"] == "완료"]
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        final_df.to_excel(writer, index=False)
    st.download_button("엑셀 다운로드", data=output.getvalue(), file_name="영수증최종.xlsx")
