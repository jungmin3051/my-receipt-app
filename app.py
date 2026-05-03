import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import io
import base64
from PIL import Image, ImageOps
from fpdf import FPDF
import time
import os

# 0. 기본 설정
st.set_page_config(page_title="법카 영수증 관리", layout="wide")
SHEET_URL = "https://docs.google.com/spreadsheets/d/1x419Jb6laxcObm4z2nFU_W65Cx-4AxmAjwmE8ouFmjk/edit?usp=sharing"
conn = st.connection("gsheets", type=GSheetsConnection)

# --- [중요] 함수들을 최상단으로 이동 (에러 방지) ---

MEAL_ORDER = {"조식": 1, "중식": 2, "중식2": 3, "석식": 4, "석식2": 5 , "회식": 6}

def get_meal_priority(meal_name):
    return MEAL_ORDER.get(meal_name, 6)

def clean_meal_name(meal_name):
    if "중식" in meal_name: return "중식"
    if "석식" in meal_name: return "석식"
    return meal_name

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
    image.thumbnail((1000, 1000)) 
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG", quality=60) 
    return base64.b64encode(buffered.getvalue()).decode()

def create_photo_pdf(df):
    pdf = FPDF()
    font_path = "NanumGothic.ttf"
    if os.path.exists(font_path):
        pdf.add_font('Nanum', '', font_path, uni=True)
        pdf.set_font('Nanum', size=9) 
    else:
        pdf.set_font("Arial", size=9)
    df['temp_p'] = df['시간대'].apply(get_meal_priority)
    df_sorted = df.sort_values(by=["날짜", "temp_p"]).reset_index(drop=True)
    for i, (_, row) in enumerate(df_sorted.iterrows()):
        if i % 4 == 0: pdf.add_page()
        try:
            img_data = base64.b64decode(row["사진데이터"])
            temp_img = io.BytesIO(img_data)
            x, y = (10 if i % 2 == 0 else 105), (10 if i % 4 < 2 else 145)
            pdf.image(temp_img, x=x, y=y, w=90, h=120)
            pdf.set_xy(x, y + 122)
            p_val = f"{row['금액']}원" if "원" not in str(row['금액']) else row['금액']
            display_meal = clean_meal_name(row['시간대'])
            info_text = f"{row['날짜']} / {row['식당명']} / {display_meal} / {p_val}"
            pdf.cell(90, 10, info_text, ln=0, align='C')
        except: continue
    return bytes(pdf.output())

# --- 1. 데이터 로드 ---
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

# --- 메인 헤더 ---
header_col1, header_col2 = st.columns([8, 2])
with header_col1:
    st.markdown("<h2 style='margin-top:0; font-size: 38px;'>📑 법카 영수증 관리</h2>", unsafe_allow_html=True)

with header_col2:
    st.write("") 
    if st.button("🔄 새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- 1단계 : 사진 업로드 ---
with st.expander("📸 1단계 : 사진 업로드", expanded=True):
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
    st.subheader("💻 2단계 : 개별 내용 수정")
    row_list = all_data.to_dict('records')
    if "selected_index" not in st.session_state:
        st.session_state.selected_index = 0
        for i, r in enumerate(row_list):
            if r["상태"] == "대기":
                st.session_state.selected_index = i
                break
    curr_idx = min(st.session_state.selected_index, len(row_list)-1)
    idx = st.selectbox("항목 선택", range(len(row_list)), index=curr_idx,
                       format_func=lambda x: f"[{x+1}] {row_list[x]['날짜']} | {row_list[x]['식당명']}")
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
            meal_opts = ["조식", "중식", "중식2", "석식", "석식2", "회식"]
            u_meal = st.selectbox("시간대", meal_opts, index=1 if is_pending else meal_opts.index(row["시간대"]) if row["시간대"] in meal_opts else 1)
            u_price = st.text_input("금액", value="" if is_pending else row["금액"])
        u_note = st.text_input("비고", value="" if is_pending else row["비고"])
        if st.button("💾 이 항목 저장", use_container_width=True):
            with st.spinner("저장 중..."):
                row_list[idx].update({"날짜": u_date.strftime('%y-%m-%d'), "식당명": u_name, "시간대": u_meal, "금액": format_price(u_price), "비고": u_note, "상태": "완료"})
                conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=pd.DataFrame(row_list)[COLUMNS])
                st.cache_data.clear()
                for i in range(len(row_list)):
                    if row_list[i]["상태"] == "대기":
                        st.session_state.selected_index = i
                        break
                time.sleep(0.5)
                st.rerun()

