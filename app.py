# --- 3단계: 내역 확인 및 삭제 (최종 수정 버전) ---
if not all_data.empty:
    st.divider()
    st.subheader("👀 3단계: 내역 확인 및 삭제")
    
    edit_df = all_data.drop(columns=["사진데이터"], errors='ignore').copy()
    edit_df["삭제체크"] = False
    edit_df.index = edit_df.index + 1 
    edited_data = st.data_editor(edit_df, use_container_width=True, disabled=["날짜", "식당명", "시간대", "금액", "비고", "상태"])
    
    def parse_money(x):
        try: return int(str(x).replace(',', '').replace('원', ''))
        except: return 0

    done_items = all_data[all_data["상태"] == "완료"].copy()
    done_items['int_amount'] = done_items['금액'].apply(parse_money)
    
    def get_day_group(date_str):
        try:
            day = int(str(date_str).split('-')[-1])
            if day <= 10: return "1~10일"
            elif day <= 20: return "11~20일"
            else: return "21~말일"
        except: return "기타"

    done_items['구간'] = done_items['날짜'].apply(get_day_group)
    periodic_sum = done_items.groupby('구간')['int_amount'].sum().to_dict()
    
    total_sum = done_items['int_amount'].sum()
    limit_amount = 500000
    remaining_amount = limit_amount - total_sum
    remain_color = "#ff4b4b" if remaining_amount < 0 else "#1f77b4"

    # 상단 총액 요약 (한 줄로 압축)
    summary_html = f"<div style='background-color:#f8f9fb;padding:12px;border-radius:10px;border:1px solid #e6e9ef;margin:10px 0;'><div style='display:flex;justify-content:space-around;align-items:center;'> <div style='text-align:center;'><span style='font-size:14px;color:#666;'>💳 총 사용 금액</span><br><span style='font-size:22px;font-weight:bold;'>{total_sum:,} 원</span></div> <div style='width:1px;height:35px;background-color:#e6e9ef;'></div> <div style='text-align:center;'><span style='font-size:14px;color:#666;'>💰 총 남은 금액</span><br><span style='font-size:22px;color:{remain_color};font-weight:bold;'>{remaining_amount:,} 원</span></div> </div></div>"
    st.markdown(summary_html, unsafe_allow_html=True)

    # 구간 테이블 (줄바꿈 없이 한 줄로 조립)
    table_html = "<table style='width:100%;border-collapse:collapse;text-align:center;border:1px solid #e6e9ef;font-size:14px;'>"
    table_html += "<thead style='background-color:#f1f3f6;'><tr><th style='padding:10px;border:1px solid #e6e9ef;'>구간</th><th style='padding:10px;border:1px solid #e6e9ef;'>사용 금액</th><th style='padding:10px;border:1px solid #e6e9ef;'>13만원 대비 잔액</th></tr></thead><tbody>"
    
    for p in ["1~10일", "11~20일", "21~말일"]:
        usage = periodic_sum.get(p, 0)
        diff = 130000 - usage
        d_color = "#ff4b4b" if diff < 0 else "#1f77b4"
        table_html += f"<tr><td style='padding:10px;border:1px solid #eee;'>{p}</td><td style='padding:10px;border:1px solid #eee;'>₩ {usage:,}</td><td style='padding:10px;border:1px solid #eee;color:{d_color};font-weight:bold;'>₩ {diff:,}</td></tr>"
    
    table_html += "</tbody></table><div style='margin-bottom:20px;'></div>"
    st.markdown(table_html, unsafe_allow_html=True)

    # 삭제 버튼
    checked_indices = edited_data[edited_data["삭제체크"] == True].index.tolist()
    if checked_indices:
        if st.button(f"🗑️ {len(checked_indices)}개 항목 삭제하기", type="primary", use_container_width=True):
            remaining_df = all_data.drop(all_data.index[[i-1 for i in checked_indices]]).reset_index(drop=True)
            conn.update(spreadsheet=SHEET_URL, worksheet="Sheet1", data=remaining_df[COLUMNS])
            st.cache_data.clear()
            st.rerun()
