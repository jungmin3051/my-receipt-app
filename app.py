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

# 깔끔하게 정리된 시간대 정의
MEAL_OPTIONS = ["조식", "중식", "석식", "회식", "결제취소"]
MEAL_ORDER = {"조식": 1, "중식": 2, "석식": 3, "회식": 4, "결제취소": 5}

def get_meal_priority(meal_name):
    return MEAL_ORDER.get(meal_name, 5)

def clean_meal_name(meal_name):
    if "중식" in meal_name: return "중식"
    if "석식" in meal_name: return "석식"
    return meal_name

def format_price(val):
    try:
        if not val or str(val).lower() in ['nan', '0', '']: return ""
        clean_val = str(val).split('.')[0].replace(',', '').replace('원', '')
        if clean_val.startswith('-') and clean_val[1:].isdigit():
            return f"-{int(clean_val[1:]):,}"
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
    image.thumbnail((550, 550)) 
    quality = 80
    while True:
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG", quality=quality)
        b64_string = base64.b64encode(buffered.getvalue()).decode()
        if len(b64_string) < 40000 or quality <= 10:
            return b64_string
        quality -= 5

def create_photo_pdf(df):
    pdf = FPDF()
    font_path = "NanumGothic.ttf"
    if os.path.exists(font_path):
        pdf.add_font('Nanum', '', font_path, uni=True)
        pdf.set_font('Nanum', size=9) 
    else:
        pdf.set_font("Arial", size=9)

    # 📌 핵심 수정: 결제취소가 아니고 + '사진데이터'가 실제로 존재하는 행만 쏙 골라냅니다.
    valid_photos_df = df[(df["시간대"] != "결제취소") & (df["사진데이터"] != "") & (df["사진데이터"].notna())].reset_index(drop=True)

    # 📌 사진이 있는 건들만 정렬된 순서대로 땡겨서 4개씩 배치합니다.
    for i, row in valid_photos_df.iterrows():
        if i % 4 == 0: 
            pdf.add_page()
            
        try:
            img_data = base64.b64decode(row["사진데이터"])
            temp_img = io.BytesIO(img_data)
            
            # i가 사진 있는 건들로만 0, 1, 2, 3... 순서대로 가기 때문에 빈칸 없이 채워집니다.
            x, y = (10 if i % 2 == 0 else 105), (10 if i % 4 < 2 else 145)
            pdf.image(temp_img, x=x, y=y, w=90, h=120)
            
            pdf.set_xy(x, y + 122)
            p_val = f"{row['금액']}원" if "원" not in str(row['금액']) else row['금액']
            display_meal = clean_meal_name(row['시간대'])
            info_text = f"{row['날짜']} / {row['식당명']} / {display_meal} / {p_val}"
            pdf.cell(90, 10, info_text, ln=0, align='C')
        except: 
            continue
            
    return bytes(pdf.output())

# 1. 데이터 로드
COLUMNS = ["날짜", "식당명", "시간대", "금액", "비고", "사진데이터", "상태"]
try:
    all_data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0).astype(str)
    all_data = all_data.fillna("")
    all_data = all_data[all_data["날짜"] != "nan"].reset_index(drop=True)
    
    if not all_data.empty:
        all_data['날짜'] = all_data['날짜'].apply(fix_date)
        all_data['금액'] = all_data['금액'].apply(format_price)
        # 최초 로드 시 정렬이 깨지지 않도록 유지 (순서 조정한 내역이 시트 순서 그대로 유지됨)
except:
    all_data = pd.DataFrame(columns=COLUMNS)

st.title("📑 법카 영수증 관리")

