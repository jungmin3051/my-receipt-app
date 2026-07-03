import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import io
import requests
from fpdf import FPDF
import time
import os
import json

# 0. 기본 설정
st.set_page_config(page_title="법카 영수증 관리", layout="wide")
SHEET_URL = "https://docs.google.com/spreadsheets/d/1x419Jb6laxcObm4z2nFU_W65Cx-4AxmAjwmE8ouFmjk/edit?usp=sharing"
DRIVE_FOLDER_ID = "1BlX3KIH7Ygu8zAbDLRJBbxDzMa7AE92f" 

conn = st.connection("gsheets", type=GSheetsConnection)

# 구글 서비스 계정 자격증명 정보 안전하게 파싱하는 함수
def get_google_credentials():
    try:
        # Streamlit Secrets에서 connections.gsheets 섹션을 가져옵니다.
        secret_data = st.secrets["connections"]["gsheets"]
        
        # 서비스 계정 JSON 포맷에 맞게 딕셔너리 재구성
        creds_dict = {
            "type": secret_data.get("type", "service_account"),
            "project_id": secret_data.get("project_id"),
            "private_key_id": secret_data.get("private_key_id"),
            "private_key": secret_data.get("private_key").replace("\\n", "\n") if secret_data.get("private_key") else None,
            "client_email": secret_data.get("client_email"),
            "client_id": secret_data.get("client_id"),
            "auth_uri": secret_data.get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
            "token_uri": secret_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            "auth_provider_x509_cert_url": secret_data.get("auth_provider_x509_cert_url", "https://www.googleapis.com/oauth2/v1/certs"),
            "client_x509_cert_url": secret_data.get("client_x509_cert_url")
        }
        return creds_dict
    except Exception as e:
        st.error(f"Secrets 파일에서 인증 정보를 읽어오는데 실패했습니다: {e}")
        return None

# OAuth2 Access Token 동적 발급 함수
def get_access_token():
    creds = get_google_credentials()
    if not creds or not creds["client_email"] or not creds["private_key"]:
        return None
    
    try:
        import jwt
        now = int(time.time())
        # 구글 드라이브와 시트 권한 스코프 선언
        payload = {
            "iss": creds["client_email"],
            "scope": "https://www.googleapis.com/auth/spreadsheets https://www.googleapis.com/auth/drive.file",
            "aud": creds["token_uri"],
            "exp": now + 3600,
            "iat": now
        }
        # JWT 생성
        signed_jwt = jwt.encode(payload, creds["private_key"], algorithm="RS256")
        
        # 토큰 요청
        r = requests.post(creds["token_uri"], data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": signed_jwt
        })
        if r.status_code == 200:
            return r.json().get("access_token")
    except ImportError:
        # PyJWT 라이브러리가 없는 경우 간이 안내
        st.error("🔒 'PyJWT'와 'cryptography' 라이브러리가 필요합니다. 'pip install PyJWT cryptography'를 실행하거나 requirements.txt에 추가해 주세요.")
    except Exception as e:
        st.error(f"토큰 발급 중 오류 발생: {e}")
    return None

MEAL_OPTIONS = ["조식", "중식", "석식", "회식", "결제취소"]
MEAL_ORDER = {"조식": 1, "중식": 2, "석식": 3, "회식": 4, "결제취소": 5}
COLUMNS = ["날짜", "식당명", "시간대", "금액", "비고", "사진데이터", "상태"]

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

# 구글 드라이브 파일 업로드 함수
def upload_to_drive(file_bytes, filename, token):
    try:
        headers = {"Authorization": f"Bearer {token}"}
        metadata = {
            "name": filename,
            "parents": [DRIVE_FOLDER_ID]
        }
        files = {
            'data': ('metadata', json.dumps(metadata), 'application/json; charset=UTF-8'),
            'file': ('image/jpeg', file_bytes, 'image/jpeg')
        }
        
        r = requests.post(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
            headers=headers, files=files
        )
        if r.status_code == 200:
            file_id = r.json().get("id")
            return f"https://drive.google.com/uc?export=view&id={file_id}"
    except Exception as e:
        st.error(f"구글 드라이브 업로드 에러: {e}")
    return ""

# 구글 드라이브 파일 다운로드 함수 (PDF 빌드용)
def download_image_bytes(url, token):
    try:
        if not url or "drive.google.com" not in url:
            return None
        headers = {"Authorization": f"Bearer {token}"}
        file_id = url.split("id=")[-1]
        download_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
        res = requests.get(download_url, headers=headers)
        if res.status_code == 200:
            return res.content
    except:
        pass
    return None

