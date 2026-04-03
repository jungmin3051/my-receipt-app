import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import io
import base64
from PIL import Image, ImageOps
from fpdf import FPDF

# 0. 설정
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
    if 5 <= hour < 10: return "조식"
    elif 10 <= hour < 16: return "중식"
    else: return "석식"

# PDF 생성 함수 (한글 깨짐 방지 및 에러 수정)
def create_pdf(df):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    for _, row in df.iterrows():
        pdf.add_page()
        # 한글은 PDF 표준 폰트에서 지원되지 않으므로 영어 위주 레이아웃 구성
        pdf.set_font("Helvetica", 'B', 16)
        pdf.cell(0, 10, f"Receipt Report", ln=True, align='C')
        pdf.ln(10)
        pdf.set_font("Helvetica", '', 12)
        pdf.cell(0, 10, f"Date: {row['날짜']}  |  Shop: {row['식당']}", ln=True)
        pdf.cell(0, 10, f"Meal: {row['시간대']}  |  Price: {int(row['금액']):,}", ln=True)
        pdf.cell(0, 10, f"Note: {row['비고']}", ln=True)
        
        # 사진 삽입
        img_data = base64.b64decode(row["사진데이터"])
        img = Image.open(io.BytesIO(img_data))
        temp_img = io.BytesIO()
        img.save(temp_img, format="JPEG")
        pdf.image(temp_img, x=10, y=50, w=160)
    return pdf.output()

st.title("📑 한정민 선임님 영수증 관리 시스템")

# 1단계: 모바일 업로드
with st.expander("📸 1단계: 영수증 사진 올리기 (모바일)", expanded=True):
    files = st.file_uploader("영수증 사진 선택", accept_multiple_files=True)
    if files:
        if st.button("🚀 사진 전송"):
            for f in files:
                img_data = img_to_base64(Image.open(f))
                new_row = pd.DataFrame([{
                    "날짜": datetime.now().strftime('%y-%m-%d'),
                    "식당": "미입력", "시간대": get_meal_type(),
                    "금액": 0, "비고": "$0.00", "사진데이터": img_data, "상태": "임시"
                }])
                data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)
                updated = pd.concat([data, new_row], ignore_index=True)
                conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated)
            st.success("✅ 업로드 성공!")
            st.rerun()

# 2단계: 자유로운 수정 및 내역 확인
st.divider()
all_data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)

if not all_data.empty:
    st.subheader("📝 2단계: 내역 수정 및 관리")
    
    # 수정할 항목 선택 (모든 데이터 대상)
    options = [f"[{i}] {row['날짜']} - {row['식당']}" for i, row in all_data.iterrows()]
    selected_idx = st.selectbox("수정하거나 다시 확인할 영수증을 선택하세요", range(len(options)), format_func=lambda x: options[x])
    
    with st.container(border=True):
        row = all_data.iloc[selected_idx]
        c1, c2 = st.columns([1, 2])
        with c1:
            st.image(base64.b64decode(row["사진데이터"]), use_container_width=True)
        with c2:
            m1, m2, m3 = st.columns(3)
            new_d = m1.text_input("날짜", row['날짜'], key="edit_d")
            new_s = m2.text_input("식당", row['식당'], key="edit_s")
            meal_opts = ["조식", "중식", "석식"]
            new_m = m3.selectbox("시간대", meal_opts, index=meal_opts.index(row['시간대']) if row['시간대'] in meal_opts else 1, key="edit_m")
            
            m4, m5 = st.columns(2)
            new_p = m4.number_input("금액", value=int(row['금액']), key="edit_p")
            new_n = m5.text_input("비고 ($ 형식)", row['비고'], key="edit_n")
            
            if st.button("💾 이 영수증 정보 업데이트", type="primary"):
                all_data.at[selected_idx, "날짜"] = new_d
                all_data.at[selected_idx, "식당"] = new_s
                all_data.at[selected_idx, "시간대"] = new_m
                all_data.at[selected_idx, "금액"] = new_p
                all_data.at[selected_idx, "비고"] = new_n
                all_data.at[selected_idx, "상태"] = "완료"
                conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=all_data)
                st.success("저장되었습니다!")
                st.rerun()

    # 3단계: 시트 표 보기 및 다운로드
    st.divider()
    st.subheader("📊 3단계: 전체 내역 확인 및 파일 저장")
    
    # 현재 시트의 데이터 표 보여주기 (사진데이터 제외)
    display_df = all_data.drop(columns=['사진데이터']).copy()
    display_df['금액'] = display_df['금액'].apply(lambda x: f"{int(x):,}")
    st.table(display_df)
    
    col1, col2 = st.columns(2)
    with col1:
        excel_out = io.BytesIO()
        display_df.to_excel(excel_out, index=False)
        st.download_button("📊 엑셀 다운로드", excel_out.getvalue(), f"영수증_내역_{datetime.now().strftime('%m%d')}.xlsx")
    with col2:
        if st.button("📄 PDF 생성 및 다운로드"):
            pdf_bytes = create_pdf(all_data[all_data["상태"] == "완료"])
            st.download_button("📎 PDF 저장", pdf_bytes, "00월 개인법인카드 영수증_한정민.pdf", "application/pdf")
