import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import io
import base64
from PIL import Image, ImageOps
from fpdf import FPDF

# 0. 기본 설정
st.set_page_config(page_title="정민 선임 영수증 관리", layout="wide")
SHEET_URL = "https://docs.google.com/spreadsheets/d/1x419Jb6laxcObm4z2nFU_W65Cx-4AxmAjwmE8ouFmjk/edit?usp=sharing"
conn = st.connection("gsheets", type=GSheetsConnection)

def img_to_base64(image):
    image = ImageOps.exif_transpose(image)
    image.thumbnail((500, 500)) 
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG", quality=50)
    return base64.b64encode(buffered.getvalue()).decode()

def create_4split_pdf(df):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=10)
    
    # '완료' 상태인 사진들만 필터링
    photo_rows = df[df["상태"] == "완료"].reset_index()
    
    for i, (_, row) in enumerate(photo_rows.iterrows()):
        if i % 4 == 0:
            pdf.add_page()
        
        img_data = base64.b64decode(row["사진데이터"])
        img = Image.open(io.BytesIO(img_data))
        temp_img = io.BytesIO()
        img.save(temp_img, format="JPEG")
        
        # 한 페이지 4분할 좌표 (2x2 배치)
        x = 10 if (i % 2 == 0) else 105
        y = 10 if (i % 4 < 2) else 148
        
        pdf.image(temp_img, x=x, y=y, w=90)
    return pdf.output()

st.title("📑 영수증 관리 시스템 (한정민 선임)")

# --- 1단계: 업로드 ---
with st.expander("📸 1단계: 새 영수증 업로드", expanded=True):
    files = st.file_uploader("영수증 사진 선택 (여러 장 가능)", accept_multiple_files=True)
    if files and st.button("🚀 시트로 전송"):
        data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)
        new_records = []
        for f in files:
            img_b64 = img_to_base64(Image.open(f))
            new_records.append({
                "날짜": datetime.now().strftime('%Y-%m-%d'),
                "식당명": "입력필요", "금액": 0, "비고": "", 
                "사진데이터": img_b64, "상태": "대기"
            })
        updated = pd.concat([data, pd.DataFrame(new_records)], ignore_index=True)
        conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated)
        st.success(f"{len(files)}장 업로드 완료!")
        st.rerun()

# --- 2단계: 내용 수정 ---
st.divider()
all_data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)

if not all_data.empty:
    st.subheader("📝 2단계: 내용 수정 및 '완료' 처리")
    
    # 수정할 항목 선택
    pending_df = all_data[all_data["상태"] == "대기"]
    if not pending_df.empty:
        idx = st.selectbox("수정할 영수증 선택", pending_df.index)
        row = all_data.loc[idx]
        
        col1, col2 = st.columns([1, 1.5])
        with col1:
            st.image(base64.b64decode(row["사진데이터"]), caption="원본 사진")
        with col2:
            u_date = st.text_input("날짜", row["날짜"])
            u_name = st.text_input("식당명", row["식당명"])
            u_price = st.number_input("금액", value=int(row["금액"]))
            u_note = st.text_input("비고", row["비고"])
            
            if st.button("💾 정보 저장 및 완료"):
                all_data.at[idx, "날짜"] = u_date
                all_data.at[idx, "식당명"] = u_name
                all_data.at[idx, "금액"] = u_price
                all_data.at[idx, "비고"] = u_note
                all_data.at[idx, "상태"] = "완료"
                conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=all_data)
                st.success("저장되었습니다!")
                st.rerun()
    else:
        st.info("수정할 대기 내역이 없습니다.")

    # --- 3단계: PDF 다운로드 ---
    st.divider()
    st.subheader("🖨️ 3단계: PDF 증빙 출력 (4분할)")
    
    done_df = all_data[all_data["상태"] == "완료"]
    if not done_df.empty:
        st.write(f"현재 완료된 영수증: {len(done_df)}장")
        if st.button("📄 PDF 파일 생성 시작", type="primary"):
            pdf_bytes = create_4split_pdf(all_data)
            st.download_button(
                "📥 PDF 다운로드", 
                pdf_bytes, 
                f"영수증증빙_{datetime.now().strftime('%m%d')}.pdf",
                "application/pdf"
            )
    else:
        st.warning("완료 처리된 영수증이 없습니다.")
    
    # 전체 데이터 표 (삭제 기능 포함)
    with st.expander("🗑️ 전체 데이터 보기 및 삭제"):
        st.dataframe(all_data.drop(columns=["사진데이터"]))
        del_idx = st.number_input("삭제할 행 번호", min_value=0, max_value=len(all_data)-1, step=1)
        if st.button("❌ 선택 행 삭제"):
            all_data = all_data.drop(del_idx).reset_index(drop=True)
            conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=all_data)
            st.rerun()
