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

# 사진 최적화 함수
def img_to_base64(image):
    image = ImageOps.exif_transpose(image)
    image.thumbnail((400, 400)) 
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG", quality=40)
    return base64.b64encode(buffered.getvalue()).decode()

# 시간대 자동 인식 함수
def get_meal_type():
    hour = datetime.now().hour
    if 5 <= hour < 10: return "조식"
    elif 10 <= hour < 16: return "중식"
    else: return "석식"

# PDF 생성 함수 (에러 수정 완료)
def create_pdf(df):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    for _, row in df.iterrows():
        pdf.add_page()
        pdf.set_font("Helvetica", 'B', 14)
        # 금액과 비고 형식 적용하여 PDF 기입
        display_price = f"{int(row['금액']):,}"
        pdf.cell(0, 10, f"Date: {row['날짜']} | Shop: {row['식당']} | Meal: {row['시간대']}", ln=True)
        pdf.cell(0, 10, f"Price: {display_price} | Note: {row['비고']}", ln=True)
        
        img_data = base64.b64decode(row["사진데이터"])
        img = Image.open(io.BytesIO(img_data))
        temp_img = io.BytesIO()
        img.save(temp_img, format="JPEG")
        pdf.image(temp_img, x=10, y=35, w=150)
    return pdf.output() # fpdf2의 표준 출력 방식

st.title("📑 영수증 관리 시스템 (한정민 선임님 전용)")

# 1단계: 모바일 업로드
with st.expander("📸 1단계: 영수증 사진 올리기", expanded=True):
    files = st.file_uploader("영수증 사진을 선택하세요", accept_multiple_files=True)
    if files:
        if st.button("🚀 사진 전송"):
            for f in files:
                with st.spinner(f'{f.name} 처리 중...'):
                    img_data = img_to_base64(Image.open(f))
                    new_row = pd.DataFrame([{
                        "날짜": datetime.now().strftime('%y-%m-%d'),
                        "식당": "미입력",
                        "시간대": get_meal_type(),
                        "금액": 0,
                        "비고": "$0.00",
                        "사진데이터": img_data,
                        "상태": "임시"
                    }])
                    data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)
                    updated = pd.concat([data, new_row], ignore_index=True)
                    conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated)
            st.success("✅ 업로드 완료! 이제 아래에서 내용을 수정하세요.")
            st.rerun()

# 2단계: PC 내역 수정
st.divider()
try:
    all_data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)
    temp_targets = all_data[all_data["상태"] == "임시"].copy()
    
    if not temp_targets.empty:
        st.subheader("📝 2단계: 내역 수정 및 최종 확정")
        for i, row in temp_targets.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([1, 2])
                with c1:
                    st.image(base64.b64decode(row["사진데이터"]), use_container_width=True)
                with c2:
                    m1, m2, m3 = st.columns(3)
                    new_d = m1.text_input("날짜 (YY-MM-DD)", row['날짜'], key=f"d_{i}")
                    new_s = m2.text_input("식당", key=f"s_{i}")
                    # 조식/중식/석식 선택박스
                    meal_options = ["조식", "중식", "석식"]
                    new_m = m3.selectbox("시간대", meal_options, index=meal_options.index(row['시간대']), key=f"m_{i}")
                    
                    m4, m5 = st.columns(2)
                    new_p = m4.number_input("금액", value=0, key=f"p_{i}")
                    new_n = m5.text_input("비고 (형식: $7.25)", "$0.00", key=f"n_{i}")
                    
                    if st.button("확정 저장", key=f"btn_{i}", type="primary"):
                        all_data.at[i, "날짜"] = new_d
                        all_data.at[i, "식당"] = new_s
                        all_data.at[i, "시간대"] = new_m
                        all_data.at[i, "금액"] = new_p
                        all_data.at[i, "비고"] = new_n
                        all_data.at[i, "상태"] = "완료"
                        conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=all_data)
                        st.rerun()
    else:
        st.info("수정할 임시 내역이 없습니다. 사진을 먼저 올려주세요.")
except Exception as e:
    st.error(f"데이터 로드 중 오류 발생: {e}")

# 3단계: 다운로드
if 'all_data' in locals():
    final_view = all_data[all_data["상태"] == "완료"]
    if not final_view.empty:
        st.divider()
        st.subheader("📥 3단계: 최종 결과물 다운로드")
        col1, col2 = st.columns(2)
        with col1:
            excel_data = final_view.drop(columns=['사진데이터']).copy()
            # 엑셀용 금액 콤마 형식 적용
            excel_data['금액'] = excel_data['금액'].apply(lambda x: f"{int(x):,}")
            excel_out = io.BytesIO()
            excel_data.to_excel(excel_out, index=False)
            st.download_button("📊 엑셀 다운로드", excel_out.getvalue(), f"영수증_내역_{datetime.now().strftime('%m%d')}.xlsx")
        with col2:
            if st.button("📄 PDF 생성 및 다운로드"):
                try:
                    pdf_bytes = create_pdf(final_view)
                    st.download_button("📎 PDF 저장", pdf_bytes, "00월 개인법인카드 영수증_한정민.pdf", "application/pdf")
                except Exception as e:
                    st.error(f"PDF 생성 오류: {e}")
