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

# 시간대 정렬을 위한 가중치 함수
def get_meal_priority(meal_name):
    priority = {"조식": 1, "중식": 2, "석식": 3}
    return priority.get(meal_name, 2) # 기본값은 중식(2)

def img_to_base64(image):
    image = ImageOps.exif_transpose(image)
    image.thumbnail((500, 500)) 
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG", quality=50)
    return base64.b64encode(buffered.getvalue()).decode()

def create_photo_pdf(df):
    pdf = FPDF()
    # [중요] PDF 생성 전 날짜순 -> 시간대(조>중>석)순으로 정렬
    df['priority'] = df['시간대'].apply(get_meal_priority)
    df_sorted = df.sort_values(by=["날짜", "priority"], ascending=[True, True])
    
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

# 1. 데이터 불러오기 및 정렬
raw_data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0).astype(str)
all_data = raw_data[raw_data["사진데이터"] != "nan"].fillna("")

if not all_data.empty:
    all_data['priority'] = all_data['시간대'].apply(get_meal_priority)
    all_data = all_data.sort_values(by=["날짜", "priority"], ascending=[True, True])

# --- 1단계: 사진 업로드 ---
with st.expander("📸 1단계: 사진 업로드 (시간 자동 감지)", expanded=True):
    files = st.file_uploader("사진 선택", accept_multiple_files=True)
    if files and st.button("🚀 사진 전송"):
        new_list = []
        now = datetime.now()
        
        # [센스] 시간 읽기 기능: 10시 이전 조식, 16시 이전 중식, 이후 석식
        current_hour = now.hour
        if current_hour < 10: auto_meal = "조식"
        elif current_hour < 16: auto_meal = "중식"
        else: auto_meal = "석식"
        
        for f in files:
            img_b64 = img_to_base64(Image.open(f))
            new_list.append({
                "날짜": now.strftime('%y-%m-%d'), 
                "식당명": "", 
                "시간대": auto_meal, # 자동 감지된 시간대 적용
                "금액": "0", "비고": "", "사진데이터": img_b64, "상태": "대기"
            })
        
        updated = pd.concat([all_data, pd.DataFrame(new_list)], ignore_index=True)
        updated['priority'] = updated['시간대'].apply(get_meal_priority)
        updated = updated.sort_values(by=["날짜", "priority"], ascending=[True, True]).drop(columns=['priority'])
        conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated)
        st.rerun()

# --- 2단계: 내역 수정 ---
st.divider()
if not all_data.empty:
    st.subheader("💻 2단계: 상세 내용 수정")
    row_list = all_data.to_dict('records')
    idx = st.selectbox("수정 항목 선택", range(len(row_list)), format_func=lambda x: f"[{x}] {row_list[x]['날짜']} {row_list[x]['식당명']} ({row_list[x]['시간대']})")
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
            # [요청] 기본 선택은 '중식'으로 하되, 기존 데이터가 있으면 유지
            meal_options = ["조식", "중식", "석식"]
            current_meal = row["시간대"] if row["시간대"] in meal_options else "중식"
            u_meal = st.selectbox("시간대", meal_options, index=meal_options.index(current_meal))
            
            clean_price = str(row["금액"]).split('.')[0].replace(',', '')
            try: formatted_price = f"{int(clean_price):,}" if clean_price.isdigit() else clean_price
            except: formatted_price = clean_price
            u_price = st.text_input("금액", value=formatted_price)
        
        u_note = st.text_input("비고", row["비고"])
        
        if st.button("💾 저장 및 자동 정렬"):
            save_price = u_price.replace(',', '')
            row_list[idx].update({"날짜": u_date.strftime('%y-%m-%d'), "식당명": u_name, "시간대": u_meal, "금액": save_price, "비고": u_note, "상태": "완료"})
            new_df = pd.DataFrame(row_list)
            new_df['priority'] = new_df['시간대'].apply(get_meal_priority)
            new_df = new_df.sort_values(by=["날짜", "priority"], ascending=[True, True]).drop(columns=['priority'])
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
            report_df = done_df.copy()
            report_df["금액"] = report_df["금액"].apply(lambda x: f"{int(float(x)):,}" if str(x).replace('.','').isdigit() else x)
            report_df.drop(columns=["사진데이터", "상태", "priority"], errors='ignore').to_excel(excel_out, index=False)
            st.download_button("📊 엑셀 내역서 다운로드", excel_out.getvalue(), "Receipt_List.xlsx")
        with col_pdf:
            pdf_bytes = create_photo_pdf(done_df)
            st.download_button("📄 PDF 사진증빙 다운로드", pdf_bytes, "Receipt_Photos.pdf", "application/pdf")
