import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import io
import base64
from PIL import Image, ImageOps
from fpdf import FPDF

# 0. 설정
st.set_page_config(page_title="영수증 관리 마스터", layout="wide")
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
    return pdf.output(dest='S').encode('latin-1')

st.title("📑 영수증 통합 관리 (한정민 선임)")

# 1. 데이터 불러오기 및 nan 처리 (비고 칸 빈칸으로!)
all_data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)
all_data = all_data.fillna("") # 모든 nan을 빈칸으로 자동 변경

# --- 1단계: 사진 업로드 (폰용) ---
with st.expander("📸 1단계: 사진 업로드", expanded=True):
    files = st.file_uploader("영수증 사진 선택", accept_multiple_files=True)
    if files and st.button("🚀 사진 전송"):
        new_list = []
        now = datetime.now()
        # 시간대에 따른 기본값 자동 파악
        current_hour = now.hour
        default_meal = "조식" if current_hour < 10 else "중식" if current_hour < 16 else "석식"
        
        for f in files:
            img_b64 = img_to_base64(Image.open(f))
            new_list.append({
                "날짜": now.strftime('%Y-%m-%d'), 
                "식당명": "", 
                "시간대": default_meal,
                "금액": 0, 
                "비고": "", 
                "사진데이터": img_b64, 
                "상태": "대기"
            })
        updated = pd.concat([all_data, pd.DataFrame(new_list)], ignore_index=True)
        conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated)
        st.rerun()

# --- 2단계: 내역 수정 (PC용) ---
st.divider()
if not all_data.empty:
    st.subheader("💻 2단계: 내역 수정 (달력/시간대 선택)")
    row_list = all_data.to_dict('records')
    idx = st.selectbox("항목 선택", range(len(row_list)), 
                       format_func=lambda x: f"[{x}] {row_list[x]['날짜']} {row_list[x]['식당명']} ({row_list[x]['시간대']})")
    row = row_list[idx]
    
    c_img, c_form = st.columns([1, 2])
    with c_img:
        st.image(base64.b64decode(row["사진데이터"]), width=300)
    with c_form:
        f1, f2 = st.columns(2)
        with f1:
            # 날짜 선택기 (달력 소환!)
            try:
                curr_date = datetime.strptime(str(row["날짜"]), '%Y-%m-%d')
            except:
                curr_date = datetime.now()
            u_date = st.date_input("날짜 선택", curr_date)
            u_name = st.text_input("식당명", str(row["식당명"]))
        with f2:
            # 시간대 선택 (조/중/석)
            meal_options = ["조식", "중식", "석식"]
            default_idx = meal_options.index(row["시간대"]) if row["시간대"] in meal_options else 1
            u_meal = st.selectbox("시간대", meal_options, index=default_idx)
            u_price = st.text_input("금액", value=str(row["금액"]))
        
        u_note = st.text_area("비고 (메모)", str(row["비고"]))
        
        if st.button("💾 수정 내용 저장"):
            row_list[idx].update({
                "날짜": u_date.strftime('%Y-%m-%d'), 
                "식당명": u_name, 
                "시간대": u_meal,
                "금액": u_price, 
                "비고": u_note, 
                "상태": "완료"
            })
            conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=pd.DataFrame(row_list))
            st.success("성공적으로 저장되었습니다!")
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
            st.download_button("📥 PDF 다운로드", pdf_bytes, "Receipt_Photos.pdf", "application/pdf")
            
    if st.button("🗑️ 행 삭제"):
        all_data = all_data.drop(idx).reset_index(drop=True)
        conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=all_data)
        st.rerun()
