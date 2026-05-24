import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import concurrent.futures

st.set_page_config(page_title="모멘텀 주식 추출기", page_icon="📈", layout="wide")

st.title("🔥 강력한 우상향 모멘텀 주식 추출기")
st.markdown("""
최근 1개월, 3개월, 6개월, 1년 동안 꾸준하고 강하게 우상향하는 주도주를 검색합니다.
* **검색 조건:** 1개월 > 10%, 3개월 > 20%, 6개월 > 30%, 1년 > 50%
""")

def process_stock(code, name, date_1m, date_3m, date_6m, date_1y, today):
    try:
        df = fdr.DataReader(code, date_1y.strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d'))
        if len(df) < 200: return None
            
        current_price = int(df['Close'].iloc[-1])
        price_1m = df[df.index <= date_1m]['Close'].iloc[-1]
        price_3m = df[df.index <= date_3m]['Close'].iloc[-1]
        price_6m = df[df.index <= date_6m]['Close'].iloc[-1]
        price_1y = df['Close'].iloc[0]
        
        ret_1m = ((current_price - price_1m) / price_1m) * 100
        ret_3m = ((current_price - price_3m) / price_3m) * 100
        ret_6m = ((current_price - price_6m) / price_6m) * 100
        ret_1y = ((current_price - price_1y) / price_1y) * 100
        
        if (ret_1m >= 10.0) and (ret_3m >= 20.0) and (ret_6m >= 30.0) and (ret_1y >= 50.0):
            return {
                '종목코드': code,
                '종목명': name,
                '현재주가': current_price,
                '1개월(%)': round(ret_1m, 2),
                '3개월(%)': round(ret_3m, 2),
                '6개월(%)': round(ret_6m, 2),
                '1년(%)': round(ret_1y, 2)
            }
    except:
        pass
    return None

if st.button("🚀 초고속 검색 시작 (클릭)"):
    with st.spinner("한국거래소 전체 종목을 초고속 병렬(멀티스레드)로 분석 중입니다... (약 1분 소요)"):
        # 1. 종목 코드 가져오기 (클라우드 IP 차단 방지를 위해 로컬 CSV 파일 사용)
        try:
            krx = pd.read_csv('tickers.csv', dtype=str)
        except FileNotFoundError:
            krx = fdr.StockListing('KRX-DESC')
            
        if 'Market' in krx.columns:
            krx = krx[krx['Market'].isin(['KOSPI', 'KOSDAQ'])]
        
        today = datetime.today()
        date_1m = today - relativedelta(months=1)
        date_3m = today - relativedelta(months=3)
        date_6m = today - relativedelta(months=6)
        date_1y = today - relativedelta(years=1)
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        results = []
        target_stocks = krx.to_dict('records')
        total_stocks = len(target_stocks)
        completed = 0
        
        # 2. 멀티스레딩(병렬 처리) 적용: 한 번에 30개씩 요청
        with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
            futures = {executor.submit(process_stock, row['Code'], row['Name'], date_1m, date_3m, date_6m, date_1y, today): row for row in target_stocks}
            
            for future in concurrent.futures.as_completed(futures):
                completed += 1
                # UI 업데이트 부하를 줄이기 위해 20개 단위로 프로그레스 바 갱신
                if completed % 20 == 0 or completed == total_stocks:
                    progress_bar.progress(completed / total_stocks)
                    status_text.text(f"초고속 병렬 분석 진행 중... ({completed}/{total_stocks})")
                
                res = future.result()
                if res is not None:
                    results.append(res)
                
        progress_bar.progress(1.0)
        status_text.text("분석 완료!")
        
        # 3. 결과 출력
        results_df = pd.DataFrame(results)
        if not results_df.empty:
            results_df = results_df.sort_values(by='1년(%)', ascending=False)
            st.success(f"🎉 총 {len(results_df)}개의 강력한 모멘텀 주식을 찾았습니다!")
            st.dataframe(results_df, use_container_width=True)
        else:
            st.warning("현재 시장에서 조건을 만족하는 종목이 없습니다.")