def create_photo_pdf(df, token):
    pdf = FPDF()
    font_path = "NanumGothic.ttf"
    if os.path.exists(font_path):
        pdf.add_font('Nanum', '', font_path, uni=True)
        pdf.set_font('Nanum', size=9) 
    else:
        pdf.set_font("Arial", size=9)

    valid_photos_df = df[(df["시간대"] != "결제취소") & (df["사진데이터"] != "") & (df["사진데이터"].notna()) & (df["사진데이터"].str.contains("drive.google", na=False))].reset_index(drop=True)

    for i, row in valid_photos_df.iterrows():
        if i % 4 == 0: pdf.add_page()
        img_bytes = download_image_bytes(row["사진데이터"], token)
        if img_bytes:
            try:
                temp_img = io.BytesIO(img_bytes)
                x, y = (10 if i % 2 == 0 else 105), (10 if i % 4 < 2 else 145)
                pdf.image(temp_img, x=x, y=y, w=90, h=120)
                
                pdf.set_xy(x, y + 122)
                p_val = f"{row['금액']}원" if "원" not in str(row['금액']) else row['금액']
                display_meal = clean_meal_name(row['시간대'])
                info_text = f"{row['날짜']} / {row['식당명']} / {display_meal} / {p_val}"
                pdf.cell(90, 10, info_text, ln=0, align='C')
            except: continue
    return bytes(pdf.output())

# 1. 데이터 로드
try:
    all_data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0).astype(str)
    all_data = all_data.fillna("")
    if all_data.empty or not all(col in all_data.columns for col in ["날짜", "상태"]):
        all_data = pd.DataFrame(columns=COLUMNS)
    else:
        all_data = all_data[all_data["날짜"] != "nan"].reset_index(drop=True)
        if not all_data.empty:
            all_data['날짜'] = all_data['날짜'].apply(fix_date)
            all_data['금액'] = all_data['금액'].apply(format_price)
except:
    all_data = pd.DataFrame(columns=COLUMNS)

st.title("📑 법카 영수증 관리 (드라이브 고화질 정렬형)")

# 토큰 미리 받아오기
token = get_access_token()

# --- 1단계 : 사진 업로드 ---
with st.expander("📸 1단계 : 사진 업로드", expanded=True):
    files = st.file_uploader("사진 선택", accept_multiple_files=True)
    if files and st.button("🚀 사진 전송"):
        if not token:
            st.error("🔑 구글 인증 토큰을 가져오지 못했습니다. `PyJWT` 설치 상태 및 Secrets 설정을 확인해 주세요.")
        else:
            new_list = []
            now = datetime.now()
            progress_text = st.empty()
            
            for i, f in enumerate(files):
                try:
                    progress_text.text(f"구글 드라이브에 원본 전송 중... ({i+1}/{len(files)})")
                    file_bytes = f.read()
                    filename = f"receipt_{now.strftime('%y%m%d')}_{i}_{f.name}"
                    
                    drive_url = upload_to_drive(file_bytes, filename, token)
                    
                    if drive_url:
                        new_list.append({
                            "날짜": now.strftime('%y-%m-%d'), "식당명": "", "시간대": "중식", 
                            "금액": "", "비고": "", "사진데이터": drive_url, "상태": "대기"
                        })
                    else:
                        st.error(f"{f.name} 업로드에 실패했습니다. 드라이브 폴더 공유 권한(편집자)을 재확인하세요.")
                except Exception as e: 
                    st.error(f"오류: {e}")
            
            if new_list:
                progress_text.text("구글 시트에 내역 매칭 중...")
                updated = pd.concat([all_data, pd.DataFrame(new_list)], ignore_index=True)
                updated['temp_p'] = updated['시간대'].apply(get_meal_priority)
                updated = updated.sort_values(by=["날짜", "temp_p"], ascending=[True, True]).reset_index(drop=True).drop(columns=['temp_p'])
                
                conn.update(spreadsheet=SHEET_URL, data=updated[COLUMNS])
                st.cache_data.clear()
                st.success("고화질 연동 완료! 시트가 가벼워졌습니다.")
                time.sleep(1)
                st.rerun()

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
        conn.update(spreadsheet=SHEET_URL, data=updated[COLUMNS])
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
        if row["사진데이터"] and "drive.google" in row["사진데이터"] and token: 
            img_b = download_image_bytes(row["사진데이터"], token)
            if img_b:
                st.image(img_b, width=350, caption="구글 드라이브 원본 고화질 프리뷰")
            else:
                st.warning("🔄 이미지를 불러오는 중이거나 드라이브 권한 확인이 필요합니다.")
        else:
            st.info("📷 사진이 없는 건이거나 기존 데이터입니다.")
            
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
            row_list[idx].update({
                "날짜": u_date.strftime('%y-%m-%d'), "식당명": u_name, "시간대": u_meal,
                "금액": format_price(u_price), "비고": u_note, "상태": "완료"
            })
            conn.update(spreadsheet=SHEET_URL, data=pd.DataFrame(row_list)[COLUMNS])
            st.cache_data.clear()
            for i in range(len(row_list)):
                if row_list[i]["상태"] == "대기":
                    st.session_state.selected_index = i
                    break
            time.sleep(0.5)
            st.rerun()

