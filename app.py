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

def format_price(val):
    try:
        if not val or str(val).lower() in ['nan', '0', '']: return ""
        clean_val = str(val).split('.')[0].replace(',', '')
        if clean_val.isdigit(): return f"{int(clean_val):,}"
        return val
    except: return ""

def img_to_base64(image):
    image = ImageOps.exif_transpose(image)
    if image.mode != 'RGB': image = image.convert('RGB')
    image.thumbnail((600, 600)) 
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG", quality=30) 
    return base64.b64encode(buffered.getvalue()).decode()

# 1. 데이터 불러오기 (정렬 로직 최소화)
COLUMNS = ["날짜", "식당명", "시간대", "금액", "비고", "사진데이터", "상태"]
try:
    # ttl=0으로 최신 데이터 유지하되, 정렬을 제거하여 데이터 위치 고정
    all_data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0).astype(str)
    all_data = all_data[all_data["사진데이터"] != "nan"].fillna("")
    # 인덱스를 초기화하여 시트의 물리적 순서와 앱의 번호를 일치시킴
    all_data = all_data.reset_index(drop=True)
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
                    new_list.append({"날짜": now.strftime('%y-%m-%d'), "식당명": "", "시간대": "중식", "금액": "", "비고": "", "사진데이터": img_b64, "상태": "대기"})
                except Exception as e: st.error(f"오류: {e}")
        if new_list:
            updated = pd.concat([all_data, pd.DataFrame(new_list)], ignore_index=True)
            conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated[COLUMNS])
            st.cache_data.clear()
            time.sleep(1) # API 에러 방지용 지연
            st.rerun()

# --- 2단계: 개별 내용 수정 ---
st.divider()
if not all_data.empty:
    st.subheader("💻 2단계: 개별 내용 수정")
    row_list = all_data.to_dict('records')
    
    # 자동으로 다음 '대기' 항목 찾기
    if "selected_index" not in st.session_state:
        st.session_state.selected_index = 0
        for i, r in enumerate(row_list):
            if r["상태"] == "대기":
                st.session_state.selected_index = i
                break
    
    # 인덱스 유효성 검사
    curr_idx = min(st.session_state.selected_index, len(row_list)-1)
    
    idx = st.selectbox(
        "항목 선택", 
        range(len(row_list)), 
        index=curr_idx,
        format_func=lambda x: f"[{x}] {row_list[x]['날짜']} | {row_list[x]['식당명'] if row_list[x]['식당명'] else '미입력'} - {row_list[x]['상태']}"
    )
    
    if idx != st.session_state.selected_index:
        st.session_state.selected_index = idx
        st.rerun()

    row = row_list[idx]
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
            u_name = st.text_input("식당명", value="" if is_pending else row["식당명"])
        with f2:
            meal_opts = ["조식", "중식", "석식"]
            u_meal = st.selectbox("시간대", meal_opts, index=1 if is_pending else meal_opts.index(row["시간대"]) if row["시간대"] in meal_opts else 1)
            u_price = st.text_input("금액", value="" if is_pending else format_price(row["금액"]))
        u_note = st.text_input("비고", value="" if is_pending else row["비고"])
        
        if st.button("💾 이 항목 저장", use_container_width=True):
            row_list[idx].update({
                "날짜": u_date.strftime('%y-%m-%d'), "식당명": u_name, "시간대": u_meal, 
                "금액": format_price(u_price), "비고": u_note, "상태": "완료"
            })
            new_df = pd.DataFrame(row_list)
            conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=new_df[COLUMNS])
            
            # 저장 후 다음 대기 항목 찾기
            st.cache_data.clear()
            time.sleep(0.5)
            next_pending = idx
            for i in range(len(row_list)):
                if row_list[i]["상태"] == "대기":
                    next_pending = i
                    break
            st.session_state.selected_index = next_pending
            st.rerun()

# --- 3단계: 내역 확인 및 체크 삭제 ---
if not all_data.empty:
    st.divider()
    st.subheader("👀 3단계: 내역 확인 및 체크 삭제")
    
    edit_df = all_data.drop(columns=["사진데이터"], errors='ignore').copy()
    edit_df["삭제체크"] = False
    
    edited_data = st.data_editor(
        edit_df,
        use_container_width=True,
        column_config={"삭제체크": st.column_config.CheckboxColumn(label="삭제", default=False)},
        disabled=["날짜", "식당명", "시간대", "금액", "비고", "상태"],
        key="editor_v3"
    )
    
    checked_indices = edited_data[edited_data["삭제체크"] == True].index.tolist()
    
    if checked_indices:
        if st.button(f"🗑️ {len(checked_indices)}개 항목 일괄 삭제", type="primary", use_container_width=True):
            remaining_df = all_data.drop(all_data.index[checked_indices]).reset_index(drop=True)
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
    pdf_fn = f"{datetime.now().month}월 영수증_한정민.pdf"
    # (create_photo_pdf 함수 생략 - 이전 버전과 동일)
