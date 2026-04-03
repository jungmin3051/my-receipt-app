import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import io
import base64
from PIL import Image, ImageOps
from fpdf import FPDF
from google.cloud import vision
from google.oauth2 import service_account

# 기본 설정
st.set_page_config(page_title="법카 영수증 관리 (AI)", layout="wide")
SHEET_URL = "https://docs.google.com/spreadsheets/d/1x419Jb6laxcObm4z2nFU_W65Cx-4AxmAjwmE8ouFmjk/edit?usp=sharing"

# [수정] 에러 방지를 위한 연결 로직 강화
try:
    # Secrets 구조를 직접 지정하여 연결 시도
    if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
        conn = st.connection("gsheets", type=GSheetsConnection, **st.secrets["connections"]["gsheets"])
    else:
        # 구조가 단순할 경우 대비
        conn = st.connection("gsheets", type=GSheetsConnection, **st.secrets["gsheets"])
except Exception as e:
    st.error(f"시트 연결 에러: {e}")
    st.info("Secrets 설정을 다시 확인해 주세요.")

# OCR 분석 함수
def analyze_receipt(image_bytes):
    try:
        # Secrets에서 AI 키 가져오기
        key_info = st.secrets["google_cloud_key"]
        creds = service_account.Credentials.from_service_account_info(key_info)
        client = vision.ImageAnnotatorClient(credentials=creds)
        
        image = vision.Image(content=image_bytes)
        response = client.text_detection(image=image)
        texts = response.text_annotations
        
        if not texts: return "인식 실패", "0"
        
        full_text = texts[0].description
        lines = full_text.split('\n')
        res_name = lines[0].strip() if lines else "알 수 없음"
        
        price = "0"
        for line in lines:
            if '원' in line or ',' in line:
                clean_p = ''.join(filter(str.isdigit, line))
                if clean_p and int(clean_p) > 100:
                    price = f"{int(clean_p):,}"
                    break
        return res_name, price
    except Exception as e:
        return f"분석 에러", "0"

# (이하 기존 이미지 처리 및 UI 로직 동일...)
# ... (생략된 부분은 이전 '통 코드'와 같습니다)