# --- 3단계: 순서 조정 및 당겨서 정렬 ---
if not all_data.empty:
    st.divider()
    st.subheader("👀 3단계 : 내역 확인 및 순서 변경")
    
    SHOW_COLUMNS = ["날짜", "식당명", "시간대", "금액", "비고", "상태", "삭제체크"]
    edit_df = all_data.copy()
    edit_df["삭제체크"] = False
    edit_df = edit_df[SHOW_COLUMNS]
    edit_df.index = edit_df.index + 1 
    
    edited_data = st.data_editor(edit_df, use_container_width=True, disabled=["날짜", "식당명", "시간대", "금액", "비고", "상태"])
    checked_indices = edited_data[edited_data["삭제체크"] == True].index.tolist()
    
    b1, b2, b_msg = st.columns([1, 1, 5])
    if len(checked_indices) == 1:
        target_idx = checked_indices[0] - 1 
        with b1:
            if st.button("🔼 위로 이동", use_container_width=True) and target_idx > 0:
                if all_data.loc[target_idx, "날짜"] == all_data.loc[target_idx - 1, "날짜"]:
                    all_data.iloc[target_idx], all_data.iloc[target_idx - 1] = all_data.iloc[target_idx - 1].copy(), all_data.iloc[target_idx].copy()
                    conn.update(spreadsheet=SHEET_URL, data=all_data[COLUMNS])
                    st.cache_data.clear()
                    st.rerun()
        with b2:
            if st.button("🔽 아래로 이동", use_container_width=True) and target_idx < len(all_data) - 1:
                if all_data.loc[target_idx, "날짜"] == all_data.loc[target_idx + 1, "날짜"]:
                    all_data.iloc[target_idx], all_data.iloc[target_idx + 1] = all_data.iloc[target_idx + 1].copy(), all_data.iloc[target_idx].copy()
                    conn.update(spreadsheet=SHEET_URL, data=all_data[COLUMNS])
                    st.cache_data.clear()
                    st.rerun()
    else:
        with b1: st.button("🔼 위로 이동", disabled=True, use_container_width=True)
        with b2: st.button("🔽 아래로 이동", disabled=True, use_container_width=True)

    done_items = all_data[all_data["상태"] == "완료"].copy()
    def to_int(val):
        try: return int(str(val).replace(',', '').replace('원', '').strip())
        except: return 0
    done_items['int_amount'] = done_items['금액'].apply(to_int)
    total_sum = done_items['int_amount'].sum()
    remaining_amount = 500000 - total_sum
    remain_color = "#ff4b4b" if remaining_amount < 0 else "#1f77b4"
    
    summary_html = f"""
    <div style='background-color:#f8f9fb;padding:12px;border-radius:10px;border:1px solid #e6e9ef;margin:10px 0; display:flex; justify-content:space-around;'>
        <div>💳 총 금액: <b>{total_sum:,} 원</b></div>
        <div>💰 잔여 한도: <b style='color:{remain_color};'>{remaining_amount:,} 원</b></div>
    </div>
    """
    st.markdown(summary_html, unsafe_allow_html=True)

    if checked_indices:
        if st.button(f"🗑️ {len(checked_indices)}개 항목 삭제하기", type="primary", use_container_width=True):
            remaining_df = all_data.drop(all_data.index[[i-1 for i in checked_indices]]).reset_index(drop=True)
            conn.update(spreadsheet=SHEET_URL, data=remaining_df[COLUMNS])
            st.cache_data.clear()
            st.rerun()

# --- 4단계: 다운로드 ---
st.divider()
done_df = all_data[all_data["상태"] == "완료"]
if not done_df.empty and token:
    st.subheader("📥 4단계 : 다운로드")
    d1, d2 = st.columns(2)
    with d1:
        ex_out = io.BytesIO()
        excel_df = done_df.drop(columns=["사진데이터", "상태"], errors='ignore').copy()
        excel_df.to_excel(ex_out, index=False)
        st.download_button("📊 엑셀 다운로드", ex_out.getvalue(), "Receipt_List.xlsx", use_container_width=True)
    with d2:
        pdf_fn = f"{datetime.now().month}월 영수증_한정민.pdf"
        st.download_button("📄 영수증 PDF 다운로드", create_photo_pdf(done_df, token), pdf_fn, "application/pdf", use_container_width=True)
