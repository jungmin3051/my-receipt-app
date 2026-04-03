import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import io
import base64
import json
from PIL import Image, ImageOps
from fpdf import FPDF
from google.cloud import vision
from google.oauth2 import service_account

# 0. 기본 설정
st.set_page_config(page_title="법카 영수증 관리 (AI)", layout="wide")
SHEET_URL = "https://docs.google.com/spreadsheets/d/1x419Jb6laxcObm4z2nFU_W65Cx-4AxmAjwmE8ouFmjk/edit?usp=sharing"

# [수정] 권한 오류 해결을 위해 secrets 정보를 직접 주입합니다.
conn = st.connection("gsheets", type=GSheetsConnection, **st.secrets["connections"]["gsheets"])

# [OCR] Google Vision API 설정
def analyze_receipt(image_bytes):
    try:
        # Secrets에서 AI용 열쇠 꺼내기
        key_dict = st.secrets["google_cloud_key"]
        creds = service_account.Credentials.from_service_account_info(key_dict)
        client = vision.ImageAnnotatorClient(credentials=creds)
        
        image = vision.Image(content=image_bytes)
        response = client.text_detection(image=image)
        texts = response.text_annotations
        
        if not texts: return "인식 실패", "0"
        
        full_text = texts[0].description
        lines = full_text.split('\n')
        
        # 1. 식당명: 첫 번째 줄 추출 (다이소, 오렌지푸드 등)
        res_name = lines[0].strip() if lines else "알 수 없음"
        
        # 2. 금액 추출 로직
        price = "0"
        for line in lines:
            if '원' in line or ',' in line:
                clean_p = ''.join(filter(str.isdigit, line))
                if clean_p and int(clean_p) > 100:
                    price = f"{int(clean_p):,}"
                    break
        return res_name, price
    except Exception as e:
        return f"에러: {str(e)[:20]}", "0"

def get_meal_priority(meal_name):
    priority = {"조식": 1, "중식": 2, "석식": 3}
    return priority.get(meal_name, 2)

def img_to_base64(image):
    image = ImageOps.exif_transpose(image)
    if image.mode != 'RGB': image = image.convert('RGB')
    image.thumbnail((800, 800)) 
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG", quality=50) 
    return base64.b64encode(buffered.getvalue()).decode(), buffered.getvalue()

# PDF 생성 함수 (누락 방지)
def create_photo_pdf(df):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    for _, row in df.iterrows():
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(0, 10, f"{row['날짜']} - {row['식당명']} ({row['금액']} won)", ln=True)
        if row["사진데이터"]:
            img_data = base64.b64decode(row["사진데이터"])
            img_path = io.BytesIO(img_data)
            pdf.image(img_path, x=10, y=30, w=180)
    return pdf.output(dest='S')

# 1. 데이터 불러오기
try:
    raw_data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl="1s").astype(str)
    all_data = raw_data[raw_data["사진데이터"] != "nan"].fillna("")
except:
    all_data = pd.DataFrame(columns=["날짜", "식당명", "시간대", "금액", "비고", "사진데이터", "상태"])

st.title("📑 법카 영수증 관리 (AI 모드)")

# --- 1단계: 사진 업로드 및 AI 자동 인식 ---
with st.expander("📸 1단계: 사진 업로드", expanded=True):
    files = st.file_uploader("영수증 사진 선택", accept_multiple_files=True)
    if files and st.button("🚀 사진 전송 및 AI 분석"):
        new_list = []
        now = datetime.now()
        auto_meal = "조식" if now.hour < 10 else "중식" if now.hour < 16 else "석식"
        
        with st.spinner("AI가 영수증 글자를 읽고 있습니다..."):
            for f in files:
                img_b64, img_bytes = img_to_base64(Image.open(f))
                ai_res, ai_price = analyze_receipt(img_bytes)
                
                new_list.append({
                    "날짜": now.strftime('%y-%m-%d'), 
                    "식당명": ai_res, 
                    "시간대": auto_meal, 
                    "금액": ai_price, 
                    "비고": "AI 자동인식", 
                    "사진데이터": img_b64, "상태": "대기"
                })
        
        if new_list:
            updated = pd.concat([all_data, pd.DataFrame(new_list)], ignore_index=True)
            conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated)
            st.cache_data.clear()
            st.rerun()

