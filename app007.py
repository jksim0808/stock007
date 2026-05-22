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
# 1. 데이터 로드 함수 (네이버 스크래핑 -> KRX 전 종목 데이터로 전면 교체)
# -----------------------------------------------------------------------------
@st.cache_data(ttl=60)
def get_market_indices():
    """코스피, 코스닥, 원달러 환율 최근 한 달 데이터 가져오기"""
    today = datetime.now(KST).strftime('%Y-%m-%d')
    start_date = (datetime.now(KST) - timedelta(days=30)).strftime('%Y-%m-%d')
    
    kospi = fdr.DataReader('KS11', start_date, today)
    kosdaq = fdr.DataReader('KQ11', start_date, today)
    usd_krw = fdr.DataReader('USD/KRW', start_date, today)
    return kospi, kosdaq, usd_krw

@st.cache_data(ttl=30)
def get_realtime_target_stocks():
    """KRX 전체 종목을 훑어서 누락되는 주도주가 없게 세팅 (거래대금 중심)"""
    # fdr을 통해 국내 코스피/코스닥 2,700여 개 전 종목 리스트 확보
    df_all = fdr.StockListing('KRX')
    
    # 단타에 필요한 핵심 데이터만 추출
    df_all = df_all[['Name', 'Code', 'Market', 'Close', 'ChgRate', 'Amount']].copy()
    
    # 컬럼명 직관적으로 변경
    df_all.rename(columns={
        'Name': '종목명',
        'Code': '종목코드',
        'Market': '시장',
        'Close': '현재가',
        'ChgRate': '등락률',
        'Amount': '거래대금'
    }, inplace=True)
    
    # 거래대금이 '원' 단위로 나오므로 가독성을 위해 '백만 원' 단위로 변환
    df_all['거래대금'] = df_all['거래대금'] / 1000000
    df_all = df_all.dropna(subset=['현재가', '거래대금', '등락률'])
    
    return df_all

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
# [섹션 2] 국내주식 선물 외국인 매수 동향 및 우량주 매력도
# -----------------------------------------------------------------------------
st.subheader("💼 외국인 선물 수급 및 우량주 단타 지수")

# 실시간 선물 동향 API 연동 전까지 테스트용 시뮬레이션 데이터 구동
foreign_futures_net = np.random.randint(-5000, 5000)

if foreign_futures_net >= 0:
    program_intensity = min(100, int(foreign_futures_net / 50))
    trade_signal = "🚀 우량주 단타 적극 추천 (바스켓 매수 유입)"
    delta_msg = "매수 우위 (시장 주도)"
    score_color = "normal"
else:
    program_intensity = max(0, 100 - min(100, int(abs(foreign_futures_net) / 50)))
    trade_signal = "⚠️ 대형주 단타 자제 (프로그램 매물 압력)"
    delta_msg = "매도 우위 (시장 압박)"
    score_color = "inverse"

col_m1, col_m2 = st.columns(2)
with col_m1:
    st.metric(
        label="외국인 주식선물 순매수 금액", 
        value=f"{foreign_futures_net:,} 억 원", 
        delta=delta_msg, 
        delta_color=score_color
    )
with col_m2:
    st.metric(
        label="대형 우량주 단타 매력도 점수 (100점 만점)", 
        value=f"{program_intensity} 점", 
        delta=trade_signal,
        delta_color=score_color
    )

st.markdown("💡 **활용법:** 매력도 점수가 **70점 이상**일 때 아래 스캐너에 잡히는 우량주를 집중적으로 공략하세요!")
st.markdown("---")

# -----------------------------------------------------------------------------
# [섹션 3] 거래대금 중심 타겟 스크리닝 (현재가 10,000원 이상 전체 대상)
# -----------------------------------------------------------------------------
st.subheader("🎯 단타 타겟 Top 30 (현재가 10,000원 이상 & 거래대금 폭발 종목)")

try:
    df_universe = get_realtime_target_stocks()
    
    cond_price = df_universe['현재가'] >= 10000
    cond_rise = df_universe['등락률'] > 0
    df_universe['Sidecar'] = False 
    cond_sidecar = df_universe['Sidecar'] == False
    
    filtered_df = df_universe[cond_price & cond_rise & cond_sidecar].copy()
    
    # 예측 스코어 로직 변경: 상승률보다 '뭉칫돈(거래대금)'에 가중치를 더 많이 부여 (삼아알미늄 등 포착 용도)
    filtered_df['예측_상승_Score'] = (filtered_df['등락률'] * 0.4 + np.log1p(filtered_df['거래
