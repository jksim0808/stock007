import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import FinanceDataReader as fdr
import yfinance as yf
from datetime import datetime, timedelta

# 페이지 기본 설정
st.set_page_config(layout="wide", page_title="국내주식 단타 스캐너")
st.title("🚀 실시간 단타 및 시장 동향 대시보드")

# -----------------------------------------------------------------------------
# 1. 데이터 로드 함수 (캐싱 처리로 속도 최적화)
# -----------------------------------------------------------------------------
@st.cache_data(ttl=60)  # 1분마다 데이터 갱신
def get_market_indices():
    """코스피, 코스닥, 원달러 환율 최근 30일 데이터 가져오기"""
    today = datetime.today().strftime('%Y-%m-%d')
    start_date = (datetime.today() - timedelta(days=45)).strftime('%Y-%m-%d')
    
    # 지수 및 환율 가져오기
    kospi = fdr.DataReader('KS11', start_date, today)
    kosdaq = fdr.DataReader('KQ11', start_date, today)
    usd_krw = fdr.DataReader('USD/KRW', start_date, today)
    
    return kospi, kosdaq, usd_krw

@st.cache_data(ttl=60)
def get_stock_universe():
    """KRX 전체 종목 시세 데이터 가져오기 (종목 스크리닝용)"""
    # 전일/금일 기준 대략적인 상승 종목 리스트 확보를 위해 KRX 전체 종목 조회
    df_krx = fdr.StockListing('KRX')
    # 예시용 더미 데이터 구성 (실제 실시간 조건 검색은 네이버 금융/KRX 스크래핑이나 증권사 API 권장)
    # 가상의 거래대금 및 전일대비 상승률 부여 (실제 운영시 라이브 데이터 바인딩 필요)
    np.random.seed(42)
    df_krx = df_krx[df_krx['Market'].isin(['KOSPI', 'KOSDAQ'])].copy()
    df_krx['Close'] = pd.to_numeric(df_krx['Close'], errors='coerce')
    df_krx['ChgRate'] = np.random.uniform(-5, 29.9, size=len(df_krx)) # 가상 상승률
    df_krx['VolumeValue'] = np.random.uniform(100, 50000, size=len(df_krx)) # 가상 거래대금 (억원)
    df_krx['Sidecar'] = np.random.choice([False, True], size=len(df_krx), p=[0.99, 0.01]) # 가상 사이드카 여부
    
    return df_krx

# -----------------------------------------------------------------------------
# [화면 레이아웃 1] 코스피 / 코스닥 / 환율 변동 그래프
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
# [화면 레이아웃 2] 국내주식 선물 외국인 매수비용 표시
# -----------------------------------------------------------------------------
st.subheader("💼 국내주식 선물 외국인 매수 동향")

# 실제 실시간 선물 수급은 증권사 API 연동이 필요하므로 오픈 소스 구현을 위한 예시 데이터 배치
# 매수가 없으면(순매도) 마이너스(-)로 표시되는 로직 반영
foreign_futures_net = np.random.randint(-1500, 2000) # 단위: 억원

if foreign_futures_net >= 0:
    st.metric(label="외국인 주식선물 순매수 금액", value=f"{foreign_futures_net:,} 억 원", delta="매수 우위 (정상)")
else:
    st.metric(label="외국인 주식선물 순매수 금액", value=f"{foreign_futures_net:,} 억 원", delta="매도 우위 (주의)", delta_color="inverse")

st.markdown("---")

# -----------------------------------------------------------------------------
# [화면 레이아웃 3] 조건 만족 30개 종목 스크리닝 및 상승 예측 순위
# -----------------------------------------------------------------------------
st.subheader("🎯 단타 타겟 Top 30 종목 (조건: 주가 5,000원 이상 & 사이드카 미발동)")

df_universe = get_stock_universe()

# 조건 필터링
# 1. 주가 5000원 이상
filtered_df = df_universe[df_universe['Close'] >= 5000].copy()
# 2. 사이드카 타지 않은 종목 (Sidecar == False)
filtered_df = filtered_df[filtered_df['Sidecar'] == False]
# 3. 상승 종목 중 (상승률 > 0)
filtered_df = filtered_df[filtered_df['ChgRate'] > 0]

