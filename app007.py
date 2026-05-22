import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# ==========================================
# 1. 페이지 설정
# ==========================================
st.set_page_config(page_title="국내주식 단타 대시보드", layout="wide")
st.title("📈 실시간 단타 종목 예측 대시보드")
st.caption("데이터 출처: Yahoo Finance, Naver Finance (15분 지연될 수 있습니다)")

# ==========================================
# 2. 데이터 수집 함수 (캐싱 적용)
# ==========================================
@st.cache_data(ttl=60)
def get_market_data():
    """코스피, 코스닥, 환율 당일 데이터 가져오기"""
    tickers = {"KOSPI": "^KS11", "KOSDAQ": "^KQ11", "USD/KRW": "KRW=X"}
    data = {}
    for name, ticker in tickers.items():
        # 1일치 데이터를 5분 간격으로 가져옴
        df = yf.download(ticker, period="1d", interval="5m", progress=False)
        data[name] = df
    return data

@st.cache_data(ttl=60)
def get_foreigner_futures():
    """
    외국인 국내주식 선물 순매수 비용 스크래핑 (네이버 금융)
    * 웹구조 변경 시 수정이 필요할 수 있습니다.
    """
    try:
        url = "https://finance.naver.com/sise/"
        res = requests.get(url)
        soup = BeautifulSoup(res.text, 'html.parser')
        # 네이버 금융 메인에서 외국인 선물 순매수 데이터 추출 (CSS 선택자는 상황에 따라 변동 가능)
        # 여기서는 안정적인 데모를 위해 스크래핑 로직 골격과 대체 난수를 사용합니다.
        # 실제 환경에서는 증권사 API 사용을 강력히 권장합니다.
        
        # 임의의 시뮬레이션 값 (실제 연결 시 위 soup 객체에서 파싱한 값을 float로 변환하여 return)
        net_buy = np.random.uniform(-5000, 5000) 
        return net_buy
    except Exception as e:
        return 0.0

@st.cache_data(ttl=60)
def get_top_stocks():
    """네이버 금융 거래대금 상위 종목 스크래핑 및 필터링"""
    url = "https://finance.naver.com/sise/sise_quant.naver"
    res = requests.get(url)
    
    # HTML에서 테이블 읽기
    dfs = pd.read_html(res.text, encoding='euc-kr')
    df = dfs[1].dropna(how='all')  # 빈 행 제거
    
    # 컬럼 정리
    df = df[['종목명', '현재가', '전일비', '등락률', '거래량', '거래대금']]
    for col in ['현재가', '전일비', '거래량', '거래대금']:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce')
    df['등락률'] = pd.to_numeric(df['등락률'].astype(str).str.replace('%', ''), errors='coerce')
    
    # 1. 5000원 이상 종목 필터링
    df = df[df['현재가'] >= 5000]
    
    # 2. 상승 종목 필터링 (등락률 > 0)
    df = df[df['등락률'] > 0]
    
    # 3. 거래대금 많은 순 정렬
    df = df.sort_values(by='거래대금', ascending=False)
    
    # 4. 사이드카 타지 않은 종목 (공공 API로 실시간 확인이 어려워 여기서는 모두 False로 가정)
    df['사이드카'] = "정상"
    
    # 30개 추출
    df = df.head(30).copy()
    
    # 5. 금일 상승 예측치 (%) - 머신러닝 모델의 predict() 결과를 넣는 자리
    # 데모를 위해 등락률과 거래대금을 기반으로 한 가중치 난수를 부여
    np.random.seed(datetime.now().second)
    df['상승예측(%)'] = (df['등락률'] * 0.5) + np.random.uniform(1.0, 15.0, size=len(df))
    df['상승예측(%)'] = df['상승예측(%)'].round(2)
    
    # 예측률 순으로 최종 정렬
    df = df.sort_values(by='상승예측(%)', ascending=False).reset_index(drop=True)
    
    # 전일비교 포맷팅
    df['전일비교'] = df['등락률'].apply(lambda x: f"▲ {x}%" if x > 0 else f"▼ {x}%")
    
    return df[['종목명', '현재가', '전일비교', '등락률', '상승예측(%)']]

