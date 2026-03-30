import streamlit as st
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="영수증 관리 시스템", layout="centered")

# 세션 초기화
if 'user_info' not in st.session_state:
    st.session_state.user_info = None

st.title("💳 법인카드 로그인")

# GSheets 연결 및 데이터 로드 (중략 - 이전 코드와 동일)
conn = st.connection("gsheets", type=GSheetsConnection)
df = conn.read(spreadsheet="URL", worksheet="Staff", ttl=0)

name = st.text_input("성함")
pw = st.text_input("비밀번호", type="password")

if st.button("로그인"):
    user_match = df[(df["성명"] == name.strip()) & (df["비밀번호"] == str(pw).strip())]
    if not user_match.empty:
        st.session_state.user_info = user_match.iloc[0].to_dict()
        st.success(f"{name}님 환영합니다! 왼쪽 메뉴에서 '영수증 등록'을 선택하세요.")
    else:
        st.error("로그인 정보가 틀립니다.")
