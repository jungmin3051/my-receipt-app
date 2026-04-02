import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import io
from PIL import Image, ImageOps
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseUpload

# 0. 선임님 전용 단일 페이지 설정
st.set_page_config(page_title="정민 영수증 매니저", layout="wide")

# --- 고정값 ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1x419Jb6laxcObm4z2nFU_W65Cx-4AxmAjwmE8ouFmjk/edit?usp=sharing"
DRIVE_FOLDER_ID = "1eja2vLLsUeDZhwgU7HVPadb2FhxyCFgr"

@st.cache_resource
def get_drive_service():
    creds_dict = st.secrets["connections"]["gsheets"]
    credentials = service_account.Credentials.from_service_account_info(creds_dict)
    return build('drive', 'v3', credentials=credentials)

drive_service = get_drive_service()
conn = st.connection("gsheets", type=GSheetsConnection)

def process_and_upload(image, filename):
    image = ImageOps.exif_transpose(image)
    image.thumbnail((1000, 1000))
    img_byte_arr = io.BytesIO()
    image.convert("RGB").save(img_byte_arr, format='JPEG', quality=70)
    img_byte_arr.seek(0)
    
    file_metadata = {'name': filename, 'parents': [DRIVE_FOLDER_ID]}
    media = MediaIoBaseUpload(img_byte_arr, mimetype='image/jpeg', resumable=True)
    
    try:
        file = drive_service.files().create(
            body=file_metadata, media_body=media, 
            fields='id, webViewLink', supportsAllDrives=True 
        ).execute()
        drive_service.permissions().create(
            fileId=file.get('id'), body={'type': 'anyone', 'role': 'viewer'}, 
            supportsAllDrives=True
        ).execute()
        return file.get('webViewLink')
    except Exception as e:
        st.error(f"업로드 실패: {e}")
        return None

# --- 화면 구성 ---
st.title("📑 한정민 선임님 영수증 관리")

# 1. 업로드 (모바일용)
with st.expander("📸 1단계: 사진 업로드", expanded=True):
    files = st.file_uploader("영수증 사진 선택", accept_multiple_files=True)
    if files:
        for f in files:
            if f"up_{f.name}" not in st.session_state:
                with st.spinner(f'{f.name} 처리 중...'):
                    img = Image.open(f)
                    url = process_and_upload(img, f"한정민_{datetime.now().strftime('%m%d_%H%M')}_{f.name}")
                    if url:
                        new_row = pd.DataFrame([{
                            "성명": "한정민", "날짜": datetime.now().strftime('%Y-%m-%d'),
                            "식당명": "미입력", "금액": 0, "비고": url, "상태": "임시"
                        }])
                        data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)
                        updated = pd.concat([data, new_row], ignore_index=True)
                        conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated)
                        st.session_state[f"up_{f.name}"] = True
        st.success("✅ 업로드 완료!")

# 2. 수정 (PC용)
st.divider()
try:
    all_data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)
    temp_targets = all_data[all_data["상태"] == "임시"].copy()
    
    if not temp_targets.empty:
        st.subheader("📝 2단계: 내역 수정 및 확정")
        for i, row in temp_targets.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([1, 4])
                c1.link_button("🖼️ 보기", row["비고"])
                with c2:
                    ca, cb, cc = st.columns(3)
                    d = ca.date_input("날짜", datetime.now(), key=f"d_{i}")
                    s = cb.text_input("식당명", row["식당명"], key=f"s_{i}")
                    p = cc.number_input("금액", value=0, key=f"p_{i}")
                    if st.button("확정 저장", key=f"b_{i}"):
                        all_data.at[i, "날짜"], all_data.at[i, "식당명"], all_data.at[i, "금액"], all_data.at[i, "상태"] = d.strftime('%Y-%m-%d'), s, p, "완료"
                        conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=all_data)
                        st.rerun()
    else:
        st.info("수정할 내역이 없습니다.")
except Exception as e:
    st.error(f"데이터 로드 에러: {e}")

# 3. 다운로드
final_data = all_data[all_data["상태"] == "완료"]
if not final_data.empty:
    st.divider()
    out = io.BytesIO()
    final_data.to_excel(out, index=False)
    st.download_button("📥 최종 엑셀 다운로드", out.getvalue(), f"영수증_{datetime.now().strftime('%m%d')}.xlsx")