# --- 2단계: 내용 수정 및 삭제 ---
if not all_data.empty:
    st.divider()
    st.subheader("💻 2단계: 내용 수정 및 삭제")
    all_data['priority'] = all_data['시간대'].apply(get_meal_priority)
    sorted_data = all_data.sort_values(by=["날짜", "priority"], ascending=[True, True])
    row_list = sorted_data.to_dict('records')
    
    idx = st.selectbox("항목 선택", range(len(row_list)), 
                       format_func=lambda x: f"[{x}] {row_list[x]['날짜']} {row_list[x]['식당명']} ({row_list[x]['시간대']})")
    row = row_list[idx]
    
    c1, c2 = st.columns([1, 2])
    with c1: 
        if row["사진데이터"]: st.image(base64.b64decode(row["사진데이터"]), width=300)
    with c2:
        f1, f2 = st.columns(2)
        with f1:
            try: d_val = datetime.strptime(row["날짜"], '%y-%m-%d')
            except: d_val = datetime.now()
            u_date = st.date_input("날짜", d_val)
            u_name = st.text_input("식당명", row["식당명"])
        with f2:
            meal_opts = ["조식", "중식", "석식"]
            curr_m = row["시간대"] if row["시간대"] in meal_opts else "중식"
            u_meal = st.selectbox("시간대", meal_opts, index=meal_opts.index(curr_m))
            p_val = str(row["금액"]).replace(',', '').split('.')[0]
            d_price = f"{int(p_val):,}" if p_val.isdigit() else p_val
            u_price = st.text_input("금액", value=d_price)
        u_note = st.text_input("비고", row["비고"])
        
        b_c1, b_c2 = st.columns(2)
        with b_c1:
            if st.button("💾 저장 및 수정", use_container_width=True):
                clean_p = u_price.replace(',', '')
                final_p = f"{int(clean_p):,}" if clean_p.isdigit() else u_price
                row_list[idx].update({"날짜": u_date.strftime('%y-%m-%d'), "식당명": u_name, "시간대": u_meal, "금액": final_p, "비고": u_note, "상태": "완료"})
                new_df = pd.DataFrame(row_list).drop(columns=['priority'], errors='ignore')
                conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=new_df)
                st.cache_data.clear()
                st.rerun()
        with b_c2:
            if st.button("🗑️ 삭제", use_container_width=True):
                row_list.pop(idx)
                new_df = pd.DataFrame(row_list).drop(columns=['priority'], errors='ignore') if row_list else pd.DataFrame(columns=["날짜", "식당명", "시간대", "금액", "비고", "사진데이터", "상태"])
                conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=new_df)
                st.cache_data.clear()
                st.rerun()

# --- 3단계: 확인 및 다운로드 ---
if not all_data.empty:
    st.divider()
    st.subheader("👀 현재 저장된 내역")
    disp_df = all_data.drop(columns=["사진데이터", "priority"], errors='ignore').copy()
    st.dataframe(disp_df, use_container_width=True)

    done_df = all_data[all_data["상태"] == "완료"]
    if not done_df.empty:
        st.subheader("📥 3단계: 다운로드")
        d1, d2 = st.columns(2)
        with d1:
            ex_out = io.BytesIO()
            done_df.drop(columns=["사진데이터", "상태", "priority"], errors='ignore').to_excel(ex_out, index=False)
            st.download_button("📊 엑셀 다운로드", ex_out.getvalue(), "Receipt_List.xlsx")
        with d2:
            pdf_fn = f"{datetime.now().month}월 영수증보고서_한정민.pdf"
            st.download_button("📄 영수증 PDF 다운로드", create_photo_pdf(done_df), pdf_fn, "application/pdf")
