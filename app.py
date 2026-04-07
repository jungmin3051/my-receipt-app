def create_photo_pdf(df):
    pdf = FPDF()
    
    # 1. 폰트 설정 (깃허브에 올린 파일명과 대소문자 일치 필수)
    font_path = "NanumGothic.ttf"
    if os.path.exists(font_path):
        pdf.add_font('Nanum', '', font_path, uni=True)
        pdf.set_font('Nanum', size=8) # 작은 한 줄을 위해 사이즈 8 설정
    else:
        pdf.set_font("Arial", size=8)

    # 2. 내부 정렬 (날짜 -> 조중석 순)
    df['temp_p'] = df['시간대'].apply(get_meal_priority)
    df_sorted = df.sort_values(by=["날짜", "temp_p"]).reset_index(drop=True)
    
    for i, (_, row) in enumerate(df_sorted.iterrows()):
        if i % 4 == 0: pdf.add_page()
        try:
            img_data = base64.b64decode(row["사진데이터"])
            temp_img = io.BytesIO(img_data)
            
            # 1페이지 4개 배치 좌표
            x = 10 if i % 2 == 0 else 105
            y = 15 if i % 4 < 2 else 153
            
            # 영수증 이미지 출력
            pdf.image(temp_img, x=x, y=y, w=90)
            
            # [요청사항] 사진 바로 밑에 작은 한 줄로 정보 출력
            # 위치를 사진 끝나는 지점(y + 62)으로 잡았습니다.
            pdf.set_xy(x, y + 62)
            
            # 금액에 '원' 표시 추가
            price_display = f"{row['금액']}원" if "원" not in str(row['금액']) else row['금액']
            info_text = f"{row['날짜']} / {row['식당명']} / {row['시간대']} / {price_display}"
            
            # 중앙 정렬('C')로 깔끔하게 한 줄 출력
            pdf.cell(90, 8, info_text, ln=0, align='C')
        except: continue
        
    return bytes(pdf.output())
