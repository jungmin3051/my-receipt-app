import streamlit as st
import pandas as pd
from datetime import datetime
import re
from PIL import Image
import pytesseract
import io

st.set_page_config(page_title="영수증 정리기", layout="centered")

st.title("📑 법인카드 영수증 자동 정리")
st.write("영수증을 찍으면 날짜, 식당명, 금액, 식사구분을 자동으로 분석합니다.")

# 1. 사용자 정보 설정
with st.expander("👤 사용자 및 월 설정", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        user_name = st.text_input("성명", "한정민")
    with col2:
        report_month = st.date_input("대상 월 선택")

# 2. 영수증 업로드
uploaded_files = st.file_uploader("영수증 사진을 올려주세요", accept_multiple_files=True)

if uploaded_files:
    data_list = []
    
    for uploaded_file in uploaded_files:
        img = Image.open(uploaded_file)
        
        # OCR 실행 (한국어+영어)
        try:
            raw_text = pytesseract.image_to_string(img, lang='kor+eng')
        except:
            raw_text = ""

        # --- [지능형 추출 로직 시작] ---
        
        # 1. 날짜 추출 (YYYY-MM-DD 또는 YYYY/MM/DD)
        date_match = re.search(r'(\d{4}[-/.]\d{2}[-/.]\d{2})', raw_text)
        extracted_date = date_match.group(1).replace('.', '-').replace('/', '-') if date_match else datetime.now().strftime('%Y-%m-%d')
        
        # 2. 시간 추출 및 식사 구분 (HH:MM:SS)
        time_match = re.search(r'(\d{2}:\d{2}:\d{2})', raw_text)
        meal_type = "중식" # 기본값
        extracted_time = "12:00:00"
        
        if time_match:
            extracted_time = time_match.group(1)
            hour = int(extracted_time.split(':')[0])
            if 3 <= hour <= 10: meal_type = "조식"
            elif 10 < hour <= 15: meal_type = "중식"
            else: meal_type = "석식"
            
        # 3. 금액 추출 (합계, 금액, 가액 등 키워드 뒤의 숫자)
        price_match = re.search(r'(?:합계|금액|받을금액|결제금액)\s*[:]?\s*([\d,]+)', raw_text.replace(' ', ''))
        extracted_price = int(price_match.group(1).replace(',', '')) if price_match else 0
        
        # 4. 식당명 추출 (가장 윗줄 혹은 [매장명] 키워드)
        store_match = re.search(r'(?:매장명|가맹점명|상호)\s*[:]?\s*([^\n]+)', raw_text)
        extracted_store = store_match.group(1).strip() if store_match else "식당이름"

        # --- [지능형 추출 로직 끝] ---

        with st.form(key=f"form_{uploaded_file.name}"):
            st.image(img, width=400)
            st.info("💡 영수증에서 읽어온 정보입니다. 틀린 부분만 고쳐주세요!")
            
            c1, c2, c3 = st.columns(3)
            with c1: date = st.text_input("날짜", extracted_date, key=f"d_{uploaded_file.name}")
            with c2: store = st.text_input("식당/매장명", extracted_store, key=f"s_{uploaded_file.name}")
            with c3: meal = st.selectbox("구분", ["조식", "중식", "석식"], index=["조식", "중식", "석식"].index(meal_type), key=f"m_{uploaded_file.name}")
            
            p1, p2 = st.columns(2)
            with p1: price = st.number_input("금액(원)", value=extracted_price, key=f"p_{uploaded_file.name}")
            with p2: remark = st.text_input("비고(달러 등)", "", key=f"r_{uploaded_file.name}")
            
            submit = st.form_submit_button("확정 및 목록 추가")
            
            if submit:
                data_list.append([date, store, meal, price, remark])
                st.success(f"{store} 내역이 추가되었습니다!")

    if data_list:
        df = pd.DataFrame(data_list, columns=["일자", "내용", "구분", "금액", "비고"])
        st.write("### 📊 현재까지 정리된 내역")
        st.table(df)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, startrow=4, sheet_name='내역서')
            
        st.download_button(
            label="📈 엑셀 파일 다운로드",
            data=output.getvalue(),
            file_name=f"사용내역서_{user_name}.xlsx"
        )
