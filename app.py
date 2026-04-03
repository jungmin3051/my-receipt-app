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
    df_sorted = df.sort_values(by=["날짜", "시간대"], ascending=[True, True])
    for i, (_, row) in enumerate(df_sorted.iterrows()):
        if i % 4 == 0: pdf.add_page()
        try:
            img_data = base64.b64decode(row["사진데이터"])
            temp_img = io.BytesIO(img_data)
            x, y = (10 if i % 2 == 0 else 105), (10 if i % 4 < 2 else 148)
            pdf.image(temp_img, x=x, y=y, w=90)
        except: continue
    return bytes(pdf.output())

st.title("📑 법카 영수증 관리 (한정민 선임)")

# 1. 데이터 불러오기 및 타입 정리
raw_data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0).astype(str)
all_data = raw_data[raw_data["사진데이터"] != "nan"].fillna("")
if not all_data.empty:
    all_data = all_data.sort_values(by=["날짜", "시간대"], ascending=[True, True])

# --- 1단계: 사진 업로드 ---
with st.expander("📸 1단계: 사진 업로드", expanded=True):
    files = st.file_uploader("사진 선택", accept_multiple_files=True)
    if files and st.button("🚀 사진 전송"):
        new_list = []
        now = datetime.now()
        meal = "조식" if now.hour < 10 else "중식" if now.hour < 16 else "석식"
        for f in files:
            img_b64 = img_to_base64(Image.open(f))
            new_list.append({"날짜": now.strftime('%y-%m-%d'), "식당명": "", "시간대": meal, "금액": "0", "비고": "", "사진데이터": img_b64, "상태": "대기"})
        updated = pd.concat([all_data, pd.DataFrame(new_list)], ignore_index=True)
        conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated)
        st.rerun()

# --- 2단계: 내역 수정 ---
st.divider()
if not all_data.empty:
    st.subheader("💻 2단계: 상세 내용 수정")
    row_list = all_data.to_dict('records')
    idx = st.selectbox("수정 항목 선택", range(len(row_list)), format_func=lambda x: f"[{x}] {row_list[x]['날짜']} {row_list[x]['식당명']}")
    row = row_list[idx]
    
    c1, c2 = st.columns([1, 2])
    with c1: st.image(base64.b64decode(row["사진데이터"]), width=300)
    with c2:
        f1, f2 = st.columns(2)
        with f1:
            try: d_val = datetime.strptime(row["날짜"], '%y-%m-%d')
            except: d_val = datetime.now()
            u_date = st.date_input("날짜", d_val)
            u_name = st.text_input("식당명", row["식당명"])
        with f2:
            u_meal = st.selectbox("시간대", ["조식", "중식", "석식"], index=["조식", "중식", "석식"].index(row["시간대"]) if row["시간대"] in ["조식", "중식", "석식"] else 1)
            # [센스] 금액 처리: .0 제거 후 콤마 추가
            clean_price = str(row["금액"]).split('.')[0].replace(',', '')
            try: formatted_price = f"{int(clean_price):,}" if clean_price.isdigit() else clean_price
            except: formatted_price = clean_price
            u_price = st.text_input("금액", value=formatted_price)
        
        # [센스] 비고 칸 높이를 다른 입력창과 동일하게 (label_visibility로 간격 조정)
        u_note = st.text_input("비고", row["비고"]) 
        
        if st.button("💾 저장 및 정렬"):
            # 저장할 때는 다시 콤마 제거
            save_price = u_price.replace(',', '')
            row_list[idx].update({"날짜": u_date.strftime('%y-%m-%d'), "식당명": u_name, "시간대": u_meal, "금액": save_price, "비고": u_note, "상태": "완료"})
            new_df = pd.DataFrame(row_list).sort_values(by=["날짜", "시간대"], ascending=[True, True])
            conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=new_df)
            st.rerun()

    # --- 3단계: 다운로드 ---
    st.divider()
    done_df = all_data[all_data["상태"] == "완료"]
    if not done_df.empty:
        st.subheader("📥 3단계: 결과물 다운로드")
        col_ex, col_pdf = st.columns(2)
        with col_ex:
            excel_out = io.BytesIO()
            # 엑셀 저장 시에도 금액 포맷 적용
            report_df = done_df.copy()
            report_df["금액"] = report_df["금액"].apply(lambda x: f"{int(float(x)):,}" if str(x).replace('.','').isdigit() else x)
            report_df.drop(columns=["사진데이터", "상태"]).to_excel(excel_out, index=False)
            st.download_button("📊 엑셀 내역서 다운로드", excel_out.getvalue(), "Receipt_List.xlsx")
        with col_pdf:
            pdf_bytes = create_photo_pdf(done_df)
            st.download_button("📄 PDF 사진증빙 다운로드", pdf_bytes, "Receipt_Photos.pdf", "application/pdf")
