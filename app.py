import streamlit as st
import pandas as pd
from datetime import datetime
import io
from PIL import Image
import pytesseract

# Tesseract 설치 경로 설정 (일반적인 경로입니다)
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

st.set_page_config(page_title="영수증 정리기", layout="centered")

st.title("📑 법인카드 영수증 자동 정리")
st.write("영수증을 찍어 올리면 엑셀 양식에 맞춰 정리해 드립니다.")

# 1. 사용자 정보 및 날짜 설정
with st.expander("👤 사용자 및 월 설정", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        user_name = st.text_input("성명", "한정민")
        user_pos = st.text_input("직책", "선임")
    with col2:
        card_num = st.text_input("카드번호", "4265-8699-xxxx-xxxx")
        report_month = st.date_input("대상 월 선택")

# 2. 영수증 업로드
uploaded_files = st.file_uploader("영수증 사진들을 올려주세요", accept_multiple_files=True)

if uploaded_files:
    data_list = []
    
    for uploaded_file in uploaded_files:
        img = Image.open(uploaded_file)
        
        # 실제 글자 읽기 (OCR)
        # ⚠️ 처음엔 정확도가 낮을 수 있으니 수동 수정 기능을 넣었습니다.
        raw_text = pytesseract.image_to_string(img, lang='kor+eng')
        
        # 임시 데이터 (나중에 OCR 결과 분석 로직으로 대체)
        # 지금은 선임님이 규칙을 확인하실 수 있게 직접 입력창을 띄워드릴게요.
        with st.form(key=f"form_{uploaded_file.name}"):
            st.image(img, width=300)
            c1, c2, c3 = st.columns(3)
            with c1: date = st.date_input("날짜", datetime.now(), key=f"d_{uploaded_file.name}")
            with c2: store = st.text_input("식당명", "식당이름", key=f"s_{uploaded_file.name}")
            with c3: time_val = st.time_input("결제시간", datetime.now().time(), key=f"t_{uploaded_file.name}")
            
            p1, p2 = st.columns(2)
            with p1: price = st.number_input("금액", value=0, key=f"p_{uploaded_file.name}")
            with p2: is_dollar = st.checkbox("달러($) 결제인가요?", key=f"c_{uploaded_file.name}")
            
            submit = st.form_submit_button("이 영수증 확정")
            
            if submit:
                # D열 구분: 시간보고 조식/중식/석식 자동 분류
                hour = time_val.hour
                if hour < 10: meal_type = "조식"
                elif 11 <= hour <= 15: meal_type = "중식"
                else: meal_type = "석식"
                
                # E, F열 규칙: 달러면 비고란으로!
                amt_won = price if not is_dollar else ""
                amt_usd = f"{price}$" if is_dollar else ""
                
                data_list.append([date, store, meal_type, amt_won, amt_usd])
                st.success("추가되었습니다!")

    if data_list:
        df = pd.DataFrame(data_list, columns=["일자", "내용", "구분", "금액", "비고"])
        df = df.sort_values(by="일자") # 날짜순 정렬
        
        st.write("### 📊 정리된 내역")
        st.table(df)

        # 3. 엑셀 파일 생성
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # 선임님 양식처럼 5번째 줄부터 데이터 시작
            df.to_excel(writer, index=False, startrow=4, sheet_name='내역서')
            
            # 여기에 상단 성명, 직책 등을 채우는 로직을 추가할 수 있습니다.
            
        st.download_button(
            label="📈 엑셀 파일 다운로드",
            data=output.getvalue(),
            file_name=f"{report_month.strftime('%m')}월_사용내역서_{user_name}.xlsx"
        )
