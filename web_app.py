import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import concurrent.futures
import requests
from bs4 import BeautifulSoup
from io import StringIO

st.set_page_config(page_title="모멘텀 주식 추출기", page_icon="📈", layout="wide")

st.title("🔥 강력한 우상향 모멘텀 주식 추출기")
st.markdown("""
최근 1개월, 3개월, 6개월, 1년 동안 꾸준하고 강하게 우상향하는 주도주를 검색합니다.
* **검색 조건:** 1개월 > 10%, 3개월 > 20%, 6개월 > 30%, 1년 > 50%
* **추가 정보:** 시장(KOSPI/KOSDAQ), 업종, 배당수익률, 최근 3일 수급(외인/기관) 제공
""")

def process_stock(code, name, market, sector, date_1m, date_3m, date_6m, date_1y, today):
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
                '시장': market,
                '업종': str(sector) if pd.notnull(sector) else '-',
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
    with st.spinner("한국거래소 전체 종목을 초고속 병렬(멀티스레드)로 분석 중입니다... (약 1~2분 소요)"):
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
            futures = {executor.submit(process_stock, row['Code'], row['Name'], row.get('Market', '-'), row.get('Sector', '-'), date_1m, date_3m, date_6m, date_1y, today): row for row in target_stocks}
            
            for future in concurrent.futures.as_completed(futures):
                completed += 1
                if completed % 20 == 0 or completed == total_stocks:
                    progress_bar.progress(completed / total_stocks)
                    status_text.text(f"초고속 병렬 분석 진행 중... ({completed}/{total_stocks})")
                
                res = future.result()
                if res is not None:
                    results.append(res)
                
        progress_bar.progress(1.0)
        status_text.text("분석 완료! 추가 데이터를 수집합니다...")
        
        # 3. 추가 데이터 수집 및 결과 출력
        results_df = pd.DataFrame(results)
        if not results_df.empty:
            results_df = results_df.sort_values(by='1년(%)', ascending=False)
            
            div_yields = []
            inst_sums = []
            frgn_sums = []
            
            headers = {'User-Agent': 'Mozilla/5.0'}
            for idx, row in results_df.iterrows():
                code = row['종목코드']
                
                # 배당수익률 (네이버 금융 스크래핑)
                div_val = 'N/A'
                try:
                    res1 = requests.get(f'https://finance.naver.com/item/main.naver?code={code}', headers=headers, timeout=3)
                    soup = BeautifulSoup(res1.text, 'html.parser')
                    div = soup.select_one('#_dvr')
                    if div: div_val = div.text.strip()
                except: pass
                div_yields.append(div_val)
                
                # 수급 (기관/외국인 최근 3일 합산 순매수량)
                inst_val = 0
                frgn_val = 0
                try:
                    res2 = requests.get(f'https://finance.naver.com/item/frgn.naver?code={code}', headers=headers, timeout=3)
                    dfs = pd.read_html(StringIO(res2.text), encoding='euc-kr')
                    df = dfs[3].dropna()
                    if len(df) >= 3:
                        inst_val = int(df.iloc[:3, 5].astype(float).sum())
                        frgn_val = int(df.iloc[:3, 6].astype(float).sum())
                except: pass
                
                # 가독성을 위해 천단위 콤마 처리
                inst_sums.append(f"{inst_val:,}")
                frgn_sums.append(f"{frgn_val:,}")
                
            results_df['배당수익률(%)'] = div_yields
            results_df['외인순매수(최근3일)'] = frgn_sums
            results_df['기관순매수(최근3일)'] = inst_sums
            
            # 열 순서 깔끔하게 정렬
            cols = ['종목코드', '종목명', '시장', '업종', '현재주가', '배당수익률(%)', '외인순매수(최근3일)', '기관순매수(최근3일)', '1개월(%)', '3개월(%)', '6개월(%)', '1년(%)']
            results_df = results_df[cols]
            
            st.success(f"🎉 총 {len(results_df)}개의 강력한 모멘텀 주식을 찾았습니다!")
            st.dataframe(results_df, use_container_width=True)
        else:
            st.warning("현재 시장에서 조건을 만족하는 종목이 없습니다.")
