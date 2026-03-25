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

# 사이드바 설정
st.session_state.user_name = st.sidebar.text_input("성명", st.session_state.user_name)

# [센스] 대상 월 선택 (일자 제외, 월까지만 선택)
report_date = st.sidebar.date_input("대상 월 선택", value=datetime.now())
selected_month = report_date.strftime('%m').lstrip('0') # '03' -> '3'

uploaded_files = st.file_uploader("영수증 사진들을 올려주세요", accept_multiple_files=True)

if uploaded_files:
    for idx, uploaded_file in enumerate(uploaded_files):
        file_key = uploaded_file.name
        
        if file_key not in st.session_state.ocr_cache:
            img = Image.open(uploaded_file)
            gray_img = ImageOps.grayscale(img) # 인식률 향상 전처리
            raw_text = pytesseract.image_to_string(gray_img, lang='kor+eng')
            st.session_state.ocr_cache[file_key] = raw_text
        
        raw_text = st.session_state.ocr_cache[file_key]
        clean_text = raw_text.replace(' ', '')

        # 1. 달러 결제 여부 (한글 없으면 달러)
        is_dollar = not bool(re.search(r'[ㄱ-ㅎㅏ-ㅣ가-힣]', raw_text))
        remark_default = "달러 결제" if is_dollar else ""

        # 2. 날짜 추출 및 달력 기본값
        date_match = re.search(r'(\d{4})[-/.](\d{2})[-/.](\d{2})', raw_text)
        try:
            default_date = datetime.strptime(date_match.group(0).replace('.','-').replace('/','-'), '%Y-%m-%d') if date_match else datetime.now()
        except: default_date = datetime.now()
        
        # 3. 식사 구분
        time_match = re.search(r'(\d{2}):(\d{2})', raw_text)
        meal_type = "석식"
        if time_match:
            try:
                h, m = map(int, time_match.groups())
                if time(3,1) <= time(h,m) <= time(10,0): meal_type = "조식"
                elif time(10,1) <= time(h,m) <= time(15,0): meal_type = "중식"
            except: pass

        # 4. 금액 및 식당명
        price_match = re.search(r'(?:TOTAL|AMOUNT|합계|결제|금액)[:]?\s*([\d,.]+)', clean_text, re.I)
        extracted_price = price_match.group(1).replace(',', '').split('.')[0] if price_match else "0"
        lines = [l.strip() for l in raw_text.split('\n') if len(l.strip()) > 2]
        extracted_store = lines[0] if lines else "식당 직접 입력"

        with st.form(key=f"form_{file_key}"):
            st.image(Image.open(uploaded_file), width=300)
            c1, c2, c3 = st.columns([1, 1.5, 1])
            with c1: d_val = st.date_input("날짜", default_date, key=f"d_{idx}")
            with c2: s_val = st.text_input("식당명", extracted_store, key=f"s_{idx}")
            with c3: m_val = st.selectbox("구분", ["조식", "중식", "석식"], index=["조식", "중식", "석식"].index(meal_type), key=f"m_{idx}")
            
            p1, p2 = st.columns(2)
            with p1: pr_val = st.number_input("금액", value=int(extracted_price), key=f"p_{idx}")
            with p2: r_val = st.text_input("비고", remark_default, key=f"r_{idx}")
            
            if st.form_submit_button("확정 (수정 가능)"):
                st.session_state.data_dict[file_key] = {
                    "날짜": d_val.strftime('%y-%m-%d'), "식당명": s_val, "구분": m_val, 
                    "금액": pr_val, "비고": r_val, "img": Image.open(uploaded_file)
                }
                st.success("반영되었습니다!")

    if st.session_state.data_dict:
        sorted_list = sorted(st.session_state.data_dict.values(), key=lambda x: x['날짜'])
        df = pd.DataFrame(sorted_list).drop('img', axis=1)
        
        # [표시용] 금액 세자리 쉼표
        df_display = df.copy()
        df_display['금액'] = df_display['금액'].apply(lambda x: f"{x:,}")
        
        st.subheader(f"📋 {selected_month}월 확정 내역 (날짜순)")
        st.table(df_display)

        col_ex, col_pdf = st.columns(2)
        
        # [파일명 동적 생성]
        excel_name = f"{selected_month}월 개인법인카드 사용내역서_{st.session_state.user_name}.xlsx"
        pdf_name = f"{selected_month}월 개인법인카드 영수증_{st.session_state.user_name}.pdf"

        with col_ex:
            output_excel = io.BytesIO()
            with pd.ExcelWriter(output_excel, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, startrow=4, sheet_name='내역서')
            st.download_button("📈 엑셀 다운로드", output_excel.getvalue(), excel_name)

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
            st.download_button("📑 PDF(증빙용) 다운로드", pdf_buffer.getvalue(), pdf_name)
