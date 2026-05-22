import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import FinanceDataReader as fdr
import yfinance as yf
import requests
from io import StringIO
from datetime import datetime, timedelta

# 페이지 설정
st.set_page_config(layout="wide", page_title="국내주식 실시간 단타 스캐너")
st.title("🚀 실시간 단타 및 시장 동향 대시보드")

# -----------------------------------------------------------------------------
# 1. 데이터 로드 함수 (캐싱으로 로딩 속도 최적화)
# -----------------------------------------------------------------------------
@st.cache_data(ttl=60)
def get_market_indices():
    """코스피, 코스닥, 원달러 환율 최근 한 달 데이터 가져오기"""
    today = datetime.today().strftime('%Y-%m-%d')
    start_date = (datetime.today() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    kospi = fdr.DataReader('KS11', start_date, today)
    kosdaq = fdr.DataReader('KQ11', start_date, today)
    usd_krw = fdr.DataReader('USD/KRW', start_date, today)
    return kospi, kosdaq, usd_krw

@st.cache_data(ttl=30)
def get_realtime_target_stocks():
    """네이버 금융 거래상위 데이터를 파싱하고 종목코드와 매핑"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    # 1. 네이버 금융 코스피/코스닥 거래상위 파싱 (StringIO 에러 해결 적용)
    url_kospi = "https://finance.naver.com/sise/sise_quant.naver"
    url_kosdaq = "https://finance.naver.com/sise/sise_quant.naver?sosok=1"
    
    res_k = requests.get(url_kospi, headers=headers)
    res_q = requests.get(url_kosdaq, headers=headers)
    
    df_kospi = pd.read_html(StringIO(res_k.text))[1]
    df_kosdaq = pd.read_html(StringIO(res_q.text))[1]
    
    df_all = pd.concat([df_kospi, df_kosdaq])
    
    # 불필요한 결측치(선 등) 제거
    df_all = df_all.dropna(subset=['종목명'])
    
    # 데이터 전처리 (문자열 -> 숫자 변환)
    df_all['현재가'] = df_all['현재가'].astype(str).str.replace(',', '').astype(float)
    df_all['거래대금'] = df_all['거래대금'].astype(str).str.replace(',', '').astype(float)
    df_all['등락률'] = df_all['등락률'].astype(str).str.replace('%', '').str.replace('+', '').astype(float)
    
    # 2. FinanceDataReader를 이용해 종목코드(Code) 및 시장구분(Market) 맵핑
    krx_info = fdr.StockListing('KRX')[['Name', 'Code', 'Market']]
    
    # 데이터프레임 병합 (종목명 기준)
    df_merged = pd.merge(df_all, krx_info, left_on='종목명', right_on='Name', how='inner')
    
    return df_merged

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
# [섹션 2] 국내주식 선물 외국인 매수비용
# -----------------------------------------------------------------------------
st.subheader("💼 국내주식 선물 외국인 매수 동향")

# 실시간 선물 수급은 증권사 API가 필요하여 데모 데이터로 유지 (로직은 동일하게 마이너스 처리)
foreign_futures_net = np.random.randint(-2000, 2000) # 단위: 억원

if foreign_futures_net >= 0:
    st.metric(label="외국인 주식선물 순매수 금액", value=f"{foreign_futures_net:,} 억 원", delta="매수 우위")
else:
    st.metric(label="외국인 주식선물 순매수 금액", value=f"{foreign_futures_net:,} 억 원", delta="매도 우위", delta_color="inverse")

st.markdown("---")

# -----------------------------------------------------------------------------
# [섹션 3] 네이버 기반 조건 검색 및 상승 예측 순위
# -----------------------------------------------------------------------------
st.subheader("🎯 단타 타겟 Top 30 (현재가 5천원 이상 & 상승 종목 & 거래대금 랭킹)")

try:
    df_universe = get_realtime_target_stocks()
    
    # 조건 1: 주가 5,000원 이상
    # 조건 2: 당일 상승 종목 (등락률 > 0)
    # 조건 3: 사이드카 발동 여부 (API 없이 알기 어려우므로 기본 정상(False)으로 처리)
    cond_price = df_universe['현재가'] >= 5000
    cond_rise = df_universe['등락률'] > 0
    df_universe['Sidecar'] = False 
    cond_sidecar = df_universe['Sidecar'] == False
    
    filtered_df = df_universe[cond_price & cond_rise & cond_sidecar].copy()
    
    # 정렬: 상승률이 높은 순 -> 거래대금이 많은 순
    filtered_df = filtered_df.sort_values(by=['등락률', '거래대금'], ascending=[False, False])
    
    # 상승 예측 스코어 산출 (등락률과 거래대금을 조합한 가상 예측치 - 본인만의 로직으로 수정 가능)
    # 거래대금이 강할수록 상승 예측에 가중치 부여
    filtered_df['예측_상승_Score'] = (filtered_df['등락률'] * 0.7 + np.log1p(filtered_df['거래대금']) * 0.3)
    
    # 예측 점수순 30개 추출
    top_30 = filtered_df.sort_values(by='예측_상승_Score', ascending=False).head(30)
    
    # UI 출력을 위한 데이터 정제
    output_df = pd.DataFrame({
        '종목명': top_30['종목명'],
        '종목코드': top_30['Code'],
        '시장': top_30['Market'],
        '현재가': top_30['현재가'].apply(lambda x: f"{int(x):,} 원"),
        '전일비교 상승비율': top_30['등락률'].apply(lambda x: f"+{x:.2f} %"),
        '금일 상승 예측(추정)': top_30['예측_상승_Score'].apply(lambda x: f"+{x:.2f} %"),
        '거래대금(백만)': top_30['거래대금'].apply(lambda x: f"{int(x):,}")
    }).reset_index(drop=True)

    st.markdown("💡 **아래 표에서 관심 있는 종목을 클릭(행 선택)**하시면 하단에 당일 추세 차트가 렌더링 됩니다.")
    
    selected_rows = st.dataframe(
        output_df, 
        use_container_width=True, 
        selection_mode="single-row",
        on_select="rerun"
    )

    # -----------------------------------------------------------------------------
    # [섹션 4] 종목 클릭 시 일일 진행 차트 시각화
    # -----------------------------------------------------------------------------
    st.markdown("---")
    st.subheader("📈 선택 종목 일일 추세(분봉) 차트")

    # 선택된 행 인덱스 가져오기 (기본값 0)
    selected_idx = 0
    if selected_rows and len(selected_rows.get("selection", {}).get("rows", [])) > 0:
        selected_idx = selected_rows["selection"]["rows"][0]

    if not output_df.empty:
        target_code = output_df.iloc[selected_idx]['종목코드']
        target_name = output_df.iloc[selected_idx]['종목명']
        target_market = output_df.iloc[selected_idx]['시장']
        
        st.write(f"현재 선택된 종목: **{target_name} ({target_code})**")
        
        # yfinance 티커(Ticker) 포맷 맞추기 (코스피는 .KS, 코스닥은 .KQ)
        ticker_symbol = f"{target_code}.KS" if 'KOSPI' in target_market else f"{target_code}.KQ"
        
        with st.spinner("차트 데이터를 불러오는 중입니다..."):
            stock_ticker = yf.Ticker(ticker_symbol)
            # 최근 5일, 15분 간격의 당일 추세 데이터 가져오기
            hist = stock_ticker.history(period="5d", interval="15m")
            
            if not hist.empty:
                fig_stock = go.Figure(data=[go.Candlestick(
                    x=hist.index,
                    open=hist['Open'], high=hist['High'],
                    low=hist['Low'], close=hist['Close'],
                    increasing_line_color='#FF4B4B', decreasing_line_color='#00CC96'
                )])
                fig_stock.update_layout(
                    title=f"{target_name} 최근 15분봉 진행 차트",
                    xaxis_rangeslider_visible=False,
                    height=450,
                    template="plotly_dark",
                    margin=dict(l=20, r=20, t=40, b=20)
                )
                st.plotly_chart(fig_stock, use_container_width=True)
            else:
                st.warning("Yahoo Finance에서 해당 종목의 분봉 데이터를 제공하지 않습니다. (최근 신규 상장 종목이거나 서버 지연일 수 있습니다.)")
    else:
        st.warning("현재 스크리닝된 상승 종목이 없습니다.")

except Exception as e:
    st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {e}")
