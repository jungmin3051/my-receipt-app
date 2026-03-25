import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
# (중략: 기존 임포트 로직 동일)

conn = st.connection("gsheets", type=GSheetsConnection)

# 1. 명부(Staff)와 내역(Sheet1) 데이터 읽기
staff_df = conn.read(worksheet="Staff")
receipt_df = conn.read(worksheet="Sheet1")

st.title("📑 법인카드 영수증 자동 정리")

# --- [신규 기능] 직원 자율 등록 섹션 ---
with st.sidebar.expander("👤 신규 직원 등록 (처음 한 번만)"):
    new_name = st.text_input("성함")
    new_rank = st.text_input("직책 (예: 선임)")
    new_card = st.text_input("법인카드번호")
    if st.button("직원 명부에 등록"):
        if new_name and new_rank and new_card:
            new_staff = pd.DataFrame([{"성명": new_name, "직책": new_rank, "법인카드번호": new_card}])
            updated_staff = pd.concat([staff_df, new_staff], ignore_index=True)
            conn.update(worksheet="Staff", data=updated_staff)
            st.success(f"{new_name}님 등록 완료! 앱을 새로고침 해주세요.")
        else:
            st.warning("모든 정보를 입력해주세요.")

# --- 메인 기능: 이름 선택 및 영수증 처리 ---
user_list = ["선택하세요"] + staff_df["성명"].tolist()
selected_user = st.sidebar.selectbox("성함을 선택하세요", user_list)

if selected_user != "선택하세요":
    user_info = staff_df[staff_df["성명"] == selected_user].iloc[0]
    st.sidebar.write(f"**직책:** {user_info['직책']}")
    st.sidebar.write(f"**카드:** {user_info['법인카드번호']}")

# ... (이후 영수증 업로드 및 확정 시 Sheet1에 저장하는 로직 동일)
