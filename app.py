import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import io
import base64
from PIL import Image
from fpdf import FPDF

# 0. 설정 및 구글 시트 연결
st.set_page_config(page_title="영수증 사진 증빙", layout="wide")
SHEET_URL = "https://docs.google.com/spreadsheets/d/1x419Jb6laxcObm4z2nFU_W65Cx-4AxmAjwmE8ouFmjk/edit?usp=sharing"
conn = st.connection("gsheets", type=GSheetsConnection)

# --- 핵심: 사진만 4장씩 배치하는 PDF 함수 ---
def create_photo_only_pdf(df):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=10)
    
    # 사진이 있는 행만 추출
    photo_rows = df[df["사진데이터"].notformat()].reset_index()
    
    for i, (_, row) in enumerate(photo_rows.iterrows()):
        # 4장마다 새 페이지 시작
        if i % 4 == 0:
            pdf.add_page()
        
        # 사진 데이터 복원
        img_data = base64.b64decode(row["사진데이터"])
        img = Image.open(io.BytesIO(img_data))
        
        # 임시 이미지 저장 (PDF 삽입용)
        temp_img = io.BytesIO()
        img.save(temp_img, format="JPEG")
        
        # 한 페이지에 4장 배치 (세로 2열 2행)
        # x, y 좌표 및 너비(w) 설정
        x = 10 if (i % 2 == 0) else 105
        y = 10 if (i % 4 < 2) else 145
        
        pdf.image(temp_img, x=x, y=y, w=90) # 너비 90mm로 세로형 배치
        
    return pdf.output()

st.title("📸 영수증 사진 증빙 생성기")

# 1. 시트 데이터 불러오기
all_data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)

if not all_data.empty:
    # 2. 현재 저장된 사진들 표로 보여주기 (확인용)
    st.subheader("📊 현재 저장된 영수증 목록")
    display_df = all_data.drop(columns=['사진데이터']).copy()
    st.dataframe(display_df, use_container_width=True)
    
    # 3. PDF 생성 및 다운로드 버튼
    st.divider()
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📄 사진만 모아서 PDF 만들기", type="primary"):
            # '완료' 상태인 것만 뽑거나 전체 다 뽑거나 선택 가능
            pdf_bytes = create_photo_only_pdf(all_data)
            st.session_state.pdf_ready = pdf_bytes
            st.success("PDF 생성 완료! 아래 버튼을 눌러 저장하세요.")

    with col2:
        if 'pdf_ready' in st.session_state:
            st.download_button(
                label="📥 PDF 파일 컴퓨터에 저장",
                data=st.session_state.pdf_ready,
                file_name=f"영수증증빙_한정민_{pd.Timestamp.now().strftime('%m%d')}.pdf",
                mime="application/pdf"
            )
else:
    st.info("시트에 데이터가 없습니다. 먼저 사진을 업로드해 주세요.")
