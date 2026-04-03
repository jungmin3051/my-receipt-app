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
    # 글자 없이 사진만 4장씩 배치 (에러 0%)
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

st.title("📑 법카 영수증 관리 (한정민 선임)")

# 1. 데이터 불러오기 (캐시 없이 강제 로드)
all_data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)

# --- 1단계: 사진 업로드 (폰용) ---
with st.expander("📸 1단계: 사진 업로드", expanded=True):
    files = st.file_uploader("영수증 사진 선택", accept_multiple_files=True)
    if files and st.button("🚀 사진 전송"):
        new_list = []
        for f in files:
            img_b64 = img_to_base64(Image.open(f))
            new_list.append({"날짜": datetime.now().strftime('%Y-%m-%d'), "식당명": "", "금액": 0, "비고": "", "사진데이터": img_b64, "상태": "대기"})
        updated = pd.concat([all_data, pd.DataFrame(new_list)], ignore_index=True)
        conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated)
        st.success("업로드 완료!")
        st.rerun()

# --- 2단계: 내역 수정 (PC용) ---
st.divider()
if not all_data.empty:
    st.subheader("💻 2단계: 내역 수정")
    # 인덱스 대신 안전하게 리스트 번호로 선택
    row_list = all_data.to_dict('records')
    idx = st.selectbox("항목 선택", range(len(row_list)), format_func=lambda x: f"[{x}] {row_list[x]['날짜']} {row_list[x]['식당명']}")
    row = row_list[idx]
    
    c_img, c_form = st.columns([1, 2])
    with c_img:
        st.image(base64.b64decode(row["사진데이터"]), width=300)
    with c_form:
        f1, f2 = st.columns(2)
        with f1:
            u_date = st.text_input("날짜", str(row["날짜"]))
            u_name = st.text_input("식당명", str(row["식당명"]))
        with f2:
            u_price = st.text_input("금액", value=str(row["금액"]))
            u_note = st.text_input("비고", str(row["비고"]))
        
        if st.button("💾 이 내역 저장"):
            # 판다스 에러를 피하기 위해 딕셔너리 리스트를 직접 수정 후 데이터프레임 재생성
            row_list[idx]["날짜"] = u_date
            row_list[idx]["식당명"] = u_name
            row_list[idx]["금액"] = u_price
            row_list[idx]["비고"] = u_note
            row_list[idx]["상태"] = "완료"
            
            new_df = pd.DataFrame(row_list)
            conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=new_df)
            st.success("저장되었습니다!")
            st.rerun()

    # --- 3단계: 다운로드 ---
    st.divider()
    done_df = all_data[all_data["상태"] == "완료"]
    d1, d2 = st.columns(2)
    with d1:
        excel_out = io.BytesIO()
        done_df.drop(columns=["사진데이터", "상태"]).to_excel(excel_out, index=False)
        st.download_button("📊 엑셀(내역서) 다운로드", excel_out.getvalue(), "Receipt_List.xlsx")
    with d2:
        if st.button("📄 PDF(사진증빙) 생성"):
            pdf_bytes = create_photo_pdf(done_df)
            st.download_button("📥 PDF 다운로드", pdf_bytes, "Receipt_Photos.pdf")
            
    if st.button("🗑️ 선택 항목 삭제"):
        all_data = all_data.drop(idx).reset_index(drop=True)
        conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=all_data)
        st.rerun()
