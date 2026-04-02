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

# 0. 설정 (한정민 선임님 고정 정보)
st.set_page_config(page_title="정민 영수증 매니저", layout="wide")
SHEET_URL = "https://docs.google.com/spreadsheets/d/1x419Jb6laxcObm4z2nFU_W65Cx-4AxmAjwmE8ouFmjk/edit?usp=sharing"
DRIVE_FOLDER_ID = "1eja2vLLsUeDZhwgU7HVPadb2FhxyCFgr"

# --- 서비스 연결 (캐시 적용) ---
@st.cache_resource
def get_drive_service():
    try:
        creds_dict = st.secrets["connections"]["gsheets"]
        credentials = service_account.Credentials.from_service_account_info(creds_dict)
        return build('drive', 'v3', credentials=credentials)
    except Exception as e:
        st.error(f"서비스 연결 실패: {e}")
        return None

drive_service = get_drive_service()
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 사진 처리 함수 (세로 고정 + 압축) ---
def process_and_upload(image, filename):
    image = ImageOps.exif_transpose(image) # 세로 고정
    image.thumbnail((1000, 1000)) # 저용량 압축
    img_byte_arr = io.BytesIO()
    image.convert("RGB").save(img_byte_arr, format='JPEG', quality=70)
    img_byte_arr.seek(0)
    
    file_metadata = {'name': filename, 'parents': [DRIVE_FOLDER_ID]}
    media = MediaIoBaseUpload(img_byte_arr, mimetype='image/jpeg')
    
    # 에러 방지를 위한 실행부
    try:
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
        # 외부에서도 볼 수 있게 권한 부여
        drive_service.permissions().create(fileId=file.get('id'), body={'type': 'anyone', 'role': 'viewer'}).execute()
        return file.get('webViewLink')
    except Exception as e:
        st.error(f"드라이브 업로드 중 오류 발생: {e}")
        return None

st.title("📑 한정민 선임님 영수증 관리 (모바일-PC 동기화)")

# 1. 사진 업로드 (모바일에서 업로드용)
with st.expander("📸 1단계: 사진 찍어 올리기", expanded=True):
    files = st.file_uploader("영수증 사진을 선택하세요", accept_multiple_files=True)
    if files:
        for f in files:
            if f"ok_{f.name}" not in st.session_state:
                with st.spinner(f'{f.name} 처리 중...'):
                    img = Image.open(f)
                    url = process_and_upload(img, f"한정민_{datetime.now().strftime('%m%d_%H%M')}_{f.name}")
                    
                    if url:
                        # 즉시 시트에 '미입력' 상태로 기록
                        temp_df = pd.DataFrame([{"성명": "한정민", "날짜": datetime.now().strftime('%Y-%m-%d'), 
                                               "식당명": "미입력", "금액": 0, "비고": url, "상태": "임시"}])
                        current = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)
                        updated = pd.concat([current, temp_df], ignore_index=True)
                        conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated)
                        st.session_state[f"ok_{f.name}"] = True
        st.success("✅ 드라이브에 저장 완료! 이제 아래에서 내용을 수정하세요.")

# 2. 내역 수정 (PC에서 상세 입력용)
st.divider()
st.subheader("📝 2단계: 내역 수정 및 최종 확정")
data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)
edit_targets = data[data["상태"] == "임시"].copy()

if not edit_targets.empty:
    for i, row in edit_targets.iterrows():
        with st.container(border=True):
            c1, c2 = st.columns([1, 4])
            with c1: st.link_button("🖼️ 영수증 보기", row["비고"])
            with c2:
                col_a, col_b, col_c = st.columns(3)
                new_date = col_a.date_input("날짜", datetime.now(), key=f"d_{i}")
                new_shop = col_b.text_input("식당명", row["식당명"], key=f"s_{i}")
                new_price = col_c.number_input("금액", value=0, key=f"p_{i}")
                
                if st.button(f"확정 저장하기", key=f"btn_{i}"):
                    data.at[i, "날짜"] = new_date.strftime('%Y-%m-%d')
                    data.at[i, "식당명"] = new_shop
                    data.at[i, "금액"] = new_price
                    data.at[i, "상태"] = "완료"
                    conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=data)
                    st.toast("저장되었습니다!")
                    st.rerun()
else:
    st.info("수정할 임시 내역이 없습니다.")

# 3. 완료 내역 확인 및 엑셀
st.divider()
final_data = data[data["상태"] == "완료"]
if not final_data.empty:
    st.write("✅ 완료된 내역")
    st.table(final_data[["날짜", "식당명", "금액"]])
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        final_data.to_excel(writer, index=False)
    st.download_button("📥 최종 엑셀 다운로드", data=output.getvalue(), file_name="영수증정리_최종.xlsx")