# --- 3단계: 내역 확인 및 삭제 ---
if not all_data.empty:
    st.divider()
    st.subheader("👀 3단계 : 내역 확인 및 삭제")
    
    edit_df = all_data.drop(columns=["사진데이터"], errors='ignore').copy()
    edit_df["삭제체크"] = False
    edit_df.index = edit_df.index + 1 
    edited_data = st.data_editor(edit_df, use_container_width=True, disabled=["날짜", "식당명", "시간대", "금액", "비고", "상태"])
    
    def parse_money(x):
        try: return int(str(x).replace(',', '').replace('원', ''))
        except: return 0

    done_items = all_data[all_data["상태"] == "완료"].copy()
    done_items['int_amount'] = done_items['금액'].apply(parse_money)
    
    dinner_items = done_items[done_items["시간대"] == "회식"].copy()
    dinner_usage = dinner_items['int_amount'].sum()
    dinner_diff = 100000 - dinner_usage
    dinner_color = "#ff4b4b" if dinner_diff < 0 else "#1f77b4"

    def get_day_group(date_str):
        try:
            day = int(str(date_str).split('-')[-1])
            if day <= 10: return "1~10일"
            elif day <= 20: return "11~20일"
            else: return "21~말일"
        except: return "기타"

    done_items['구간'] = done_items['날짜'].apply(get_day_group)
    periodic_sum = done_items.groupby('구간')['int_amount'].sum().to_dict()
    
    total_sum = done_items['int_amount'].sum()
    limit_amount = 500000
    remaining_amount = limit_amount - total_sum
    remain_color = "#ff4b4b" if remaining_amount < 0 else "#1f77b4"

    summary_html = f"<div style='background-color:#f8f9fb;padding:12px;border-radius:10px;border:1px solid #e6e9ef;margin:10px 0;'><div style='display:flex;justify-content:space-around;align-items:center;'> <div style='text-align:center;'><span style='font-size:14px;color:#666;'>💳 총 사용 금액</span><br><span style='font-size:22px;font-weight:bold;'>{total_sum:,} 원</span></div> <div style='width:1px;height:35px;background-color:#e6e9ef;'></div> <div style='text-align:center;'><span style='font-size:14px;color:#666;'>💰 총 남은 금액</span><br><span style='font-size:22px;color:{remain_color};font-weight:bold;'>{remaining_amount:,} 원</span></div> </div></div>"
    st.markdown(summary_html, unsafe_allow_html=True)

    table_html = "<table style='width:100%;border-collapse:collapse;text-align:center;border:1px solid #e6e9ef;font-size:14px;'>"
    table_html += "<thead style='background-color:#f1f3f6;'><tr><th style='padding:10px;border:1px solid #e6e9ef;'>구간</th><th style='padding:10px;border:1px solid #e6e9ef;'>사용 금액</th><th style='padding:10px;border:1px solid #e6e9ef;'>한도 대비 잔액</th></tr></thead><tbody>"
    
    custom_order = ["11~20일", "21~말일", "1~10일"]
    for p in custom_order:
        usage = periodic_sum.get(p, 0)
        diff = 130000 - usage
        d_color = "#ff4b4b" if diff < 0 else "#1f77b4"
        table_html += f"<tr><td style='padding:10px;border:1px solid #eee;background-color:#fff;'>{p}</td><td style='padding:10px;border:1px solid #eee;background-color:#fff;'>₩ {usage:,}</td><td style='padding:10px;border:1px solid #eee;background-color:#fff;color:{d_color};font-weight:bold;'>₩ {diff:,}</td></tr>"
    
    table_html += f"<tr><td style='padding:10px;border:1px solid #eee;background-color:#fff;'>회식</td><td style='padding:10px;border:1px solid #eee;background-color:#fff;'>₩ {dinner_usage:,}</td><td style='padding:10px;border:1px solid #eee;background-color:#fff;color:{dinner_color};font-weight:bold;'>₩ {dinner_diff:,}</td></tr>"
    table_html += "</tbody></table><div style='margin-bottom:20px;'></div>"
    st.markdown(table_html, unsafe_allow_html=True)

    checked_indices = edited_data[edited_data["삭제체크"] == True].index.tolist()
    if checked_indices:
        if st.button(f"🗑️ {len(checked_indices)}개 항목 삭제하기", type="primary", use_container_width=True):
            remaining_df = all_data.drop(all_data.index[[i-1 for i in checked_indices]]).reset_index(drop=True)
            conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=remaining_df[COLUMNS])
            st.cache_data.clear()
            st.rerun()

# --- 4단계: 다운로드 ---
st.divider()
done_df = all_data[all_data["상태"] == "완료"]
if not done_df.empty:
    st.subheader("📥 4단계 : 다운로드")
    d1, d2 = st.columns(2)
    with d1:
        ex_out = io.BytesIO()
        excel_df = done_df.drop(columns=["사진데이터", "상태"], errors='ignore').copy()
        excel_df["시간대"] = excel_df["시간대"].apply(clean_meal_name)
        excel_df.to_excel(ex_out, index=False)
        st.download_button("📊 엑셀 다운로드", ex_out.getvalue(), "Receipt_List.xlsx", use_container_width=True)
    with d2:
        pdf_fn = f"{datetime.now().month}월 개인법인카드 영수증_한정민.pdf"
        st.download_button("📄 영수증 PDF 다운로드", create_photo_pdf(done_df), pdf_fn, "application/pdf", use_container_width=True)
