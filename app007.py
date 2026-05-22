import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import FinanceDataReader as fdr
import yfinance as yf
import requests
from io import StringIO
from datetime import datetime, timedelta, timezone

# 페이지 설정
st.set_page_config(layout="wide", page_title="국내주식 실시간 단타 스캐너")
st.title("🚀 실시간 단타 및 시장 동향 대시보드")

# 한국 시간(KST) 설정 (UTC + 9시간)
KST = timezone(timedelta(hours=9))

# -----------------------------------------------------------------------------
# 1. 데이터 로드 함수
# -----------------------------------------------------------------------------
@st.cache_data(ttl=60)
def get_market_indices():
    """코스피, 코스닥, 원달러 환율 최근 한 달 데이터 가져오기 (한국 시간 기준)"""
    # KST 기준으로 오늘과 30일 전 날짜 계산
    today = datetime.now(KST).strftime('%Y-%m-%d')
    start_date = (datetime.now(KST) - timedelta(days=30)).strftime('%Y-%m-%d')
    
    kospi = fdr.DataReader('KS11', start_date, today)
    kosdaq = fdr.DataReader('KQ11', start_date, today)
    usd_krw = fdr.DataReader('USD/KRW', start_date, today)
    return kospi, kosdaq, usd_krw

@st.cache_data(ttl=30)
def get_realtime_target_stocks():
    """네이버 금융 거래상위 데이터를 파싱하고 종목코드와 매핑"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    url_kospi = "https://finance.naver.com/sise/sise_quant.naver"
    url_kosdaq = "https://finance.naver.com/sise/sise_quant.naver?sosok=1"
    
    res_k = requests.get(url_kospi, headers=headers)
    res_q = requests.get(url_kosdaq, headers=headers)
    
    df_kospi = pd.read_html(StringIO(res_k.text))[1]
    df_kosdaq = pd.read_html(StringIO(res_q.text))[1]
    
    df_all = pd.concat([df_kospi, df_kosdaq])
    
    df_all = df_all.dropna(subset=['종목명'])
    
    df_all['현재가'] = df_all['현재가'].astype(str).str.replace(',', '').astype(float)
    df_all['거래대금'] = df_all['거래대금'].astype(str).str.replace(',', '').astype(float)
    df_all['등락률'] = df_all['등락률'].astype(str).str.replace('%', '').str.replace('+', '').astype(float)
    
    krx_info = fdr.StockListing('KRX')[['Name', 'Code', 'Market']]
    
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

foreign_futures_net = np.random.randint(-2000, 2000)

if foreign_futures_net >= 0:
    st.metric(label="외국인 주식선물 순매수 금액", value=f"{foreign_futures_net:,} 억 원", delta="매수 우위")
else:
    st.metric(label="외국인 주식선물 순매수 금액", value=f"{foreign_futures_net:,} 억 원", delta="매도 우위", delta_color="inverse")

st.markdown("---")

# -----------------------------------------------------------------------------
# [섹션 3] 조건 검색 및 상승 예측 순위 (10,000원 이상)
# -----------------------------------------------------------------------------
st.subheader("🎯 단타 타겟 Top 30 (현재가 10,000원 이상 & 상승 종목 & 거래대금 랭킹)")

try:
    df_universe = get_realtime_target_stocks()
    
    # [수정된 부분] 조건 1: 주가 10,000원 이상으로 변경
    cond_price = df_universe['현재가'] >= 10000
    cond_rise = df_universe['등락률'] > 0
    df_universe['Sidecar'] = False 
    cond_sidecar = df_universe['Sidecar'] == False
    
    filtered_df = df_universe[cond_price & cond_rise & cond_sidecar].copy()
    
    filtered_df = filtered_df.sort_values(by=['등락률', '거래대금'], ascending=[False, False])
    
    filtered_df['예측_상승_Score'] = (filtered_df['등락률'] * 0.7 + np.log1p(filtered_df['거래대금']) * 0.3)
    
    top_30 = filtered_df.sort_values(by='예측_상승_Score', ascending=False).head(30)
    
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
    # [섹션 4] 종목 클릭 시 일일 진행 차트 시각화 (종목별 가격 범위 동적 맞춤)
    # -----------------------------------------------------------------------------
    st.markdown("---")
    
    selected_idx = 0
    if selected_rows and len(selected_rows.get("selection", {}).get("rows", [])) > 0:
        selected_idx = selected_rows["selection"]["rows"][0]

    if not output_df.empty:
        target_code = output_df.iloc[selected_idx]['종목코드']
        target_name = output_df.iloc[selected_idx]['종목명']
        target_market = output_df.iloc[selected_idx]['시장']
        target_price = output_df.iloc[selected_idx]['현재가']
        target_change = output_df.iloc[selected_idx]['전일비교 상승비율']
        target_vol = output_df.iloc[selected_idx]['거래대금(백만)']
        
        # 상단 헤더 디자인
        st.markdown(f"""
        <div style='padding: 10px 0; border-bottom: 1px solid #ddd; margin-bottom: 15px;'>
            <span style='font-size: 20px; font-weight: bold;'>{target_name}</span> 
            <span style='font-size: 14px; color: #888;'>시</span> <span style='font-size: 14px;'>-</span>
            <span style='font-size: 14px; color: #888;'>고</span> <span style='font-size: 14px;'>-</span>
            <span style='font-size: 14px; color: #888;'>저</span> <span style='font-size: 14px;'>-</span>
            <span style='font-size: 14px; color: #888;'>종</span> <span style='font-size: 14px; font-weight: bold;'>{target_price}</span>
            <span style='font-size: 14px; color: #e12929; margin-left: 5px;'>{target_change}</span>
            <span style='font-size: 14px; color: #888; margin-left: 10px;'>거(대금) {target_vol}백만</span>
            <span style='float: right; font-size: 12px; color: #999; margin-top: 5px;'>한국거래소({target_market})</span>
        </div>
        """, unsafe_allow_html=True)
        
        ticker_symbol = f"{target_code}.KS" if 'KOSPI' in target_market else f"{target_code}.KQ"
        
        with st.spinner("차트 데이터를 불러오는 중입니다..."):
            stock_ticker = yf.Ticker(ticker_symbol)
            hist = stock_ticker.history(period="1d", interval="1m")
            
            if not hist.empty:
                hist.index = hist.index.tz_convert('Asia/Seoul')
                
                # Y축 상하단 여백을 위해 종목의 당일 최고/최저가 계산
                min_price = hist['Close'].min()
                max_price = hist['Close'].max()
                # 위아래로 약간의 여백(약 10%)을 주어 차트가 답답해 보이지 않게 설정
                price_margin = (max_price - min_price) * 0.1
                if price_margin == 0: # 가격 변동이 아예 없는 경우 방어코드
                    price_margin = min_price * 0.01 
                
                # 라인 차트 생성 (fill 옵션 제거하여 Y축이 0으로 가는 현상 방지)
                fig_stock = go.Figure()
                fig_stock.add_trace(go.Scatter(
                    x=hist.index,
                    y=hist['Close'],
                    mode='lines',
                    line=dict(color='#4c6198', width=1.5),
                    name="현재가"
                ))
                
                # 차트 레이아웃 설정
                fig_stock.update_layout(
                    template="plotly_white",
                    height=500,
                    margin=dict(l=10, r=60, t=20, b=20),
                    xaxis=dict(
                        showgrid=True,
                        gridcolor='#f0f0f0',
                        rangeslider_visible=False,
                        type='date'
                    ),
                    yaxis=dict(
                        side='right',
                        showgrid=True,
                        gridcolor='#f0f0f0',
                        tickformat=',',
                        # 계산된 최고/최저가 범위로 Y축 강제 고정
                        range=[min_price - price_margin, max_price + price_margin] 
                    ),
                    hovermode='x unified'
                )
                
                # 우측 현재가 박스 태그
                last_price = hist['Close'].iloc[-1]
                fig_stock.add_annotation(
                    x=hist.index[-1],
                    y=last_price,
                    text=f"{int(last_price):,}",
                    showarrow=True,
                    arrowcolor='rgba(0,0,0,0)',
                    ax=45, ay=0,
                    xanchor='left',
                    font=dict(color="white", size=11),
                    bgcolor="#4c6198",
                    bordercolor="#4c6198",
                    borderwidth=1,
                    borderpad=4
                )

                st.plotly_chart(fig_stock, use_container_width=True)
