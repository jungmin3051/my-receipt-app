import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import io
import base64
from PIL import Image, ImageOps
from fpdf import FPDF

# 0. 설정 및 구글 시트 연결
st.set_page_config(page_title="영수증 정리 도우미", layout="wide")
SHEET_URL = "https://docs.google.com/spreadsheets/d/1x419Jb6laxcObm4z2nFU_W65Cx-4AxmAjwmE8ouFmjk/edit?usp=sharing"
conn = st.connection("gsheets", type=GSheetsConnection)

def img_to_base64(image):
    image = ImageOps.exif_transpose(image)
    image.thumbnail((500, 500)) 
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG", quality=50)
    return base64.b64encode(buffered.getvalue()).decode()

# --- 사진만 4장씩 PDF로 만드는 함수 (글자 에러 방지) ---
def create_photo_pdf(df):
    pdf = FPDF()
    for i, (_, row) in enumerate(df.iterrows()):
        if i % 4 == 0: pdf.add_page()
        try:
            img_data = base64.b64decode(row["사진데이터"])
            temp_img = io.BytesIO(img_data)
            # 한 페이지 4분할 좌표
            x = 10 if (i % 2 == 0) else 105
            y = 10 if (i % 4 < 2) else 148
            pdf.image(temp_img, x=x, y=y, w=90)
        except: continue
    return pdf.output()

st.title("📑 법카 영수증 관리 (한정민 선임)")

# --- 1단계: [폰] 사진 업로드 ---
with st.expander("📸 1단계: [폰에서 접속] 사진 업로드", expanded=True):
    files = st.file_uploader("영수증 사진 선택", accept_multiple_files=True)
    if files and st.button("🚀 사진 전송"):
        data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)
        new_list = []
        for f in files:
            img_b64 = img_to_base64(Image.open(f))
            new_list.append({
                "날짜": datetime.now().strftime('%Y-%m-%d'),
                "식당명": "입력전", "금액": 0, "비고": "", 
                "사진데이터": img_b64, "상태": "대기"
            })
        updated = pd.concat([data, pd.DataFrame(new_list)], ignore_index=True)
        conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated)
        st.success("사진 전송 완료! 이제 PC에서 수정하세요.")

# --- 2단계: [PC] 내역 수정 ---
st.divider()
all_data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)

if not all_data.empty:
    st.subheader("💻 2단계: [PC에서 접속] 내역 수정")
    edit_idx = st.selectbox("수정할 항목", all_data.index, format_func=lambda x: f"[{x}] {all_data.at[x, '날짜']}")
    row = all_data.loc[edit_idx]
    
    c_img, c_form = st.columns([1, 2])
    with c_img:
        st.image(base64.b64decode(row["사진데이터"]), caption="현재 사진", width=300)
    with c_form:
        f1, f2 = st.columns(2)
        with f1:
            u_date = st.text_input("날짜", row["날짜"])
            u_name = st.text_input("식당명", row["식당명"])
        with f2:
            u_price = st.number_input("금액", value=int(row["금액"]))
            u_note = st.text_input("비고", row["비고"])
        
        if st.button("💾 이 내역 저장 및 완료"):
            all_data.at[edit_idx, "날짜"] = u_date
            all_data.at[edit_idx, "식당명"] = u_name
            all_data.at[edit_idx, "금액"] = u_price
            all_data.at[edit_idx, "비고"] = u_note
            all_data.at[edit_idx, "상태"] = "완료"
            conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=all_data)
            st.success("수정 완료!")
            st.rerun()

    # --- 3단계: 다운로드 (엑셀 따로, PDF 따로) ---
    st.divider()
    st.subheader("📥 3단계: 최종 결과물 다운로드")
    done_df = all_data[all_data["상태"] == "완료"]
    
    col_ex, col_pdf = st.columns(2)
    with col_ex:
        # 내역은 엑셀로 다운로드
        excel_out = io.BytesIO()
        done_df.drop(columns=["사진데이터", "상태"]).to_excel(excel_out, index=False)
        st.download_button("📊 엑셀(내역서) 받기", excel_out.getvalue(), "영수증_내역.xlsx")
    
    with col_pdf:
        # 사진은 PDF로 다운로드
        if st.button("📄 PDF(사진증빙) 만들기"):
            pdf_bytes = create_photo_pdf(done_df)
            st.download_button("📥 PDF(사진증빙) 받기", pdf_bytes, "영수증_사진증빙.pdf")

    # 데이터 삭제 버튼 (필요시)
    if st.button("🗑️ 선택한 행 영구 삭제"):
        all_data = all_data.drop(edit_idx).reset_index(drop=True)
        conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=all_data)
        st.rerun()
