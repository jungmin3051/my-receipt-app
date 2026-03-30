import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

# 0. 기본 설정
st.set_page_config(page_title="법인카드 관리 시스템", layout="centered")

# --- 1. 설정 (선임님 구글 시트 URL) ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1x419Jb6laxcObm4z2nFU_W65Cx-4AxmAjwmE8ouFmjk/edit?usp=sharing"

# --- 2. 서비스 연결 ---
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception as e:
    st.error(f"연결 오류: {e}")

# 세션 초기화
if 'user_info' not in st.session_state:
    st.session_state.user_info = None

st.title("💳 법인카드 시스템 로그인")

# --- 3. 로그인 로직 ---
if st.session_state.user_info is None:
    staff_df = conn.read(spreadsheet=SHEET_URL, worksheet="Staff", ttl=0)
    
    l_name = st.text_input("성함")
    l_pw = st.text_input("비밀번호 (숫자 4자리)", type="password")
    
    if st.button("로그인 하기"):
        # 데이터 정제 (공백 제거 및 문자열 변환)
        staff_df['성명'] = staff_df['성명'].astype(str).str.strip()
        staff_df['비밀번호'] = staff_df['비밀번호'].astype(str).str.strip()
        
        user_match = staff_df[(staff_df["성명"] == l_name.strip()) & (staff_df["비밀번호"] == str(l_pw).strip())]
        
        if not user_match.empty:
            st.session_state.user_info = user_match.iloc[0].to_dict()
            st.success(f"✅ {l_name}님 확인되었습니다!")
            st.info("왼쪽 사이드바에서 '1 receipt upload' 메뉴를 클릭해 영수증을 등록하세요.")
        else:
            st.error("정보가 일치하지 않습니다. 이름과 비밀번호를 확인하세요.")
else:
    st.success(f"현재 {st.session_state.user_info['성명']}님으로 로그인 되어 있습니다.")
    if st.button("로그아웃"):
        st.session_state.user_info = None
        st.rerun()
