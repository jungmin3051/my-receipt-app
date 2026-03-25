import streamlit as st
import pandas as pd
from datetime import datetime
import re
from PIL import Image
import pytesseract
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

st.set_page_config(page_title="영수증 정리기", layout="centered")
st.title("📑 법인카드 영수증 자동 정리")

# 1. 사용자 정보 설정
user_name = st.sidebar.text_input("성명", "한정민")
report_month = st.sidebar.date_input("대상 월 선택")

# 2. 영수증 업로드
uploaded_files = st.file_uploader("영수증 사진들을 올려주세요", accept_multiple_files=True)

if uploaded_files:
    if 'data_list' not in st.session_state:
        st.session_state.data_list = []
    
    # 폼 생성 및 데이터 수집
    for idx, uploaded_file in enumerate(uploaded_files):
        img = Image.open(uploaded_file)
        try:
            raw_text = pytesseract.image_to_string(img, lang='kor+eng')
        except:
            raw_text = ""

        # 추출 로직 (날짜, 금액, 식당명)
        date_match = re.search(r'(?:매출일|일시|날짜|판매일)\s*[:]?\s*(\d{4}[-/.]\d{2}[-/.]\d{2})', raw_text)
        if not date_match:
             date_match = re.search(r'(\d{4}[-/.]\d{2}[-/.]\d{2})', raw_text)
        extracted_date = date_match.group(1).replace('.', '-').replace('/', '-') if date_match else datetime.now().strftime('%Y-%m-%d')
        
        price_match = re.search(r'(?:합계|받을|결제|금\s*액)\s*[:]?\s*([\d,]{3,})', raw_text.replace(' ', '').replace(':', ''))
        extracted_price = int(price_match.group(1).replace(',', '')) if price_match else 0
        
        store_match = re.search(r'(?:매장명|가맹점|상\s*호)\s*[:]?\s*([^\n\d\(\)/]+)', raw_text)
        extracted_store = store_match.group(1).strip() if store_match else "직접 입력"

        with st.form(key=f"form_{uploaded_file.name}_{idx}"):
            st.image(img, width=300)
            c1, c2 = st.columns(2)
            with c1: date_val = st.text_input("날짜", extracted_date, key=f"d_{idx}")
            with c2: store_val = st.text_input("식당명", extracted_store, key=f"s_{idx}")
            
            if st.form_submit_button(f"{idx+1}번 영수증 확정"):
                # PDF 생성을 위해 이미지 객체도 함께 저장합니다.
                st.session_state.data_list.append({
                    "date": date_val,
                    "store": store_val,
                    "price": extracted_price,
                    "img": img
                })
                st.success(f"{store_val} 추가됨!")

    if st.session_state.data_list:
        # 1. 날짜 순 정렬
        st.session_state.data_list.sort(key=lambda x: x['date'])
        
        df = pd.DataFrame(st.session_state.data_list)[["date", "store", "price"]]
        st.table(df)

        col_dl1, col_dl2 = st.columns(2)
        
        # 2. 엑셀 다운로드
        with col_dl1:
            output_excel = io.BytesIO()
            with pd.ExcelWriter(output_excel, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, startrow=4, sheet_name='내역서')
            st.download_button("📈 엑셀 다운로드", output_excel.getvalue(), f"내역서_{user_name}.xlsx")

        # 3. PDF 생성 (A4 한 장에 4개씩)
        with col_dl2:
            pdf_buffer = io.BytesIO()
            c = canvas.Canvas(pdf_buffer, pagesize=A4)
            width, height = A4
            
            # 영수증 위치 설정 (2x2 배열)
            positions = [
                (50, height/2 + 20, width/2 - 60, height/2 - 60), # 좌상
                (width/2 + 10, height/2 + 20, width/2 - 60, height/2 - 60), # 우상
                (50, 50, width/2 - 60, height/2 - 60), # 좌하
                (width/2 + 10, 50, width/2 - 60, height/2 - 60) # 우하
            ]
            
            for i, item in enumerate(st.session_state.data_list):
                pos_idx = i % 4
                if i > 0 and pos_idx == 0:
                    c.showPage() # 4개 다 차면 새 페이지
                
                x, y, w, h = positions[pos_idx]
                
                # 이미지 임시 저장 후 PDF에 삽입
                img_temp = io.BytesIO()
                item['img'].save(img_temp, format='JPEG')
                img_temp.seek(0)
                c.drawImage(io.BytesIO(img_temp.read()), x, y, width=w, height=h, preserveAspectRatio=True)
                c.drawString(x, y-15, f"[{item['date']}] {item['store']}")
                
            c.save()
            st.download_button("📑 PDF(증빙용) 다운로드", pdf_buffer.getvalue(), f"영수증증빙_{user_name}.pdf")
