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
st.set_page_config(page_title="정민 영수증 매니저 V2", layout="wide")

# --- 고정 설정값 ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1x419Jb6laxcObm4z2nFU_W65Cx-4AxmAjwmE8ouFmjk/edit?usp=sharing"
DRIVE_FOLDER_ID = "1eja2vLLsUeDZhwgU7HVPadb2FhxyCFgr"

# --- 구글 서비스 연결 (드라이브 & 시트) ---
@st.cache_resource
def get_drive_service():
    try:
        creds_dict = st.secrets["connections"]["gsheets"]
        credentials = service_account.Credentials.from_service_account_info(creds_dict)
        return build('drive', 'v3', credentials=credentials)
    except Exception as e:
        st.error(f"구글 서비스 연결 실패: {e}")
        return None

drive_service = get_drive_service()
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 사진 처리 및 드라이브 업로드 함수 ---
def process_and_upload(image, filename):
    # 1. 자동 회전 방지 (세로 고정)
    image = ImageOps.exif_transpose(image)
    # 2. 저용량 압축 (최대 1000px)
    image.thumbnail((1000, 1000))
    img_byte_arr = io.BytesIO()
    # 3. JPEG 70% 화질로 용량 최적화
    image.convert("RGB").save(img_byte_arr, format='JPEG', quality=70)
    img_byte_arr.seek(0)
    
    # 4. 드라이브 업로드 설정 (공유 폴더 권한 포함)
    file_metadata = {'name': filename, 'parents': [DRIVE_FOLDER_ID]}
    media = MediaIoBaseUpload(img_byte_arr, mimetype='image/jpeg')
    
    try:
        file = drive_service.files().create(
            body=file_metadata, 
            media_body=media, 
            fields='id, webViewLink',
            supportsAllDrives=True  # 공유 폴더 용량 사용 설정
        ).execute()
        
        # 외부 링크 권한 부여
        drive_service.permissions().create(
            fileId=file.get('id'), 
            body={'type': 'anyone', 'role': 'viewer'}
        ).execute()
        return file.get('webViewLink')
    except Exception as e:
        st.error(f"드라이브 업로드 실패: {e}")
        return None

# --- 메인 화면 시작 ---
st.title("📑 한정민 선임님 영수증 관리 (모바일-PC)")
st.caption("모바일로 사진 찍고, PC에서 내용을 확정하세요!")

# 1단계: 사진 업로드 (주로 모바일에서 사용)
with st.expander("📸 1단계: 영수증 사진 업로드", expanded=True):
    files = st.file_uploader("사진을 선택하면 드라이브와 시트에 자동 기록됩니다.", accept_multiple_files=True)
    if files:
        for f in files:
            # 중복 업로드 방지 세션 체크
            if f"up_done_{f.name}" not in st.session_state:
                with st.spinner(f'{f.name} 처리 중...'):
                    img = Image.open(f)
                    # 드라이브 업로드 후 링크 받기
                    url = process_and_upload(img, f"한정민_{datetime.now().strftime('%m%d_%H%M')}_{f.name}")
                    
                    if url:
                        # 구글 시트에 '임시' 상태로 첫 기록 생성
                        new_row = pd.DataFrame([{
                            "성명": "한정민", 
                            "날짜": datetime.now().strftime('%Y-%m-%d'), 
                            "식당명": "미입력", 
                            "금액": 0, 
                            "비고": url, 
                            "상태": "임시"
                        }])
                        # 시트 데이터 읽기 및 합치기
                        try:
                            current_data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)
                            updated_data = pd.concat([current_data, new_row], ignore_index=True)
                            conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated_data)
                            st.session_state[f"up_done_{f.name}"] = True
                        except Exception as e:
                            st.error(f"시트 기록 실패: {e}")
        st.success("✅ 업로드 완료! 이제 아래에서 내용을 수정하고 '확정'하세요.")

# 2단계: 내용 수정 (주로 PC에서 사용)
st.divider()
st.subheader("📝 2단계: 내역 수정 및 최종 확정")

try:
    all_data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)
    # '임시' 상태인 데이터만 골라내기
    temp_targets = all_data[all_data["상태"] == "임시"].copy()
    
    if not temp_targets.empty:
        for i, row in temp_targets.iterrows():
            with st.container(border=True):
                col_img, col_form = st.columns([1, 4])
                with col_img:
                    st.link_button("🖼️ 영수증 보기", row["비고"])
                with col_form:
                    c1, c2, c3 = st.columns(3)
                    edit_date = c1.date_input("날짜 수정", datetime.now(), key=f"date_{i}")
                    edit_shop = c2.text_input("식당명 입력", row["식당명"], key=f"shop_{i}")
                    edit_price = c3.number_input("금액 입력", value=0, key=f"price_{i}")
                    
                    if st.button(f"확정 저장 (시트 반영)", key=f"btn_{i}"):
                        all_data.at[i, "날짜"] = edit_date.strftime('%Y-%m-%d')
                        all_data.at[i, "식당명"] = edit_shop
                        all_data.at[i, "금액"] = edit_price
                        all_data.at[i, "상태"] = "완료"
                        conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=all_data)
                        st.toast(f"{edit_shop} 확정 완료!")
                        st.rerun()
    else:
        st.info("수정할 임시 내역이 없습니다. 사진을 먼저 올려주세요.")
except Exception as e:
    st.error(f"데이터 로드 에러 (시트 '상태' 열 확인 필요): {e}")

# 3단계: 결과 확인 및 다운로드
st.divider()
final_view = all_data[all_data["상태"] == "완료"]
if not final_view.empty:
    with st.expander("✅ 완료된 내역 보기", expanded=False):
        st.dataframe(final_view[["날짜", "식당명", "금액", "비고"]], use_container_width=True)
    
    # 엑셀 다운로드 생성
    excel_out = io.BytesIO()
    with pd.ExcelWriter(excel_out, engine='openpyxl') as writer:
        final_view.to_excel(writer, index=False)
    
    st.download_button(
        label="📥 최종 확정 내역 엑셀 다운로드",
        data=excel_out.getvalue(),
        file_name=f"영수증정리_한정민_{datetime.now().strftime('%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
