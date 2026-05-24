import streamlit as st
import FinanceDataReader as fdr
import pandas as pd
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import concurrent.futures
import requests
from bs4 import BeautifulSoup
from io import StringIO

st.set_page_config(page_title="모멘텀 & 수급 주식 추출기", page_icon="📈", layout="wide")

st.title("🔥 멀티팩터 주식 추출기 (수급+모멘텀+고배당)")
st.markdown("""
과거 특정일(기준일)을 선택하면, 당시의 **수급(외국인/기관)**, **모멘텀(우상향)**, **고배당** 데이터를 분석하여 주도주를 추천합니다.
세 가지 조건 중 **하나라도 만족**하면 추천 목록에 포함되며, **수급이 강한 순서대로 정렬**됩니다.
""")

# 사용자 입력 UI
col1, col2, col3 = st.columns(3)
with col1:
    target_date = st.date_input("🗓️ 기준일 선택 (미입력시 오늘)", value=datetime.today())
with col2:
    momentum_weight = st.slider("📈 최소 1년 수익률 (모멘텀 기준 %)", 0, 100, 50)
with col3:
    div_yield_target = st.slider("💰 최소 배당수익률 (고배당 기준 %)", 0, 10, 5)

def get_supply_demand_and_dividend(code, target_date):
    headers = {'User-Agent': 'Mozilla/5.0'}
    div_val = 'N/A'
    div_num = 0.0
    inst_sum = 0
    frgn_sum = 0
    total_supply = 0
    
    # 1. 배당수익률
    try:
        res1 = requests.get(f'https://finance.naver.com/item/main.naver?code={code}', headers=headers, timeout=3)
        soup = BeautifulSoup(res1.text, 'html.parser')
        div = soup.select_one('#_dvr')
        if div: 
            div_val = div.text.strip()
            div_num = float(div_val)
    except: pass
    
    # 2. 수급 (기준일로부터 과거 3일 합산)
    try:
        # 최근 날짜가 아닐 수 있으므로 1, 2페이지 정도 탐색
        for page in [1, 2, 3]:
            res2 = requests.get(f'https://finance.naver.com/item/frgn.naver?code={code}&page={page}', headers=headers, timeout=3)
            dfs = pd.read_html(StringIO(res2.text), encoding='euc-kr')
            df = dfs[3].dropna()
            
            # 주말/공휴일을 대비하여 기준일보다 작거나 같은 가장 최근 영업일을 찾음
            df['date_dt'] = pd.to_datetime(df['날짜'], format='%Y.%m.%d', errors='coerce')
            valid_df = df[df['date_dt'] <= pd.to_datetime(target_date)]
            
            if not valid_df.empty:
                idx = valid_df.index[0]
                # 타겟 날짜 포함하여 과거 3일 (idx, idx+1, idx+2)
                sub_df = valid_df.loc[idx:idx+2]
                if len(sub_df) > 0:
                    inst_sum = int(sub_df.iloc[:, 5].astype(float).sum())
                    frgn_sum = int(sub_df.iloc[:, 6].astype(float).sum())
                    total_supply = inst_sum + frgn_sum
                break
    except: pass
    
    return div_val, div_num, inst_sum, frgn_sum, total_supply

def process_stock(code, name, market, sector, target_date, date_1m, date_3m, date_6m, date_1y):
    try:
        # 가격 데이터 1년 전 ~ 기준일
        df = fdr.DataReader(code, date_1y.strftime('%Y-%m-%d'), target_date.strftime('%Y-%m-%d'))
        if len(df) < 60: return None # 데이터가 너무 적은 신규 상장주 제외
            
        current_price = int(df['Close'].iloc[-1])
        price_1m = df[df.index <= date_1m]['Close'].iloc[-1] if len(df[df.index <= date_1m]) > 0 else df['Close'].iloc[0]
        price_3m = df[df.index <= date_3m]['Close'].iloc[-1] if len(df[df.index <= date_3m]) > 0 else df['Close'].iloc[0]
        price_6m = df[df.index <= date_6m]['Close'].iloc[-1] if len(df[df.index <= date_6m]) > 0 else df['Close'].iloc[0]
        price_1y = df['Close'].iloc[0]
        
        ret_1m = ((current_price - price_1m) / price_1m) * 100
        ret_3m = ((current_price - price_3m) / price_3m) * 100
        ret_6m = ((current_price - price_6m) / price_6m) * 100
        ret_1y = ((current_price - price_1y) / price_1y) * 100
        
        # 조건 B: 강력한 모멘텀 조건 
        is_momentum = (ret_1m >= 10.0) and (ret_3m >= 20.0) and (ret_6m >= 30.0) and (ret_1y >= momentum_weight)
        
        # 불필요한 스크래핑 최소화 (너무 심각한 폭락주는 제외하여 속도 최적화)
        if not is_momentum and ret_1y < -40:
            return None
            
        # 수급 및 배당 가져오기
        div_val, div_num, inst_sum, frgn_sum, total_supply = get_supply_demand_and_dividend(code, target_date)
        
        # 조건 C: 고배당 조건
        is_dividend = (div_num >= div_yield_target)
        # 조건 A: 수급 조건 (양매수 이거나 합산 수급이 5만주 이상)
        is_supply = (total_supply >= 50000) or (inst_sum > 0 and frgn_sum > 0 and total_supply > 0)
        
        # 세 조건 중 하나라도 만족하면 결과에 포함 (OR 조건)
        if is_momentum or is_dividend or is_supply:
            
            # 주된 조건 판별 (우선순위: 수급 -> 모멘텀 -> 고배당)
            condition_type = '수급주'
            if is_momentum and is_supply: condition_type = '수급+모멘텀'
            elif is_dividend and is_supply: condition_type = '수급+고배당'
            elif is_momentum: condition_type = '모멘텀'
            elif is_dividend: condition_type = '고배당'

            return {
                '종목코드': code,
                '종목명': name,
                '분류': condition_type,
                '시장': market,
                '업종': str(sector) if pd.notnull(sector) else '-',
                '기준일주가': current_price,
                '수급점수(외인+기관)': total_supply,
                '외인순매수(3일)': frgn_sum,
                '기관순매수(3일)': inst_sum,
                '배당수익률(%)': div_val,
                '1개월(%)': round(ret_1m, 2),
                '3개월(%)': round(ret_3m, 2),
                '6개월(%)': round(ret_6m, 2),
                '1년(%)': round(ret_1y, 2)
            }
    except:
        pass
    return None

