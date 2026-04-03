import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import io
import base64
from PIL import Image, ImageOps
from fpdf import FPDF

# 0. 기본 설정
st.set_page_config(page_title="영수증 관리 마스터", layout="wide")
SHEET_URL = "https://docs.google.com/spreadsheets/d/1x419Jb6laxcObm4z2nFU_W65Cx-4AxmAjwmE8ouFmjk/edit?usp=sharing"
conn = st.connection("gsheets", type=GSheetsConnection)

def get_meal_priority(meal_name):
    priority = {"조식": 1, "중식": 2, "석식": 3}
    return priority.get(meal_name, 2)

def img_to_base64(image):
    image = ImageOps.exif_transpose(image)
    image.thumbnail((500, 500)) 
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG", quality=50)
    return base64.b64encode(buffered.getvalue()).decode()

def create_photo_pdf(df):
    pdf = FPDF()
    # 날짜와 시간대 가중치로 정렬
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

# 1. 데이터 불러오기 (API 에러 방지를 위해 ttl 설정 강화)
try:
    # 데이터가 비어있을 경우를 대비해 기본 스키마 정의
    default_df = pd.DataFrame(columns=["날짜", "식당명", "시간대", "금액", "비고", "사진데이터", "상태"])
    raw_data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl="5m").astype(str) # 5분간 캐싱하여 API 호출 절약
    
    if raw_data.empty or "사진데이터" not in raw_data.columns:
        all_data = default_df
    else:
        all_data = raw_data[raw_data["사진데이터"] != "nan"].fillna("")
        all_data['priority'] = all_data['시간대'].apply(get_meal_priority)
        all_data = all_data.sort_values(by=["날짜", "priority"], ascending=[True, True])
except Exception as e:
    st.error("데이터를 불러오는 중 API 오류가 발생했습니다. 잠시 후 새로고침(F5) 해주세요.")
    all_data = default_df

st.title("📑 법카 영수증 관리 (한정민 선임)")

# --- 1단계: 사진 업로드 ---
with st.expander("📸 1단계: 사진 업로드 (시간 자동 감지)", expanded=True):
    files = st.file_uploader("사진 선택", accept_multiple_files=True)
    if files and st.button("🚀 사진 전송"):
        new_list = []
        now = datetime.now()
        curr_h = now.hour
        auto_meal = "조식" if curr_h < 10 else "중식" if curr_h < 16 else "석식"
        for f in files:
            img_b64 = img_to_base64(Image.open(f))
            new_list.append({"날짜": now.strftime('%y-%m-%d'), "식당명": "", "시간대": auto_meal, "금액": "0", "비고": "", "사진데이터": img_b64, "상태": "대기"})
        
        updated = pd.concat([all_data, pd.DataFrame(new_list)], ignore_index=True)
        updated = updated.drop(columns=['priority'], errors='ignore')
        conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated)
        st.cache_data.clear() # 업데이트 후 캐시 삭제
        st.rerun()

# --- 2단계: 내역 수정 ---
st.divider()
if not all_data.empty:
    st.subheader("💻 2단계: 상세 내용 수정")
    row_list = all_data.to_dict('records')
    idx = st.selectbox("수정 항목 선택", range(len(row_list)), format_func=lambda x: f"[{x}] {row_list[x]['날짜']} {row_list[x]['식당명']} ({row_list[x]['시간대']})")
    row = row_list[idx]
    
    c1, c2 = st.columns([1, 2])
    with c1: 
        if row["사진데이터"]: st.image(base64.b64decode(row["사진데이터"]), width=300)
    with c2:
        f1, f2 = st.columns(2)
        with f1:
            try: d_val = datetime.strptime(row["날짜"], '%y-%m-%d')
            except: d_val = datetime.now()
            u_date = st.date_input("날짜", d_val)
            u_name = st.text_input("식당명", row["식당명"])
        with f2:
            meal_opts = ["조식", "중식", "석식"]
            curr_m = row["시간대"] if row["시간대"] in meal_opts else "중식"
            u_meal = st.selectbox("시간대", meal_opts, index=meal_opts.index(curr_m))
            c_price = str(row["금액"]).split('.')[0].replace(',', '')
            f_price = f"{int(c_price):,}" if c_price.isdigit() else c_price
            u_price = st.text_input("금액", value=f_price)
        u_note = st.text_input("비고", row["비고"])
        
        if st.button("💾 저장 및 자동 정렬"):
            row_list[idx].update({"날짜": u_date.strftime('%y-%m-%d'), "식당명": u_name, "시간대": u_meal, "금액": u_price.replace(',', ''), "비고": u_note, "상태": "완료"})
            new_df = pd.DataFrame(row_list).drop(columns=['priority'], errors='ignore')
            conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=new_df)
            st.cache_data.clear()
            st.rerun()

    # --- [센스] 실시간 내역 확인창 ---
    st.divider()
    st.subheader("👀 현재 저장된 내역 (실시간)")
    if not all_data.empty:
        display_df = all_data.drop(columns=["사진데이터", "priority"], errors='ignore').copy()
        display_df["금액"] = display_df["금액"].apply(lambda x: f"{int(float(x)):,}" if str(x).replace('.','').isdigit() else x)
        st.dataframe(display_df, use_container_width=True)

    # --- 3단계: 다운로드 ---
    st.divider()
    done_df = all_data[all_data["상태"] == "완료"]
    if not done_df.empty:
        st.subheader("📥 3단계: 결과물 다운로드")
        d1, d2 = st.columns(2)
        with d1:
            ex_out = io.BytesIO()
            rep_df = done_df.copy()
            rep_df["금액"] = rep_df["금액"].apply(lambda x: f"{int(float(x)):,}" if str(x).replace('.','').isdigit() else x)
            rep_df.drop(columns=["사진데이터", "상태", "priority"], errors='ignore').to_excel(ex_out, index=False)
            st.download_button("📊 엑셀 다운로드", ex_out.getvalue(), "Receipt_List.xlsx")
        with d2:
            st.download_button("📄 PDF 다운로드", create_photo_pdf(done_df), "Receipt_Photos.pdf", "application/pdf")
