import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import io
import base64
from PIL import Image, ImageOps
from fpdf import FPDF

# 0. 설정 및 구글 시트 연결
st.set_page_config(page_title="영수증 관리", layout="wide")
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
    # 글자 없이 '사진만' 4장씩 배치 (에러 0%)
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

st.title("📑 법카 영수증 관리 (한정민 선임 전용)")

# --- 1단계: [폰에서 접속] 사진 업로드 ---
with st.expander("📸 1단계: 폰으로 영수증 사진 올리기", expanded=True):
    files = st.file_uploader("사진 선택", accept_multiple_files=True)
    if files and st.button("🚀 사진 전송 시작"):
        data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)
        new_list = []
        for f in files:
            img_b64 = img_to_base64(Image.open(f))
            new_list.append({"날짜": datetime.now().strftime('%Y-%m-%d'), "식당명": "입력전", "금액": 0, "비고": "", "사진데이터": img_b64, "상태": "대기"})
        updated = pd.concat([data, pd.DataFrame(new_list)], ignore_index=True)
        conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated)
        st.success("사진 전송 완료! 이제 PC에서 수정하세요.")

# --- 2단계: [PC에서 접속] 내역 수정 ---
st.divider()
all_data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)

if not all_data.empty:
    st.subheader("💻 2단계: PC에서 내역 수정하기")
    edit_idx = st.selectbox("수정할 항목", all_data.index, format_func=lambda x: f"[{x}] {all_data.at[x, '날짜']}")
    row = all_data.loc[edit_idx]
    
    col_img, col_form = st.columns([1, 2])
    with col_img:
        st.image(base64.b64decode(row["사진데이터"]), width=300)
    with col_form:
        c1, c2 = st.columns(2)
        with c1:
            u_date = st.text_input("날짜", str(row["날짜"]))
            u_name = st.text_input("식당명", str(row["식당명"]))
        with c2:
            u_price = st.number_input("금액", value=int(row["금액"]))
            u_note = st.text_input("비고", str(row["비고"]))
        
        if st.button("💾 정보 저장 및 완료 처리"):
            all_data.at[edit_idx, "날짜"], all_data.at[edit_idx, "식당명"] = u_date, u_name
            all_data.at[edit_idx, "금액"], all_data.at[edit_idx, "비고"] = u_price, u_note
            all_data.at[edit_idx, "상태"] = "완료"
            conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=all_data)
            st.success("저장 성공!")
            st.rerun()

    # --- 3단계: 다운로드 (엑셀 따로, PDF 따로) ---
    st.divider()
    st.subheader("📥 3단계: 최종 결과물 다운로드")
    done_df = all_data[all_data["상태"] == "완료"]
    
    ex_col, pdf_col = st.columns(2)
    with ex_col:
        excel_out = io.BytesIO()
        done_df.drop(columns=["사진데이터", "상태"]).to_excel(excel_out, index=False)
        st.download_button("📊 엑셀(내역서) 다운로드", excel_out.getvalue(), "Receipt_List.xlsx")
    with pdf_col:
        if st.button("📄 PDF(사진증빙) 생성"):
            pdf_bytes = create_photo_pdf(done_df)
            st.download_button("📥 PDF(사진증빙) 다운로드", pdf_bytes, "Receipt_Photos.pdf")

    if st.button("🗑️ 선택 항목 삭제"):
        all_data = all_data.drop(edit_idx).reset_index(drop=True)
        conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=all_data)
        st.rerun()
