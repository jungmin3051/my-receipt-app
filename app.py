import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import io
import base64
from PIL import Image, ImageOps

# 0. 설정
st.set_page_config(page_title="정민 영수증 매니저", layout="wide")

# 구글 시트 주소
SHEET_URL = "https://docs.google.com/spreadsheets/d/1x419Jb6laxcObm4z2nFU_W65Cx-4AxmAjwmE8ouFmjk/edit?usp=sharing"

# 서비스 연결
conn = st.connection("gsheets", type=GSheetsConnection)

# 사진을 시트에 저장 가능한 텍스트로 변환하는 함수
def img_to_base64(image):
    image = ImageOps.exif_transpose(image)
    image.thumbnail((600, 600)) # 시트 용량을 위해 크기 축소
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG", quality=60)
    return base64.b64encode(buffered.getvalue()).decode()

st.title("📑 한정민 선임님 영수증 관리 (에러 해결판)")

# 1단계: 업로드 (모바일)
with st.expander("📸 1단계: 사진 업로드", expanded=True):
    files = st.file_uploader("사진을 선택하세요", accept_multiple_files=True)
    if files:
        for f in files:
            if f"up_{f.name}" not in st.session_state:
                with st.spinner(f'{f.name} 처리 중...'):
                    img = Image.open(f)
                    img_data = img_to_base64(img) # 사진을 텍스트로 변환
                    
                    new_row = pd.DataFrame([{
                        "성명": "한정민", 
                        "날짜": datetime.now().strftime('%Y-%m-%d'),
                        "식당명": "미입력", 
                        "금액": 0, 
                        "비고": img_data, # 사진 데이터 직접 저장
                        "상태": "임시"
                    }])
                    
                    data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)
                    updated = pd.concat([data, new_row], ignore_index=True)
                    conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=updated)
                    st.session_state[f"up_{f.name}"] = True
        st.success("✅ 업로드 완료! 이제 아래에서 내용을 수정하세요.")

# 2단계: 수정 (PC)
st.divider()
try:
    all_data = conn.read(spreadsheet=SHEET_URL, worksheet="Sheet1", ttl=0)
    temp_targets = all_data[all_data["상태"] == "임시"].copy()
    
    if not temp_targets.empty:
        st.subheader("📝 2단계: 내역 수정 및 확정")
        for i, row in temp_targets.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([1, 2])
                with c1:
                    # 시트에 저장된 텍스트 데이터를 다시 사진으로 보여줌
                    st.image(base64.b64decode(row["비고"]), caption="영수증 미리보기", use_container_width=True)
                with c2:
                    ca, cb, cc = st.columns(3)
                    d = ca.date_input("날짜", datetime.now(), key=f"d_{i}")
                    s = cb.text_input("식당명", row["식당명"], key=f"s_{i}")
                    p = cc.number_input("금액", value=0, key=f"p_{i}")
                    if st.button("확정 저장", key=f"b_{i}"):
                        all_data.at[i, "날짜"], all_data.at[i, "식당명"], all_data.at[i, "금액"], all_data.at[i, "상태"] = d.strftime('%Y-%m-%d'), s, p, "완료"
                        conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=all_data)
                        st.rerun()
    else:
        st.info("수정할 내역이 없습니다.")
except Exception as e:
    st.error(f"데이터 로드 실패: {e}")

# 3단계: 다운로드
final_data = all_data[all_data["상태"] == "완료"]
if not final_data.empty:
    st.divider()
    out = io.BytesIO()
    # 엑셀 다운로드 시 '비고(사진데이터)' 열은 제외하고 저장
    final_data.drop(columns=['비고']).to_excel(out, index=False)
    st.download_button("📥 최종 엑셀 다운로드", out.getvalue(), f"영수증_{datetime.now().strftime('%m%d')}.xlsx")
