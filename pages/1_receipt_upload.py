import streamlit as st
import pandas as pd
# OCR 및 업로드 관련 라이브러리 임포트 (중략)

st.set_page_config(page_title="영수증 등록", layout="wide")

# 🔒 로그인 체크 (가장 중요)
if 'user_info' not in st.session_state or st.session_state.user_info is None:
    st.warning("로그인이 필요합니다. 메인 페이지로 이동해 주세요.")
    st.stop() # 이후 코드 실행 방지

user = st.session_state.user_info
st.title(f"📸 {user['성명']}님의 영수증 등록")

# 여기에 영수증 업로드, OCR 분석, 시트 저장 로직만 집중해서 작성
# (이전에 드린 영수증 처리 코드를 이 파일에 넣으시면 됩니다.)
