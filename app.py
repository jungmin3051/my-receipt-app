import streamlit as st
import pandas as pd
from datetime import datetime, time
import re
from PIL import Image
import pytesseract
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader

st.set_page_config(page_title="영수증 정리기", layout="centered")

# 1. 브라우저 새로고침 시 데이터 유지 및 중복 방지
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
        
        # 속도 최적화: 캐시된 OCR 결과가 없으면 실행
        if file_key not in st.session_state.ocr_cache:
            img = Image.open(uploaded_file)
            # 한국어만 지정하여 추출 속도 대폭 향상
            raw_text = pytesseract.image_to_string(img, lang='kor')
            st.session_state.ocr_cache[file_key] = raw_text
        
        raw_text = st.session_state.ocr_cache[file_key]
        clean_text = raw_text.replace(' ', '')

        # 1. 날짜 추출 (YY-MM-DD 형식 맞춤)
        date_match = re.search(r'(\d{4})[-/.](\d{2})[-/.](\d{2})', raw_text)
        extracted_date = f"{date_match.group(1)[2:]}-{date_match.group(2)}-{date_match.group(3)}" if date_match else datetime.now().strftime('%y-%m-%d')
        
        # 2. 식사 구분 (선임님 요청 시간 기준)
        time_match = re.search(r'(\d{2}):(\d{2})', raw_text)
        meal_type = "석식"
        if time_match:
            h, m = map(int, time_match.groups())
            if time(3, 1) <= time(h, m) <= time(10, 0): meal_type = "조식"
            elif time(10, 1) <= time(h, m) <= time(15, 0): meal_type = "중식"

        # 3. 금액 및 식당명
        price_match = re.search(r'(?:합계|결제|금액)[:]?([\d,]{3,})', clean_text)
        extracted_price = int(price_match.group(1).replace(',', '')) if price_match else 0
        store_match = re.search(r'(?:상호|매장명)[:]?\s*([^\n\d\(\)/]+)', raw_text)
        extracted_store = store_match.group(1).strip() if store_match else raw_text.split('\n')[0][:15]

        # 입력 폼
        with st.form(key=f"form_{file_key}"):
            st.image(Image.open(uploaded_file), width=300)
            c1, c2, c3 = st.columns([1, 1.5, 1])
            with c1: d_val = st.text_input("날짜", extracted_date, key=f"d_{idx}")
            with c2: s_val = st.text_input("식당명", extracted_store, key=f"s_{idx}")
            with c3: m_val = st.selectbox("구분", ["조식", "중식", "석식"], 
                                         index=["조식", "중식", "석식"].index(meal_type), key=f"m_{idx}")
            
            p1, p2 = st.columns(2)
            with p1: pr_val = st.number_input("금액", value=extracted_price, key=f"p_{idx}")
            with p2: r_val = st.text_input("비고", "", key=f"r_{idx}")
            
            if st.form_submit_button("확정 (수정 시 다시 클릭)"):
                # 동일 파일명 업로드 시 데이터 덮어쓰기 (중복 방지)
                st.session_state.data_dict[file_key] = {
                    "날짜": d_val, "식당명": s_val, "구분": m_val, 
                    "금액": pr_val, "비고": r_val, "img": Image.open(uploaded_file)
                }
                st.success(f"{s_val} 내역이 반영되었습니다.")

    if st.session_state.data_dict:
        # 1. 날짜 기준 오름차순 정렬 (가장 빠른 결제일이 상단)
        sorted_list = sorted(st.session_state.data_dict.values(), key=lambda x: x['날짜'])
        df = pd.DataFrame(sorted_list).drop('img', axis=1)
        st.table(df)

        col_ex, col_pdf = st.columns(2)
        with col_ex:
            output_excel = io.BytesIO()
            with pd.ExcelWriter(output_excel, engine='openpyxl') as writer:
                # 엑셀 데이터 순서: 날짜 / 식당명 / 구분 / 금액 / 비고
                df.to_excel(writer, index=False, startrow=4, sheet_name='내역서')
            st.download_button("📈 엑셀 다운로드", output_excel.getvalue(), f"내역서_{st.session_state.user_name}.xlsx")

        with col_pdf:
            pdf_buffer = io.BytesIO()
            c = canvas.Canvas(pdf_buffer, pagesize=A4)
            w, h = A4
            # A4 4분할 좌표
            pos = [(50, h/2+20, w/2-60, h/2-100), (w/2+10, h/2+20, w/2-60, h/2-100),
                   (50, 50, w/2-60, h/2-100), (w/2+10, 50, w/2-60, h/2-100)]
            
            # 2. 정렬된 순서대로 PDF 배치 (가장 빠른 날짜부터 1번 자리)
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
