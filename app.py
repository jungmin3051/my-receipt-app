import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import io
import base64
from PIL import Image, ImageOps
from fpdf import FPDF # PDF 생성을 위해 필요 (requirements.txt에 fpdf2 추가 필요)

# 0. 기본 설정
st.set_page_config(page_title="정민 영수증 매니저", layout="wide")

# 구글 시트 주소
SHEET_URL = "https://docs.google.com/spreadsheets/d/1x419Jb6laxcObm4z2nFU_W65Cx-4AxmAjwmE8ouFmjk/edit?usp=sharing"
conn = st.connection("gsheets", type=GSheetsConnection)

# 이미지 변환 함수
def img_to_base64(image):
    image = ImageOps.exif_transpose(image)
    image.thumbnail((800, 800))
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG", quality=70)
    return base64.b64encode(buffered.getvalue()).decode()

# PDF 생성 함수
def create_pdf(df):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    for _, row in df.iterrows():
        pdf.add_page()
        pdf.set_font("Arial", 'B', 16)
        pdf.cell(40, 10, f"Date: {row['날짜']} / Shop: {row['식당명']}")
        pdf.ln(10)
        
        # 사진 추가
        img_data = base64.b64decode(row["비고"])
        img_path = io.BytesIO(img_data)
        img = Image.open(img_path)
        
        # 임시 파일로 저장 후 PDF에 삽입
        temp_path = "temp_receipt.jpg"
        img.save(temp_path)
        pdf.image(temp_path, x=10, y=30, w=180)
        
    return pdf.output(dest='S').encode('latin-1')

st.title("📑 한정민 선임님 영수증 관리 시스템")

# --- 1단계: 모바일 사진 업로드 ---
with st.expander("📸 1단계: 모바일 사진 업로드", expanded=True):
    files = st.file_uploader("영수증 사진 선택 (여러 장 가능)", accept_multiple_files=True)
    if files:
        if st.button("🚀 사진 전송 시작"):
            for f in files:
                with st.spinner(f'{f.name} 처리 중...'):
                    img = Image.open(f)
                    img_data = img_to_base64(img)
                    new_row = pd.DataFrame([{
                        "성명": "한정민", "날짜": datetime.now().strftime('%Y-%m-%d'),
                        "식당명": "미입력", "금액": 0, "비고": img_data, "상태": "임시"
                    }])
                    data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)
                    updated = pd.concat([data, new_row], ignore_index=True)
                    conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated)
            st.success("✅ 서버 전송 완료! PC에서 확인하세요.")

# --- 2단계: PC 내역 수정 ---
st.divider()
try:
    all_data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)
    temp_targets = all_data[all_data["상태"] == "임시"].copy()
    
    if not temp_targets.empty:
        st.subheader("📝 2단계: 상세 항목 수정 (PC 추천)")
        for i, row in temp_targets.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([1, 2])
                with c1:
                    st.image(base64.b64decode(row["비고"]), use_container_width=True)
                with c2:
                    ca, cb, cc = st.columns(3)
                    new_d = ca.date_input("날짜", datetime.now(), key=f"d_{i}")
                    new_s = cb.text_input("식당명", "", key=f"s_{i}", placeholder="식당 이름")
                    new_p = cc.number_input("금액", value=0, key=f"p_{i}")
                    if st.button("확정 저장", key=f"btn_{i}", type="primary"):
                        all_data.at[i, "날짜"] = new_d.strftime('%Y-%m-%d')
                        all_data.at[i, "식당명"] = new_s
                        all_data.at[i, "금액"] = new_p
                        all_data.at[i, "상태"] = "완료"
                        conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=all_data)
                        st.rerun()
    else:
        st.info("수정할 새로운 영수증이 없습니다.")
except Exception:
    st.info("데이터를 불러오는 중입니다...")

# --- 3단계: 엑셀 및 PDF 다운로드 ---
final_data = all_data[all_data["상태"] == "완료"]
if not final_data.empty:
    st.divider()
    st.subheader("📥 3단계: 최종 결과물 다운로드")
    col1, col2 = st.columns(2)
    
    with col1:
        # 엑셀 다운로드 (사진 데이터는 제외)
        excel_out = io.BytesIO()
        final_data.drop(columns=['비고']).to_excel(excel_out, index=False)
        st.download_button("📊 엑셀 파일 다운로드", excel_out.getvalue(), f"영수증_내역_{datetime.now().strftime('%m%d')}.xlsx")
        
    with col2:
        # PDF 다운로드
        if st.button("PDF 생성하기"):
            pdf_bytes = create_pdf(final_data)
            st.download_button(
                "📄 PDF 파일 다운로드", 
                pdf_bytes, 
                "00월 개인법인카드 영수증_한정민.pdf",
                mime="application/pdf"
            )