# --- 1단계 : 사진 업로드 ---
with st.expander("📸 1단계 : 사진 업로드", expanded=True):
    files = st.file_uploader("사진 선택", accept_multiple_files=True)
    if files and st.button("🚀 사진 전송"):
        new_list = []
        now = datetime.now()
        progress_text = st.empty()
        
        for i, f in enumerate(files):
            try:
                progress_text.text(f"사진 초경량 압축 중... ({i+1}/{len(files)})")
                img_b64 = img_to_base64(Image.open(f))
                new_list.append({
                    "날짜": now.strftime('%y-%m-%d'), "식당명": "", "시간대": "중식", 
                    "금액": "", "비고": "", "사진데이터": img_b64, "상태": "대기"
                })
            except Exception as e: st.error(f"오류: {e}")
        
        if new_list:
            progress_text.text("구글 시트에 안전하게 병합 중...")
            updated = pd.concat([all_data, pd.DataFrame(new_list)], ignore_index=True)
            # 신규 업로드 시 같은 날짜 그리 모이도록 기본 정렬 후 저장
            updated['temp_p'] = updated['시간대'].apply(get_meal_priority)
            updated = updated.sort_values(by=["날짜", "temp_p"], ascending=[True, True]).reset_index(drop=True).drop(columns=['temp_p'])
            try:
                conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated[COLUMNS])
                st.cache_data.clear()
                st.success("용량 다이어트 성공! 안전하게 저장되었습니다.")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"저장 실패: {e}")

# --- 2단계: 개별 내용 수정 ---
st.divider()
st.subheader("💻 2단계 : 개별 내용 수정")

cc1, cc2 = st.columns([6, 1])
with cc2:
    if st.button("➕ 취소건 추가", use_container_width=True):
        now_date = datetime.now().strftime('%y-%m-%d')
        cancel_row = pd.DataFrame([{
            "날짜": now_date, "식당명": "", "시간대": "결제취소", 
            "금액": "", "비고": "오결제", "사진데이터": "", "상태": "대기"
        }])
        updated = pd.concat([all_data, cancel_row], ignore_index=True)
        conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated[COLUMNS])
        st.cache_data.clear()
        st.session_state.selected_index = len(updated) - 1
        st.rerun()

if not all_data.empty:
    row_list = all_data.to_dict('records')
    
    if "selected_index" not in st.session_state:
        st.session_state.selected_index = 0
        for i, r in enumerate(row_list):
            if r["상태"] == "대기":
                st.session_state.selected_index = i
                break
                
    curr_idx = min(st.session_state.selected_index, len(row_list)-1)
    
    def make_label(x):
        r = row_list[x]
        flag = "❌ [취소] " if r['시간대'] == "결제취소" else f"[{x+1}] "
        return f"{flag}{r['날짜']} | {r['식당명'] if r['식당명'] else '새 영수증 (내용 입력 필요)'}"

    idx = st.selectbox("항목 선택", range(len(row_list)), index=curr_idx, format_func=make_label)
    
    if idx != st.session_state.selected_index:
        st.session_state.selected_index = idx
        st.rerun()

    row = row_list[idx]
    is_pending = (row["상태"] == "대기")
    c1, c2 = st.columns([1, 2])
    
    with c1: 
        if row["사진데이터"]: 
            st.image(base64.b64decode(row["사진데이터"]), width=300)
        else:
            st.info("📷 이 항목은 사진이 없는 건입니다.")
            
    with c2:
        f1, f2 = st.columns(2)
        with f1:
            try: d_val = datetime.strptime(row["날짜"], '%y-%m-%d')
            except: d_val = datetime.now()
            u_date = st.date_input("1. 날짜", d_val)
        with f2:
            u_meal = st.selectbox("2. 시간대", MEAL_OPTIONS, index=MEAL_OPTIONS.index(row["시간대"]) if row["시간대"] in MEAL_OPTIONS else 1)
            
        f3, f4 = st.columns(2)
        with f3:
            u_name = st.text_input("3. 식당명", value="" if is_pending and row["식당명"] == "" else row["식당명"])
        with f4:
            u_price = st.text_input("4. 금액", value="" if is_pending and row["금액"] == "" else row["금액"])
            
        default_note = "오결제" if u_meal == "결제취소" else row["비고"]
        u_note = st.text_input("5. 비고", value=default_note)
        
        if st.button("💾 이 항목 저장", use_container_width=True):
            with st.spinner("저장 중..."):
                row_list[idx].update({
                    "날짜": u_date.strftime('%y-%m-%d'), 
                    "식당명": u_name, 
                    "시간대": u_meal,
                    "금액": format_price(u_price), 
                    "비고": u_note, 
                    "상태": "완료"
                })
                conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=pd.DataFrame(row_list)[COLUMNS])
                st.cache_data.clear()
                for i in range(len(row_list)):
                    if row_list[i]["상태"] == "대기":
                        st.session_state.selected_index = i
                        break
                time.sleep(0.5)
                st.rerun()