# 정렬: 상승률 높은 순 & 거래대금 많은 순
filtered_df = filtered_df.sort_values(by=['ChgRate', 'VolumeValue'], ascending=[False, False])

# 자체 상승 예측 스코어 산출 알고리즘 (예시: 거래대금과 상승률의 가중합 조합)
# 실제 프로젝트 시 이곳에 자체 ML 모델(XGBoost 등)이나 계량 알고리즘 결과 대입
filtered_df['Predict_Rate'] = (filtered_df['ChgRate'] * 0.6 + (filtered_df['VolumeValue'] / 2000) * 0.4).round(2)

# 최종 예측 순위별 정렬 및 30개 추출
top_30 = filtered_df.sort_values(by='Predict_Rate', ascending=False).head(30)

# 출력용 컬럼 재정의 및 포맷팅
output_df = pd.DataFrame({
    '종목코드': top_30['Code'],
    '종목명': top_30['Name'],
    '현재가': top_30['Close'].map(lambda x: f"{int(x):,}원"),
    '전일비교 상승비율': top_30['ChgRate'].map(lambda x: f"+{x:.2f}%"),
    '금일 상승 예측 %': top_30['Predict_Rate'].map(lambda x: f"{x:.2f}%")
}).reset_index(drop=True)

st.markdown("💡 **아래 표에서 종목 행을 클릭**하시면 하단에 해당 종목의 최근 상세 차트가 표시됩니다.")

# Streamlit 데이터프레임의 인터랙티브 선택 기능(on_select) 활용
selected_rows = st.dataframe(
    output_df, 
    use_container_width=True, 
    selection_mode="single-row",
    on_select="rerun"
)

# -----------------------------------------------------------------------------
# [화면 레이아웃 4] 종목 클릭 시 일일 차트(최근 추세) 시각화
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader("📈 선택 종목 일일 진행 차트")

# 기본 선택값 설정 (선택이 없으면 1등 종목 표시)
selected_index = 0
if selected_rows and len(selected_rows.get("selection", {}).get("rows", [])) > 0:
    selected_index = selected_rows["selection"]["rows"][0]

target_code = output_df.iloc[selected_index]['종목코드']
target_name = output_df.iloc[selected_index]['종목명']

st.write(f"현재 선택된 종목: **{target_name} ({target_code})**")

# 실시간 분봉 대신 일차트 혹은 yfinance 기반 당일 추세를 그리기 위해 최근 5일 데이터 바인딩
# (실시간 초/분봉은 크레온/한국투자증권 웹소켓 연동이 필요합니다)
try:
    ticker_code = f"{target_code}.KS" if target_code.isdigit() else target_code
    # 코스닥 종목 예외처리 등은 실제 환경에 맞게 보완 가능 (.KQ)
    stock_detail = yf.Ticker(f"{target_code}.KS") 
    hist = stock_detail.history(period="5d", interval="15m") # 15분봉 데이터 시도
    
    if hist.empty:
        stock_detail = yf.Ticker(f"{target_code}.KQ")
        hist = stock_detail.history(period="5d", interval="15m")

    if not hist.empty:
        fig_stock = go.Figure(data=[go.Candlestick(
            x=hist.index,
            open=hist['Open'],
            high=hist['High'],
            low=hist['Low'],
            close=hist['Close'],
            increasing_line_color='red', decreasing_line_color='blue'
        )])
        fig_stock.update_layout(
            title=f"{target_name} 최근 15분봉 진행 차트",
            xaxis_rangeslider_visible=False,
            height=400,
            template="plotly_dark"
        )
        st.plotly_chart(fig_stock, use_container_width=True)
    else:
        st.warning("해당 종목의 당일 차트 데이터를 가져오지 못했습니다. (데이터 피드 미연결)")
except Exception as e:
    st.error(f"차트 로딩 중 오류 발생: {e}")import streamlit as st
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
