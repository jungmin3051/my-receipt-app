import streamlit as st
import pandas as pd
from datetime import datetime, time
import re
from PIL import Image, ImageOps
import pytesseract
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader

st.set_page_config(page_title="영수증 정리기", layout="centered")

# 데이터 유지 및 중복 방지
if 'user_name' not in st.session_state:
    st.session_state.user_name = "한정민"
if 'data_dict' not in st.session_state:
    st.session_state.data_dict = {} 
if 'ocr_cache' not in st.session_state:
    st.session_state.ocr_cache = {}

st.title("📑 법인카드 영수증 자동 정리")

st.session_state.user_name = st.sidebar.text_input("성명", st.session_state.user_name)
report_month = st.sidebar.date_input("대상 월 선택")

uploaded_files = st.file_uploader("영수증 사진들을 올려주세요", accept_multiple_files=True)

if uploaded_files:
    for idx, uploaded_file in enumerate(uploaded_files):
        file_key = uploaded_file.name
        
        if file_key not in st.session_state.ocr_cache:
            img = Image.open(uploaded_file)
            # 인식률 향상을 위한 전처리 (흑백 전환)
            gray_img = ImageOps.grayscale(img)
            raw_text = pytesseract.image_to_string(gray_img, lang='kor+eng')
            st.session_state.ocr_cache[file_key] = raw_text
        
        raw_text = st.session_state.ocr_cache[file_key]
        clean_text = raw_text.replace(' ', '')

        # 1. 달러 결제 여부 확인 (한글이 하나도 없는 경우)
        is_dollar = not bool(re.search(r'[ㄱ-ㅎㅏ-ㅣ가-힣]', raw_text))
        remark_default = "달러 결제" if is_dollar else ""

        # 2. 날짜 추출 및 달력용 데이터 변환
        date_match = re.search(r'(\d{4})[-/.](\d{2})[-/.](\d{2})', raw_text)
        try:
            if date_match:
                default_date = datetime.strptime(date_match.group(0).replace('.','-').replace('/','-'), '%Y-%m-%d')
            else:
                default_date = datetime.now()
        except:
            default_date = datetime.now()
        
        # 3. 식사 구분
        time_match = re.search(r'(\d{2}):(\d{2})', raw_text)
        meal_type = "석식"
        if time_match:
            try:
                h, m = map(int, time_match.groups())
                check_time = time(h, m)
                if time(3, 1) <= check_time <= time(10, 0): meal_type = "조식"
                elif time(10, 1) <= check_time <= time(15, 0): meal_type = "중식"
            except: pass

        # 4. 금액 및 식당명
        price_match = re.search(r'(?:TOTAL|AMOUNT|합계|결제|금액)[:]?\s*([\d,.]+)', clean_text, re.I)
        extracted_price = price_match.group(1).replace(',', '').split('.')[0] if price_match else "0"
        
        # 식당명: 상단 텍스트 중 의미 있는 첫 줄 추출
        lines = [l.strip() for l in raw_text.split('\n') if len(l.strip()) > 2]
        extracted_store = lines[0] if lines else "식당 직접 입력"

        with st.form(key=f"form_{file_key}"):
            st.image(Image.open(uploaded_file), width=300)
            c1, c2, c3 = st.columns([1, 1.5, 1])
            # [센스 1] 날짜 입력 시 작은 달력이 뜨도록 수정
            with c1: d_val = st.date_input("날짜", default_date, key=f"d_{idx}")
            with c2: s_val = st.text_input("식당명", extracted_store, key=f"s_{idx}")
            with c3: m_val = st.selectbox("구분", ["조식", "중식", "석식"], 
                                         index=["조식", "중식", "석식"].index(meal_type), key=f"m_{idx}")
            
            p1, p2 = st.columns(2)
            with p1: pr_val = st.number_input("금액", value=int(extracted_price), key=f"p_{idx}")
            with p2: r_val = st.text_input("비고(달러 등)", remark_default, key=f"r_{idx}")
            
            if st.form_submit_button("확정 (수정 후 다시 누르면 교체됨)"):
                formatted_date = d_val.strftime('%y-%m-%d') # 선임님 요청 YY-MM-DD 형식
                st.session_state.data_dict[file_key] = {
                    "날짜": formatted_date, "식당명": s_val, "구분": m_val, 
                    "금액": pr_val, "비고": r_val, "img": Image.open(uploaded_file)
                }
                st.success(f"반영 완료!")

    if st.session_state.data_dict:
        sorted_list = sorted(st.session_state.data_dict.values(), key=lambda x: x['날짜'])
        df = pd.DataFrame(sorted_list).drop('img', axis=1)
        
        # [센스 2] 금액 부분 세자리마다 쉼표 표시
        df['금액'] = df['금액'].apply(lambda x: f"{x:,}")
        
        st.subheader("📋 확정된 내역 (날짜순)")
        st.table(df)

        col_ex, col_pdf = st.columns(2)
        with col_ex:
            output_excel = io.BytesIO()
            with pd.ExcelWriter(output_excel, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, startrow=4, sheet_name='내역서')
            st.download_button("📈 엑셀 다운로드", output_excel.getvalue(), f"내역서_{st.session_state.user_name}.xlsx")

        with col_pdf:
            pdf_buffer = io.BytesIO()
            c = canvas.Canvas(pdf_buffer, pagesize=A4)
            w, h = A4
            pos = [(50, h/2+20, w/2-60, h/2-100), (w/2+10, h/2+20, w/2-60, h/2-100),
                   (50, 50, w/2-60, h/2-100), (w/2+10, 50, w/2-60, h/2-100)]
            
            for i, item in enumerate(sorted_list):
                if i > 0 and i % 4 == 0: c.showPage()
                px, py, pw, ph = pos[i % 4]
                img_temp = io.BytesIO()
                item['img'].save(img_temp, format='JPEG')
                img_temp.seek(0)
                c.drawImage(ImageReader(img_temp), px, py, width=pw, height=ph, preserveAspectRatio=True)
                c.drawString(px, py-15, f"[{item['날짜']}] {item['식당명']}")
            c.save()
            st.download_button("📑 PDF(증빙용) 다운로드", pdf_buffer.getvalue(), f"영수증증빙_{st.session_state.user_name}.pdf")
