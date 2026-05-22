import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import FinanceDataReader as fdr
import yfinance as yf
from datetime import datetime, timedelta, timezone

# 페이지 설정
st.set_page_config(layout="wide", page_title="국내주식 실시간 단타 스캐너")
st.title("🚀 실시간 단타 및 시장 동향 대시보드")

# 한국 시간(KST) 설정
KST = timezone(timedelta(hours=9))

# -----------------------------------------------------------------------------
# 1. 데이터 로드 함수
# -----------------------------------------------------------------------------
@st.cache_data(ttl=60)
def get_market_indices():
    today = datetime.now(KST).strftime('%Y-%m-%d')
    start_date = (datetime.now(KST) - timedelta(days=30)).strftime('%Y-%m-%d')
    
    kospi = fdr.DataReader('KS11', start_date, today)
    kosdaq = fdr.DataReader('KQ11', start_date, today)
    usd_krw = fdr.DataReader('USD/KRW', start_date, today)
    return kospi, kosdaq, usd_krw

@st.cache_data(ttl=30)
def get_realtime_target_stocks():
    df_krx = fdr.StockListing('KRX')
    
    cols_lower = [str(c).lower() for c in df_krx.columns]
    df_krx.columns = cols_lower
    
    def find_col(candidates):
        for c in candidates:
            if c in cols_lower:
                return c
        return None
        
    name_col = find_col(['name', '종목명', '회사명'])
    code_col = find_col(['code', 'symbol', '종목코드'])
    market_col = find_col(['market', '시장구분', '시장'])
    close_col = find_col(['close', '현재가', '종가'])
    chg_col = find_col(['chagesratio', 'chgrate', 'changesratio', 'fluctuationrate', '등락률', 'change'])
    amt_col = find_col(['amount', 'tradingvalue', '거래대금'])
    marcap_col = find_col(['marcap', '시가총액', 'marketcap'])
    
    if not all([name_col, code_col, close_col, chg_col, amt_col, marcap_col]):
        st.error("⚠️ 현재 FinanceDataReader 서버 데이터 제공이 원활하지 않습니다.")
        return pd.DataFrame(columns=['종목명', '종목코드', '시장', '현재가', '등락률', '거래대금', '시가총액'])
        
    if not market_col:
        df_krx['market'] = 'KRX'
        market_col = 'market'
        
    df_krx = df_krx[[name_col, code_col, market_col, close_col, chg_col, amt_col, marcap_col]].copy()
    df_krx.columns = ['종목명', '종목코드', '시장', '현재가', '등락률', '거래대금', '시가총액']
    
    df_krx['현재가'] = pd.to_numeric(df_krx['현재가'], errors='coerce')
    df_krx['등락률'] = pd.to_numeric(df_krx['등락률'], errors='coerce')
    df_krx['거래대금'] = pd.to_numeric(df_krx['거래대금'], errors='coerce') / 1000000 
    df_krx['시가총액'] = pd.to_numeric(df_krx['시가총액'], errors='coerce') / 100000000 
    
    df_krx = df_krx.dropna(subset=['현재가', '등락률', '거래대금', '시가총액'])
    return df_krx

# -----------------------------------------------------------------------------
# [섹션 1] 코스피 / 코스닥 / 환율 변동 그래프
# -----------------------------------------------------------------------------
st.subheader("📊 주요 시장 지수 및 환율 동향")
kospi, kosdaq, usd_krw = get_market_indices()

col1, col2, col3 = st.columns(3)

def create_chart(df, title, color):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df['Close'], mode='lines', name=title, line=dict(color=color, width=2)))
    fig.update_layout(title=title, height=250, margin=dict(l=20, r=20, t=40, b=20), template="plotly_dark")
    return fig

with col1:
    st.plotly_chart(create_chart(kospi, "KOSPI 지수", "#FF4B4B"), use_container_width=True)
with col2:
    st.plotly_chart(create_chart(kosdaq, "KOSDAQ 지수", "#00CC96"), use_container_width=True)
with col3:
    st.plotly_chart(create_chart(usd_krw, "원/달러 환율", "#636EFA"), use_container_width=True)

st.markdown("---")

# -----------------------------------------------------------------------------
# [섹션 2] 국내주식 선물 외국인 매수 동향
# -----------------------------------------------------------------------------
st.subheader("💼 외국인 선물 수급 및 시장 주도 상태")

foreign_futures_net =
