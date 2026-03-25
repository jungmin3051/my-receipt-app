import streamlit as st
import pandas as pd
from datetime import datetime
import re
from PIL import Image
import pytesseract
import io

st.set_page_config(page_title="영수증 정리기", layout="centered")
st.title("📑 법인카드 영수증 자동 정리")

# 1. 사용자 정보 설정
user_name = st.sidebar.text_input("성명", "한정민")
report_month = st.sidebar.date_input("대상 월 선택")

# 2. 영수증 업로드
uploaded_files = st.file_uploader("영수증 사진을 올려주세요", accept_multiple_files=True)

if uploaded_files:
    if 'data_list' not in st.session_state:
        st.session_state.data_list = []
    
    # enumerate를 써서 파일마다 고유 번호(idx)를 부여합니다. (중복 방지)
    for idx, uploaded_file in enumerate(uploaded_files):
        img = Image.open(uploaded_file)
        try:
            raw_text = pytesseract.image_to_string(img, lang='kor+eng')
        except:
            raw_text = ""

        # --- [추출 로직 보강] ---
        # 날짜: '매출일', '일시' 단어 주변을 먼저 찾고 안되면 전체에서 찾음
        date_match = re.search(r'(?:매출일|일시|날짜|판매일)\s*[:]?\s*(\d{4}[-/.]\d{2}[-/.]\d{2})', raw_text)
        if not date_match:
             date_match = re.search(r'(\d{4}[-/.]\d{2}[-/.]\d{2})', raw_text)
        extracted_date = date_match.group(1).replace('.', '-').replace('/', '-') if date_match else datetime.now().strftime('%Y-%m-%d')
        
        # 금액: '합계', '금액' 등 키워드 뒤에 오는 숫자 3자리 이상 추출
        price_match = re.search(r'(?:합계|받을|결제|금\s*액)\s*[:]?\s*([\d,]{3,})', raw_text.replace(' ', '').replace(':', ''))
        extracted_price = int(price_match.group(1).replace(',', '')) if price_match else 0
        
        # 식당명: [매장명] 혹은 첫 줄의 상호명 추출 (특수문자 제외)
        store_match = re.search(r'(?:매장명|가맹점|상\s*호)\s*[:]?\s*([^\n\d\(\)/]+)', raw_text)
        extracted_store = store_match.group(1).strip() if store_match else "직접 입력해주세요"
        # --- [추출 로직 끝] ---

        # key 값에 idx를 붙여서 중복 에러를 방지합니다.
        with st.form(key=f"form_{uploaded_file.name}_{idx}"):
            st.image(img, width=400)
            st.info("💡 틀린 정보는 수정 후 '확정'을 눌러주세요.")
            
            c1, c2, c3 = st.columns(3)
            with c1: date = st.text_input("날짜", extracted_date, key=f"d_{idx}")
            with c2: store = st.text_input("식당/매장명", extracted_store, key=f"s_{idx}")
            with c3: meal = st.selectbox("구분", ["조식", "중식", "석식"], key=f"m_{idx}")
            
            p1, p2 = st.columns(2)
            with p1: price = st.number_input("금액(원)", value=extracted_price, key=f"p_{idx}")
            with p2: remark = st.text_input("비고", "", key=f"r_{idx}")
            
            if st.form_submit_button("이 영수증 확정"):
                st.session_state.data_list.append([date, store, meal, price, remark])
                st.success(f"{store} 추가됨!")

    if st.session_state.data_list:
        df = pd.DataFrame(st.session_state.data_list, columns=["일자", "내용", "구분", "금액", "비고"])
        st.table(df)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, startrow=4, sheet_name='내역서')
        
        st.download_button(label="📈 엑셀 파일 다운로드", data=output.getvalue(), file_name=f"내역서_{user_name}.xlsx")
