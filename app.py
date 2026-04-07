import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import io
import base64
from PIL import Image, ImageOps
from fpdf import FPDF
import time

# 0. 기본 설정
st.set_page_config(page_title="법카 영수증 관리", layout="wide")
SHEET_URL = "https://docs.google.com/spreadsheets/d/1x419Jb6laxcObm4z2nFU_W65Cx-4AxmAjwmE8ouFmjk/edit?usp=sharing"
conn = st.connection("gsheets", type=GSheetsConnection)

# 시간대별 정렬 우선순위
def get_meal_priority(meal_name):
    priority = {"조식": 1, "중식": 2, "석식": 3}
    return priority.get(meal_name, 4)

def format_price(val):
    try:
        if not val or str(val).lower() in ['nan', '0', '']: return ""
        clean_val = str(val).split('.')[0].replace(',', '')
        if clean_val.isdigit(): return f"{int(clean_val):,}"
        return val
    except: return ""

def fix_date(d):
    d_str = str(d).strip()
    if len(d_str) > 8: return d_str[-8:] 
    return d_str

def img_to_base64(image):
    image = ImageOps.exif_transpose(image)
    if image.mode != 'RGB': image = image.convert('RGB')
    image.thumbnail((600, 600)) 
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG", quality=30) 
    return base64.b64encode(buffered.getvalue()).decode()

def create_photo_pdf(df):
    pdf = FPDF()
    pdf.set_font("Arial", size=10)
    df['temp_p'] = df['시간대'].apply(get_meal_priority)
    df_sorted = df.sort_values(by=["날짜", "temp_p"]).reset_index(drop=True)
    for i, (_, row) in enumerate(df_sorted.iterrows()):
        if i % 4 == 0: pdf.add_page()
        try:
            img_data = base64.b64decode(row["사진데이터"])
            temp_img = io.BytesIO(img_data)
            x, y = (10 if i % 2 == 0 else 105), (10 if i % 4 < 2 else 148)
            pdf.image(temp_img, x=x, y=y, w=90)
            pdf.set_xy(x, y + 62)
            info_text = f"{row['날짜']} / {row['식당명']} / {row['시간대']} / {row['금액']}"
            pdf.cell(90, 10, info_text, ln=0, align='C')
        except: continue
    return bytes(pdf.output())

# 1. 데이터 로드 및 이중 정렬
COLUMNS = ["날짜", "식당명", "시간대", "금액", "비고", "사진데이터", "상태"]
try:
    all_data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0).astype(str)
    all_data = all_data[all_data["사진데이터"] != "nan"].fillna("")
    if not all_data.empty:
        all_data['날짜'] = all_data['날짜'].apply(fix_date)
        all_data['금액'] = all_data['금액'].apply(format_price)
        all_data['temp_p'] = all_data['시간대'].apply(get_meal_priority)
        all_data = all_data.sort_values(by=["날짜", "temp_p"], ascending=[True, True]).reset_index(drop=True)
        all_data = all_data.drop(columns=['temp_p'])
except:
    all_data = pd.DataFrame(columns=COLUMNS)

st.title("📑 법카 영수증 관리")

# --- 1단계: 사진 업로드 ---
with st.expander("📸 1단계: 사진 업로드", expanded=True):
    files = st.file_uploader("사진 선택", accept_multiple_files=True)
    if files and st.button("🚀 사진 전송"):
        new_list = []
        now = datetime.now()
        for f in files:
            try:
                img_b64 = img_to_base64(Image.open(f))
                new_list.append({"날짜": now.strftime('%y-%m-%d'), "식당명": "", "시간대": "중식", "금액": "", "비고": "", "사진데이터": img_b64, "상태": "대기"})
            except Exception as e: st.error(f"오류: {e}")
        if new_list:
            updated = pd.concat([all_data, pd.DataFrame(new_list)], ignore_index=True)
            conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated[COLUMNS])
            st.cache_data.clear()
            time.sleep(1)
            st.rerun()

