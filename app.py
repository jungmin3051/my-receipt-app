import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import io
import base64
from PIL import Image, ImageOps
from fpdf import FPDF

# 0. 설정
st.set_page_config(page_title="영수증 정리기", layout="wide")
SHEET_URL = "https://docs.google.com/spreadsheets/d/1x419Jb6laxcObm4z2nFU_W65Cx-4AxmAjwmE8ouFmjk/edit?usp=sharing"
conn = st.connection("gsheets", type=GSheetsConnection)

def img_to_base64(image):
    image = ImageOps.exif_transpose(image)
    image.thumbnail((500, 500)) 
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG", quality=50)
    return base64.b64encode(buffered.getvalue()).decode()

def create_photo_pdf(df):
    pdf = FPDF()
    for i, (_, row) in enumerate(df.iterrows()):
        if i % 4 == 0: pdf.add_page()
        try:
            img_data = base64.b64decode(row["사진데이터"])
            temp_img = io.BytesIO(img_data)
            x = 10 if (i % 2 == 0) else 105
            y = 10 if (i % 4 < 2) else 148
            pdf.image(temp_img, x=x, y=y, w=90)
        except: continue
    return pdf.output()

st.title("📑 영수증 통합 관리 (한정민 선임)")

# --- 1. [폰] 업로드 ---
with st.expander("📸 1단계: 사진 업로드", expanded=True):
    files = st.file_uploader("사진 선택", accept_multiple_files=True)
    if files and st.button("🚀 사진 전송"):
        data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)
        new_list = []
        for f in files:
            img_b64 = img_to_base64(Image.open(f))
            new_list.append({"날짜": datetime.now().strftime('%Y-%m-%d'), "식당명": "", "금액": 0, "비고": "", "사진데이터": img_b64, "상태": "대기"})
        updated = pd.concat([data, pd.DataFrame(new_list)], ignore_index=True)
        conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated)
        st.success("업로드 완료!")
        st.rerun()

# --- 2. [PC] 수정 ---
st.divider()
all_data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)

if not all_data.empty:
    st.subheader("💻 2단계: 내역 수정")
    edit_idx = st.selectbox("항목 선택", all_data.index)
    row = all_data.loc[edit_idx]
    
    c_img, c_form = st.columns([1, 2])
    with c_img:
        st.image(base64.b64decode(row["사진데이터"]), width=300)
    with c_form:
        f1, f2 = st.columns(2)
        with f1:
            u_date = st.text_input("날짜", str(row["날짜"]))
            u_name = st.text_input("식당명", str(row["식당명"]))
        with f2:
            u_price = st.text_input("금액 (숫자만)", value=str(row["금액"])) # 텍스트로 받아 에러 방지
            u_note = st.text_input("비고", str(row["비고"]))
        
        if st.button("💾 저장"):
            # 에러 방지를 위해 .at 대신 리스트 방식으로 안전하게 업데이트
            all_data.loc[edit_idx, "날짜"] = str(u_date)
            all_data.loc[edit_idx, "식당명"] = str(u_name)
            all_data.loc[edit_idx, "금액"] = str(u_price)
            all_data.loc[edit_idx, "비고"] = str(u_note)
            all_data.loc[edit_idx, "상태"] = "완료"
            conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=all_data)
            st.success("저장되었습니다!")
            st.rerun()

    # --- 3. [PC] 다운로드 ---
    st.divider()
    done_df = all_data[all_data["상태"] == "완료"]
    d1, d2 = st.columns(2)
    with d1:
        # 내역 엑셀 다운로드
        excel_out = io.BytesIO()
        done_df.drop(columns=["사진데이터", "상태"]).to_excel(excel_out, index=False)
        st.download_button("📊 엑셀 내역서 다운로드", excel_out.getvalue(), "Receipt_List.xlsx")
    with d2:
        # 사진 PDF 다운로드
        if st.button("📄 PDF 사진증빙 생성"):
            pdf_bytes = create_photo_pdf(done_df)
            st.download_button("📥 PDF 다운로드", pdf_bytes, "Receipt_Photos.pdf")