if st.button("🚀 멀티팩터 검색 시작 (클릭)"):
    with st.spinner("한국거래소 전체 종목을 초고속 병렬(멀티스레드)로 분석 중입니다... (약 2~3분 소요)"):
        try:
            krx = pd.read_csv('tickers.csv', dtype=str)
        except FileNotFoundError:
            krx = fdr.StockListing('KRX-DESC')
            
        if 'Market' in krx.columns:
            krx = krx[krx['Market'].isin(['KOSPI', 'KOSDAQ'])]
            # 메모리 초과(초기화) 및 속도 저하 방지를 위해 스팩, 우선주, 리츠, ETF 등 제외
            krx = krx[~krx['Name'].str.contains('스팩|제[0-9]+호|우$|우B$|리츠|KODEX|TIGER|KBSTAR|HANARO|KOSEF', regex=True)]
        
        target_date_dt = pd.to_datetime(target_date)
        date_1m = target_date_dt - relativedelta(months=1)
        date_3m = target_date_dt - relativedelta(months=3)
        date_6m = target_date_dt - relativedelta(months=6)
        date_1y = target_date_dt - relativedelta(years=1)
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        results = []
        target_stocks = krx.to_dict('records')
        total_stocks = len(target_stocks)
        completed = 0
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
            futures = {executor.submit(process_stock, row['Code'], row['Name'], row.get('Market', '-'), row.get('Sector', '-'), target_date_dt, date_1m, date_3m, date_6m, date_1y): row for row in target_stocks}
            
            for future in concurrent.futures.as_completed(futures):
                completed += 1
                if completed % 20 == 0 or completed == total_stocks:
                    progress_bar.progress(completed / total_stocks)
                    status_text.text(f"수급/모멘텀/배당 동시 분석 중... ({completed}/{total_stocks})")
                
                res = future.result()
                if res is not None:
                    results.append(res)
                
        progress_bar.progress(1.0)
        status_text.text("분석 완료! 추천 순위에 맞춰 표를 생성합니다...")
        
        results_df = pd.DataFrame(results)
        if not results_df.empty:
            # 추출 결과를 수급(외인+기관 순매수 합산) 기준으로 내림차순 정렬
            results_df = results_df.sort_values(by='수급점수(외인+기관)', ascending=False)
            
            # 가독성을 위해 수급점수를 문자열 포맷팅
            results_df['수급점수(외인+기관)'] = results_df['수급점수(외인+기관)'].apply(lambda x: f"{x:,}")
            results_df['외인순매수(3일)'] = results_df['외인순매수(3일)'].apply(lambda x: f"{x:,}")
            results_df['기관순매수(3일)'] = results_df['기관순매수(3일)'].apply(lambda x: f"{x:,}")
            
            cols = ['종목코드', '종목명', '분류', '시장', '업종', '기준일주가', '수급점수(외인+기관)', '외인순매수(3일)', '기관순매수(3일)', '배당수익률(%)', '1개월(%)', '3개월(%)', '6개월(%)', '1년(%)']
            results_df = results_df[cols]
            
            st.success(f"🎉 총 {len(results_df)}개의 상승 유력 주도주를 찾았습니다! (수급 강도 순으로 정렬됨)")
            st.dataframe(results_df, use_container_width=True)
        else:
            st.warning("해당 기준일에 조건을 만족하는 종목이 없습니다.")
