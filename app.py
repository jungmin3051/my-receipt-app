import streamlit as st
import pandas as pd
from datetime import datetime
import re
from PIL import Image, ImageOps  # 사진 회전 해결을 위해 ImageOps 추가
import pytesseract
import io
import numpy as np
import cv2
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Side, Font

st.set_page_config(page_title="영수증 정리기", layout="centered")

# 1. 세션 상태 및 기본 정보 설정
if 'user_name' not in st.session_state: st.session_state.user_name = "한정민"
if 'data_dict' not in st.session_state: st.session_state.data_dict = {} 
if 'ocr_cache' not in st.session_state: st.session_state.ocr_cache = {}

st.title("📑 법인카드 영수증 자동 정리")

# 사이드바 설정 (선임님 양식 고정 정보)
st.session_state.user_name = st.sidebar.text_input("성명", st.session_state.user_name)
user_rank = st.sidebar.text_input("직책", "선임")
card_num = st.sidebar.text_input("법인카드번호", "4265-8699-8653-1838")
report_date = st.sidebar.date_input("대상 월 선택", value=datetime.now())
selected_month = report_date.strftime('%m').lstrip('0')

uploaded_files = st.file_uploader("영수증 사진들을 올려주세요", accept_multiple_files=True)

if uploaded_files:
    for idx, uploaded_file in enumerate(uploaded_files):
        file_key = uploaded_file.name
        
        if file_key not in st.session_state.ocr_cache:
            # [이미지 회전 보정] 세로 사진이 가로로 나오는 문제 해결
            raw_img = Image.open(uploaded_file)
            img = ImageOps.exif_transpose(raw_img) # EXIF 정보를 바탕으로 정방향 회전
            
            # [한국어 강화 전처리] OpenCV 활용
            img_array = np.array(img.convert('RGB'))
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            blur = cv2.GaussianBlur(gray, (3,3), 0)
            # 적응형 이진화로 한국어 획을 또렷하게 만듦 
            thresh = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
            
            # OCR 엔진 설정 (한국어+영어 병행)
            custom_config = r'--oem 3 --psm 6 -l kor+eng'
            st.session_state.ocr_cache[file_key] = pytesseract.image_to_string(thresh, config=custom_config)
            
            # 화면 표시용 이미지 저장
            st.session_state.data_dict[file_key + "_img"] = img
        
        raw_text = st.session_state.ocr_cache[file_key]
        clean_text = raw_text.replace(' ', '')

        # 데이터 자동 추출 (달러, 날짜, 금액)
        is_dollar = not bool(re.search(r'[ㄱ-ㅎㅏ-ㅣ가-힣]', raw_text))
        date_match = re.search(r'(\d{4})[-/.](\d{2})[-/.](\d{2})', raw_text)
        try:
            default_date = datetime.strptime(date_match.group(0).replace('.','-').replace('/','-'), '%Y-%m-%d') if date_match else datetime.now()
        except: default_date = datetime.now()
        
        price_match = re.search(r'(?:TOTAL|AMOUNT|합계|결제|금액)[:]?\s*([\d,.]+)', clean_text, re.I)
        extracted_price = int(price_match.group(1).replace(',', '').split('.')[0]) if price_match else 0
        lines = [l.strip() for l in raw_text.split('\n') if len(l.strip()) > 1]
        extracted_store = lines[0] if lines else "식당 직접 입력"

        # 입력 폼
        with st.form(key=f"form_{file_key}"):
            # 회전 보정된 이미지 출력
            current_img = st.session_state.data_dict.get(file_key + "_img", Image.open(uploaded_file))
            st.image(current_img, width=300)
            
            c1, c2, c3 = st.columns([1, 1.5, 1])
            with c1: d_val = st.date_input("날짜", default_date, key=f"d_{idx}")
            with c2: s_val = st.text_input("식당명", extracted_store, key=f"s_{idx}")
            with c3: m_val = st.selectbox("구분", ["조식", "중식", "석식"], key=f"m_{idx}")
            
            p1, p2 = st.columns(2)
            with p1: pr_val = st.number_input("금액", value=extracted_price, key=f"p_{idx}")
            with p2: r_val = st.text_input("비고", "달러 결제" if is_dollar else "", key=f"r_{idx}")
            
            if st.form_submit_button("확정"):
                st.session_state.data_dict[file_key] = {
                    "날짜": d_val.strftime('%y-%m-%d'), "식당명": s_val, "구분": m_val, 
                    "금액": pr_val, "비고": r_val, "img": current_img
                }
                # 매뉴얼에서 본 고급 아이콘 적용
                st.success(f"**{s_val}** 내역 반영 완료!", icon=":material/task_alt:")

    if st.session_state.data_dict:
        # 데이터가 있는 것만 필터링 (이미지 캐시 제외)
        final_items = [v for k, v in st.session_state.data_dict.items() if isinstance(v, dict)]
        sorted_list = sorted(final_items, key=lambda x: x['날짜'])
        
        df_display = pd.DataFrame(sorted_list).drop('img', axis=1)
        df_display['금액'] = df_display['금액'].apply(lambda x: f"{x:,}")
        st.subheader(f"📋 {selected_month}월 정리 내역 요약")
        st.table(df_display)

        # ---------------- 엑셀 생성 (선임님 전용 양식) ----------------
        output_excel = io.BytesIO()
        wb = Workbook()
        ws = wb.active
        ws.title = "내역서"
        thin = Side(border_style="thin", color="000000")
        border = Border(top=thin, left=thin, right=thin, bottom=thin)

        ws['A3'] = f"성 명 : {st.session_state.user_name}"; ws['C3'] = f"직 책 : {user_rank}"
        ws['F3'] = f"제출일 : {datetime.now().strftime('%Y년 %m월 %d일')}"
        ws['A4'] = "법인카드번호 :"; ws['B4'] = card_num

        headers = ["구 분", "일 자", "내 용", "구분(식사)", "금 액", "비 고"]
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=5, column=col, value=header)
            cell.font = Font(bold=True); cell.alignment = Alignment(horizontal='center'); cell.border = border

        total_sum = 0
        for i, item in enumerate(sorted_list, 6):
            ws.cell(row=i, column=2, value=item['날짜']).border = border
            ws.cell(row=i, column=3, value=item['식당명']).border = border
            ws.cell(row=i, column=4, value=item['구분']).border = border
            ws.cell(row=i, column=5, value=item['금액']).border = border
            ws.cell(row=i, column=5).number_format = '#,##0'
            ws.cell(row=i, column=6, value=item['비고']).border = border
            total_sum += item['금액']

        res_row = len(sorted_list) + 6
        ws.cell(row=res_row, column=3, value="합 계").alignment = Alignment(horizontal='right')
        ws.cell(row=res_row, column=5, value=total_sum).number_format = '#,##0'; ws.cell(row=res_row, column=5).border = border
        wb.save(output_excel)
        
        # ---------------- PDF 생성 (회전 보정 이미지 반영) ----------------
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
        
        col_ex, col_pdf = st.columns(2)
        excel_fn = f"{selected_month}월 개인법인카드 사용내역서_{st.session_state.user_name}.xlsx"
        pdf_fn = f"{selected_month}월 개인법인카드 영수증_{st.session_state.user_name}.pdf"
        
        with col_ex: st.download_button("📈 엑셀 다운로드", output_excel.getvalue(), excel_fn)
        with col_pdf: st.download_button("📑 PDF(증빙용) 다운로드", pdf_buffer.getvalue(), pdf_fn)
