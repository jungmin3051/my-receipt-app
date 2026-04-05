import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import io
import base64
from PIL import Image, ImageOps
from fpdf import FPDF

# 0. 기본 설정
st.set_page_config(page_title="법카 영수증 관리", layout="wide")
SHEET_URL = "https://docs.google.com/spreadsheets/d/1x419Jb6laxcObm4z2nFU_W65Cx-4AxmAjwmE8ouFmjk/edit?usp=sharing"
conn = st.connection("gsheets", type=GSheetsConnection)

def get_meal_priority(meal_name):
    priority = {"조식": 1, "중식": 2, "석식": 3}
    return priority.get(meal_name, 2)

def format_price(val):
    try:
        clean_val = str(val).replace(',', '').split('.')[0]
        if clean_val.isdigit(): return f"{int(clean_val):,}"
        return val
    except: return val

def img_to_base64(image):
    image = ImageOps.exif_transpose(image)
    if image.mode != 'RGB': image = image.convert('RGB')
    image.thumbnail((600, 600)) 
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG", quality=30) 
    return base64.b64encode(buffered.getvalue()).decode()

def create_photo_pdf(df):
    pdf = FPDF()
    temp_df = df.copy()
    temp_df['priority'] = temp_df['시간대'].apply(get_meal_priority)
    df_sorted = temp_df.sort_values(by=["상태", "날짜", "priority"], ascending=[False, True, True])
    for i, (_, row) in enumerate(df_sorted.iterrows()):
        if i % 4 == 0: pdf.add_page()
        try:
            img_data = base64.b64decode(row["사진데이터"])
            temp_img = io.BytesIO(img_data)
            x, y = (10 if i % 2 == 0 else 105), (10 if i % 4 < 2 else 148)
            pdf.image(temp_img, x=x, y=y, w=90)
        except: continue
    return bytes(pdf.output())

# 1. 데이터 불러오기
COLUMNS = ["날짜", "식당명", "시간대", "금액", "비고", "사진데이터", "상태"]
try:
    all_data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0).astype(str)
    all_data = all_data[all_data["사진데이터"] != "nan"].fillna("")
    if not all_data.empty:
        all_data['날짜'] = all_data['날짜'].apply(lambda x: x[-8:] if len(x) > 8 else x)
        all_data['priority'] = all_data['시간대'].apply(get_meal_priority)
        all_data = all_data.sort_values(by=["상태", "날짜", "priority"], ascending=[False, True, True]).reset_index(drop=True)
except:
    all_data = pd.DataFrame(columns=COLUMNS)

st.title("📑 법카 영수증 관리")

# --- 1단계: 사진 업로드 ---
with st.expander("📸 1단계: 사진 업로드", expanded=True):
    files = st.file_uploader("사진 선택", accept_multiple_files=True)
    if files and st.button("🚀 사진 전송"):
        new_list = []
        now = datetime.now()
        with st.spinner("이미지 최적화 중..."):
            for f in files:
                try:
                    img_b64 = img_to_base64(Image.open(f))
                    new_list.append({"날짜": now.strftime('%y-%m-%d'), "식당명": "", "시간대": "중식", "금액": "0", "비고": "", "사진데이터": img_b64, "상태": "대기"})
                except Exception as e: st.error(f"오류: {e}")
        if new_list:
            updated = pd.concat([all_data, pd.DataFrame(new_list)], ignore_index=True)
            conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated[COLUMNS])
            st.cache_data.clear()
            st.rerun()

# --- 2단계: 개별 내용 수정 ---
st.divider()
if not all_data.empty:
    st.subheader("💻 2단계: 개별 내용 수정")
    row_list = all_data.to_dict('records')
    idx = st.selectbox("항목 선택", range(len(row_list)), format_func=lambda x: f"[{x+1}] {row_list[x]['날짜']} | {row_list[x]['식당명'] if row_list[x]['식당명'] else '미입력'} - {row_list[x]['상태']}")
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
            u_meal = st.selectbox("시간대", meal_opts, index=meal_opts.index(row["시간대"]) if row["시간대"] in meal_opts else 1)
            u_price = st.text_input("금액", value=format_price(row["금액"]))
        u_note = st.text_input("비고", row["비고"])
        if st.button("💾 이 항목 저장", use_container_width=True):
            row_list[idx].update({"날짜": u_date.strftime('%y-%m-%d'), "식당명": u_name, "시간대": u_meal, "금액": format_price(u_price), "비고": u_note, "상태": "완료"})
            new_df = pd.DataFrame(row_list)
            conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=new_df[COLUMNS])
            st.cache_data.clear()
            st.rerun()

# --- 3단계: 내역 확인 및 체크 삭제 ---
if not all_data.empty:
    st.divider()
    st.subheader("👀 3단계: 내역 확인 및 체크 삭제")
    
    # 표시용 데이터 가공 (사진데이터 제외)
    edit_df = all_data.drop(columns=["사진데이터", "priority"], errors='ignore').copy()
    # [수정] 삭제체크 열을 가장 뒤(마지막 컬럼)에 추가
    edit_df["삭제체크"] = False
    edit_df.index = edit_df.index + 1
    
    edited_data = st.data_editor(
        edit_df,
        use_container_width=True,
        column_config={
            "삭제체크": st.column_config.CheckboxColumn(label="삭제체크", help="삭제할 항목 체크", default=False)
        },
        disabled=["날짜", "식당명", "시간대", "금액", "비고", "상태"]
    )
    
    checked_indices = edited_data[edited_data["삭제체크"] == True].index.tolist()
    real_indices = [i-1 for i in checked_indices]
    
    if real_indices:
        if st.button(f"🗑️ 체크한 {len(real_indices)}개 항목 일괄 삭제", type="primary", use_container_width=True):
            remaining_df = all_data.drop(all_data.index[real_indices])
            save_df = remaining_df[COLUMNS] if not remaining_df.empty else pd.DataFrame(columns=COLUMNS)
            conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=save_df)
            st.cache_data.clear()
            st.rerun()

# --- 4단계: 다운로드 ---
st.divider()
done_df = all_data[all_data["상태"] == "완료"] if not all_data.empty else pd.DataFrame()
if not done_df.empty:
    st.subheader("📥 4단계: 다운로드")
    d1, d2 = st.columns(2)
    with d1:
        ex_out = io.BytesIO()
        excel_df = done_df.drop(columns=["사진데이터", "상태", "priority"], errors='ignore').copy()
        excel_df["금액"] = excel_df["금액"].apply(format_price)
        excel_df.to_excel(ex_out, index=False)
        st.download_button("📊 엑셀 다운로드", ex_out.getvalue(), "Receipt_List.xlsx")
    with d2:
        pdf_fn = f"{datetime.now().month}월 개인법인카드 영수증_한정민.pdf"
        st.download_button("📄 영수증 PDF 다운로드", create_photo_pdf(done_df), pdf_fn, "application/pdf")