else:
    st.info("등록된 영수증이 없습니다.")

# --- 3단계: 내역 확인 및 순서 변경 ---
if not all_data.empty:
    st.divider()
    st.subheader("👀 3단계 : 내역 확인 및 순서 변경")
    st.caption("💡 같은 날짜 내에서 순서를 바꾸려면 표의 [삭제체크] 칸에 체크(V)를 한 후, [🔼 위로 이동] 또는 [🔽 아래로 이동] 버튼을 누르세요.")

    # 1. 표 미리 정의 (사용자가 체크박스 체크한 데이터를 받기 위함)
    SHOW_COLUMNS = ["날짜", "식당명", "시간대", "금액", "비고", "상태", "삭제체크"]
    edit_df = all_data.copy()
    edit_df["삭제체크"] = False
    edit_df = edit_df[SHOW_COLUMNS]
    edit_df.index = edit_df.index + 1 
    
    # 표 렌더링 및 편집 데이터 받아오기
    edited_data = st.data_editor(
        edit_df, 
        use_container_width=True, 
        disabled=["날짜", "식당명", "시간대", "금액", "비고", "상태"]
    )

    # 2. [삭제체크]에 체크된 행의 인덱스 번호 찾기
    checked_indices = edited_data[edited_data["삭제체크"] == True].index.tolist()
    
    # 이동 버튼 배치
    b1, b2, b_msg = st.columns([1, 1, 5])
    
    # 딱 1개 항목만 체크했을 때 순서 이동 기능 작동
    if len(checked_indices) == 1:
        # 표 index는 1부터 시작하므로 실제 데이터(all_data) 인덱스는 -1 해줍니다.
        target_idx = checked_indices[0] - 1 
        
        with b1:
            if st.button("🔼 위로 이동", use_container_width=True) and target_idx > 0:
                if all_data.loc[target_idx, "날짜"] == all_data.loc[target_idx - 1, "날짜"]:
                    all_data.iloc[target_idx], all_data.iloc[target_idx - 1] = all_data.iloc[target_idx - 1].copy(), all_data.iloc[target_idx].copy()
                    conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=all_data[COLUMNS])
                    st.cache_data.clear()
                    st.success("위로 이동 완료!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.warning("동일한 날짜 내에서만 순서를 변경할 수 있습니다.")
                    
        with b2:
            if st.button("🔽 아래로 이동", use_container_width=True) and target_idx < len(all_data) - 1:
                if all_data.loc[target_idx, "날짜"] == all_data.loc[target_idx + 1, "날짜"]:
                    all_data.iloc[target_idx], all_data.iloc[target_idx + 1] = all_data.iloc[target_idx + 1].copy(), all_data.iloc[target_idx].copy()
                    conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=all_data[COLUMNS])
                    st.cache_data.clear()
                    st.success("아래로 이동 완료!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.warning("동일한 날짜 내에서만 순서를 변경할 수 있습니다.")
                    
    elif len(checked_indices) > 1:
        with b1: st.button("🔼 위로 이동", disabled=True, use_container_width=True)
        with b2: st.button("🔽 아래로 이동", disabled=True, use_container_width=True)
        with b_msg: st.warning("⚠️ 순서를 바꿀 때는 하나의 항목만 체크해 주세요! (여러 개 체크 시 이동 불가)")
    else:
        # 아무것도 체크하지 않았을 때 버튼 비활성화 및 안내
        with b1: st.button("🔼 위로 이동", disabled=True, use_container_width=True)
        with b2: st.button("🔽 아래로 이동", disabled=True, use_container_width=True)
        with b_msg: st.info("👈 순서를 바꾸거나 삭제하려면 원하는 항목의 [삭제체크] 칸을 선택해 주세요!")

    # 통계 및 계산 로직 (기존과 동일)
    done_items = all_data[all_data["상태"] == "완료"].copy()
    
    def to_int(val):
        try: return int(str(val).replace(',', '').replace('원', '').strip())
        except: return 0

    done_items['int_amount'] = done_items['금액'].apply(to_int)
    total_sum = done_items['int_amount'].sum()
    remaining_amount = 500000 - total_sum
    remain_color = "#ff4b4b" if remaining_amount < 0 else "#1f77b4"

    def get_day_group(date_str):
        try:
            day = int(str(date_str).split('-')[-1])
            if day <= 10: return "1~10일"
            elif day <= 20: return "11~20일"
            else: return "21~말일"
        except: return "기타"

    normal_meals = done_items[~done_items["시간대"].isin(["회식"])].copy()
    normal_meals['구간'] = normal_meals['날짜'].apply(get_day_group)
    periodic_sum = normal_meals.groupby('구간')['int_amount'].sum().to_dict()

    dinner_items = done_items[done_items["시간대"] == "회식"].copy()
    dinner_usage = dinner_items['int_amount'].sum()
    dinner_diff = 100000 - dinner_usage
    dinner_color = "#ff4b4b" if dinner_diff < 0 else "#1f77b4"

    summary_html = f"""
    <div style='background-color:#f8f9fb;padding:12px;border-radius:10px;border:1px solid #e6e9ef;margin:10px 0;'>
        <div style='display:flex;justify-content:space-around;align-items:center;'> 
            <div style='text-align:center;'><span style='font-size:14px;color:#666;'>💳 총 사용 금액 (회식/취소 반영)</span><br><span style='font-size:22px;font-weight:bold;'>{total_sum:,} 원</span></div> 
            <div style='width:1px;height:35px;background-color:#e6e9ef;'></div> 
            <div style='text-align:center;'><span style='font-size:14px;color:#666;'>💰 전체 남은 한도</span><br><span style='font-size:22px;color:{remain_color};font-weight:bold;'>{remaining_amount:,} 원</span></div> 
        </div>
    </div>
    """
    st.markdown(summary_html, unsafe_allow_html=True)

    table_html = "<table style='width:100%;border-collapse:collapse;text-align:center;border:1px solid #e6e9ef;font-size:14px;'>"
    table_html += "<thead style='background-color:#f1f3f6;'><tr><th style='padding:10px;border:1px solid #e6e9ef;'>구간</th><th style='padding:10px;border:1px solid #e6e9ef;'>사용 금액</th><th style='padding:10px;border:1px solid #e6e9ef;'>구간 한도 잔액</th></tr></thead><tbody>"
    
    for p in ["11~20일", "21~말일", "1~10일"]:
        usage = periodic_sum.get(p, 0)
        diff = 130000 - usage
        d_color = "#ff4b4b" if diff < 0 else "#1f77b4"
        table_html += f"<tr><td style='padding:10px;border:1px solid #eee;'>{p}</td><td style='padding:10px;border:1px solid #eee;'>₩ {usage:,}</td><td style='padding:10px;border:1px solid #eee;color:{d_color};font-weight:bold;'>₩ {diff:,}</td></tr>"
    
    table_html += f"<tr><td style='padding:10px;border:1px solid #eee;'>회식</td><td style='padding:10px;border:1px solid #eee;'>₩ {dinner_usage:,}</td><td style='padding:10px;border:1px solid #eee;color:{dinner_color};font-weight:bold;'>₩ {dinner_diff:,}</td></tr>"
    table_html += "</tbody></table>"
    st.markdown(table_html, unsafe_allow_html=True)

    # 삭제용 버튼 로직 (체크가 여러 개 되어 있어도 한 번에 삭제 가능)
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
        pdf_fn = f"{datetime.now().month}월 영수증_한정민.pdf"
        st.download_button("📄 영수증 PDF 다운로드", create_photo_pdf(done_df), pdf_fn, "application/pdf", use_container_width=True)
