import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import io
import base64
from PIL import Image, ImageOps
from fpdf import FPDF

# 0. 기본 설정
st.set_page_config(page_title="정민 영수증 매니저", layout="wide")

SHEET_URL = "https://docs.google.com/spreadsheets/d/1x419Jb6laxcObm4z2nFU_W65Cx-4AxmAjwmE8ouFmjk/edit?usp=sharing"
conn = st.connection("gsheets", type=GSheetsConnection)

def img_to_base64(image):
    image = ImageOps.exif_transpose(image)
    image.thumbnail((400, 400)) 
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG", quality=40)
    return base64.b64encode(buffered.getvalue()).decode()

def get_meal_type():
    hour = datetime.now().hour
    if 5 <= hour < 10: return "Morning" # 한글 대신 영어로 설정하여 에러 방지
    elif 10 <= hour < 16: return "Lunch"
    else: return "Dinner"

# --- 핵심: 에러 없는 PDF 생성 함수 ---
def create_pdf(df):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # 한글 시간대를 영어로 매핑 (에러 방지용)
    meal_map = {"조식": "Morning", "중식": "Lunch", "석식": "Dinner"}

    for _, row in df.iterrows():
        pdf.add_page()
        pdf.set_font("Helvetica", 'B', 16)
        pdf.cell(0, 10, "Receipt Report (Han Jeong-min)", ln=True, align='C')
        pdf.ln(10)
        
        pdf.set_font("Helvetica", '', 12)
        # 한글이 포함될 수 있는 식당명은 빼고, 날짜와 금액 위주로 구성 (에러 원천 봉쇄)
        pdf.cell(0, 10, f"Date: {row['날짜']}", ln=True)
        
        meal_eng = meal_map.get(row['시간대'], row['시간대'])
        display_price = f"{int(row['금액']):,}"
        pdf.cell(0, 10, f"Meal: {meal_eng}  |  Price: KRW {display_price}", ln=True)
        pdf.cell(0, 10, f"Note: {row['비고']}", ln=True)
        
        # 영수증 원본 사진 삽입 (이게 가장 중요하니까요!)
        img_data = base64.b64decode(row["사진데이터"])
        img = Image.open(io.BytesIO(img_data))
        temp_img = io.BytesIO()
        img.save(temp_img, format="JPEG")
        pdf.image(temp_img, x=10, y=60, w=160)
        
    return pdf.output()

st.title("📑 한정민 선임님 영수증 관리 (PDF 에러 해결 버전)")

# 1단계: 업로드
with st.expander("📸 1단계: 사진 업로드", expanded=True):
    files = st.file_uploader("사진을 선택하세요", accept_multiple_files=True)
    if files and st.button("🚀 사진 전송"):
        for f in files:
            img_data = img_to_base64(Image.open(f))
            new_row = pd.DataFrame([{
                "날짜": datetime.now().strftime('%y-%m-%d'),
                "식당": "Restaurant", "시간대": "Lunch", 
                "금액": 0, "비고": "$0.00", "사진데이터": img_data, "상태": "임시"
            }])
            data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)
            updated = pd.concat([data, new_row], ignore_index=True)
            conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated)
        st.success("업로드 완료!")
        st.rerun()

# 2단계: 수정 및 시트 뷰
st.divider()
all_data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)

if not all_data.empty:
    st.subheader("📊 2단계: 내역 확인 및 PDF 저장")
    
    # 표로 먼저 보여주기
    display_df = all_data.drop(columns=['사진데이터']).copy()
    st.table(display_df)
    
    col1, col2 = st.columns(2)
    with col1:
        # 수정 기능
        target_idx = st.selectbox("수정할 내역 선택", range(len(all_data)))
        if st.button("✅ 선택 내역 '완료' 처리"):
            all_data.at[target_idx, "상태"] = "완료"
            conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=all_data)
            st.rerun()
            
    with col2:
        # PDF 다운로드 (완료된 내역만)
        ready_df = all_data[all_data["상태"] == "완료"]
        if not ready_df.empty:
            if st.button("📄 PDF 파일 생성"):
                pdf_bytes = create_pdf(ready_df)
                st.download_button("📥 PDF 다운로드 하기", pdf_bytes, "Receipt_Report_Jeongmin.pdf", "application/pdf")
        else:
            st.info("수정 후 '완료' 처리된 내역이 있어야 PDF를 만들 수 있습니다.")