# ==========================================
# 3. 상단 차트 렌더링 (코스피 / 코스닥 / 환율)
# ==========================================
market_data = get_market_data()

col1, col2, col3 = st.columns(3)

def draw_mini_chart(df, title):
    fig = go.Figure(go.Scatter(x=df.index, y=df['Close'], mode='lines', line=dict(color='#FF5733', width=2)))
    fig.update_layout(title=title, height=250, margin=dict(l=0, r=0, t=30, b=0), 
                      xaxis_visible=False, yaxis_visible=False, plot_bgcolor='rgba(0,0,0,0)')
    return fig

with col1:
    if not market_data["KOSPI"].empty:
        st.plotly_chart(draw_mini_chart(market_data["KOSPI"], "KOSPI"), use_container_width=True)
with col2:
    if not market_data["KOSDAQ"].empty:
        st.plotly_chart(draw_mini_chart(market_data["KOSDAQ"], "KOSDAQ"), use_container_width=True)
with col3:
    if not market_data["USD/KRW"].empty:
        st.plotly_chart(draw_mini_chart(market_data["USD/KRW"], "USD/KRW 환율"), use_container_width=True)

# ==========================================
# 4. 외국인 선물 순매수 동향
# ==========================================
st.markdown("---")
foreign_futures = get_foreigner_futures()
color = "red" if foreign_futures > 0 else "blue"
sign = "+" if foreign_futures > 0 else ""

st.subheader("🌐 외국인 국내주식 선물 동향")
st.markdown(f"**현재 매수 비용:** <span style='color:{color}; font-size:24px; font-weight:bold;'>{sign}{foreign_futures:,.0f} 억원</span>", unsafe_allow_html=True)
if foreign_futures < 0:
    st.caption("⚠️ 외국인 선물 순매도 진행 중")

# ==========================================
# 5. 상승 예측 30개 종목 리스트 (클릭 이벤트 포함)
# ==========================================
st.markdown("---")
st.subheader("🔥 당일 단타 추천 종목 (상승 예측순 Top 30)")
st.write("종목을 클릭하면 하단에 일일 주식 진행 차트가 나타납니다.")

top_stocks = get_top_stocks()

# Streamlit 1.35 이상부터 지원하는 DataFrame Row Selection
event = st.dataframe(
    top_stocks,
    use_container_width=True,
    hide_index=True,
    selection_mode="single_row",
    on_select="rerun"
)

# ==========================================
# 6. 클릭한 종목의 일일 진행 차트
# ==========================================
if event.selection.rows:
    selected_idx = event.selection.rows[0]
    selected_stock = top_stocks.iloc[selected_idx]['종목명']
    
    st.markdown("---")
    st.subheader(f"📊 {selected_stock} - 당일 진행 차트")
    st.info("실제 환경에서는 증권사 API를 통해 1분/3분봉 데이터를 가져와야 합니다. 아래는 예시 캔들스틱 차트입니다.")
    
    # 캔들스틱 차트 생성을 위한 임의의 1분봉 데이터 생성
    times = pd.date_range(start="09:00", end="15:30", freq="1min")
    open_p = np.random.normal(loc=5000, scale=20, size=len(times))
    close_p = open_p + np.random.normal(loc=0, scale=10, size=len(times))
    high_p = np.maximum(open_p, close_p) + np.random.uniform(0, 10, size=len(times))
    low_p = np.minimum(open_p, close_p) - np.random.uniform(0, 10, size=len(times))
    
    fig_stock = go.Figure(data=[go.Candlestick(
        x=times, open=open_p, high=high_p, low=low_p, close=close_p,
        increasing_line_color='red', decreasing_line_color='blue'
    )])
    
    fig_stock.update_layout(height=400, margin=dict(l=20, r=20, t=30, b=20), xaxis_rangeslider_visible=False)
    st.plotly_chart(fig_stock, use_container_width=True)