# --- 2단계: 개별 내용 수정 ---
st.divider()
if not all_data.empty:
    st.subheader("💻 2단계: 개별 내용 수정")
    row_list = all_data.to_dict('records')
    
    if "selected_index" not in st.session_state:
        st.session_state.selected_index = 0
        for i, r in enumerate(row_list):
            if r["상태"] == "대기":
                st.session_state.selected_index = i
                break
    
    curr_idx = min(st.session_state.selected_index, len(row_list)-1)
    
    idx = st.selectbox(
        "항목 선택", 
        range(len(row_list)), 
        index=curr_idx,
        format_func=lambda x: f"[{x+1}] {row_list[x]['날짜']} | {row_list[x]['식당명'] if row_list[x]['식당명'] else '미입력'} - {row_list[x]['상태']}"
    )
    
    if idx != st.session_state.selected_index:
        st.session_state.selected_index = idx
        st.rerun()

    row = row_list[idx]
    # [수정] '대기' 상태인 항목을 새로 선택하면 입력란을 무조건 빈칸으로 강제함
    is_pending = (row["상태"] == "대기")
    
    c1, c2 = st.columns([1, 2])
    with c1: 
        if row["사진데이터"]: st.image(base64.b64decode(row["사진데이터"]), width=300)
    with c2:
        f1, f2 = st.columns(2)
        with f1:
            try: d_val = datetime.strptime(row["날짜"], '%y-%m-%d')
            except: d_val = datetime.now()
            u_date = st.date_input("날짜", d_val)
            # 대기 상태면 빈칸, 아니면 저장된 값
            u_name = st.text_input("식당명", value="" if is_pending else row["식당명"])
        with f2:
            meal_opts = ["조식", "중식", "석식"]
            u_meal = st.selectbox("시간대", meal_opts, index=1 if is_pending else meal_opts.index(row["시간대"]) if row["시간대"] in meal_opts else 1)
            u_price = st.text_input("금액", value="" if is_pending else format_price(row["금액"]))
        u_note = st.text_input("비고", value="" if is_pending else row["비고"])
        
        if st.button("💾 이 항목 저장", use_container_width=True):
            with st.spinner("저장 중..."):
                row_list[idx].update({
                    "날짜": u_date.strftime('%y-%m-%d'), "식당명": u_name, "시간대": u_meal, 
                    "금액": format_price(u_price), "비고": u_note, "상태": "완료"
                })
                new_df = pd.DataFrame(row_list)
                conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=new_df[COLUMNS])
                st.cache_data.clear()
                time.sleep(1)
                
                # 저장 후 다음 대기 항목 찾기
                next_idx = idx
                for i in range(len(row_list)):
                    if row_list[i]["상태"] == "대기":
                        next_idx = i
                        break
                st.session_state.selected_index = next_idx
                # 리런하여 다음 항목의 입력창을 빈칸(is_pending=True)으로 만듦
                st.rerun()

# --- 3단계: 내역 확인 및 삭제 ---
if not all_data.empty:
    st.divider()
    st.subheader("👀 3단계: 내역 확인 및 체크 삭제")
    edit_df = all_data.drop(columns=["사진데이터"], errors='ignore').copy()
    edit_df["삭제체크"] = False
    edit_df.index = edit_df.index + 1 
    
    edited_data = st.data_editor(
        edit_df, use_container_width=True,
        column_config={"삭제체크": st.column_config.CheckboxColumn(label="삭제", default=False)},
        disabled=["날짜", "식당명", "시간대", "금액", "비고", "상태"]
    )
    
    checked_indices = edited_data[edited_data["삭제체크"] == True].index.tolist()
    real_indices = [i-1 for i in checked_indices]
    
    if real_indices:
        if st.button(f"🗑️ {len(real_indices)}개 항목 일괄 삭제", type="primary", use_container_width=True):
            remaining_df = all_data.drop(all_data.index[real_indices]).reset_index(drop=True)
            conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=remaining_df[COLUMNS])
            st.cache_data.clear()
            st.session_state.selected_index = 0
            time.sleep(1)
            st.rerun()

# --- 4단계: 다운로드 ---
st.divider()
done_df = all_data[all_data["상태"] == "완료"]
if not done_df.empty:
    st.subheader("📥 4단계: 다운로드")
    d1, d2 = st.columns(2)
    with d1:
        ex_out = io.BytesIO()
        excel_df = done_df.drop(columns=["사진데이터", "상태"], errors='ignore').copy()
        excel_df.to_excel(ex_out, index=False)
        st.download_button("📊 엑셀 다운로드", ex_out.getvalue(), "Receipt_List.xlsx")
    with d2:
        pdf_fn = f"{datetime.now().month}월 개인법인카드 영수증_한정민.pdf"
        st.download_button("📄 영수증 PDF 다운로드", create_photo_pdf(done_df), pdf_fn, "application/pdf")
