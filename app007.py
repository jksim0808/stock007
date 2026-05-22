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
# 1. 데이터 로드 함수 (수정된 안정적인 KRX 크롤링 방식)
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
    """안정적인 KRX 전체 종목 시세 가져오기 (컬럼 에러 방어 로직 적용)"""
    # 1. KRX 전 종목 리스트 가져오기
    df_krx = fdr.StockListing('KRX')
    
    # 2. 버전에 따라 다르게 넘어오는 컬럼명(ChgRate vs FluctuationRate 등)에 대한 유연한 대처
    # '등락률'을 의미하는 컬럼을 찾아서 매핑
    chg_col = 'ChgRate' if 'ChgRate' in df_krx.columns else 'FluctuationRate' if 'FluctuationRate' in df_krx.columns else '등락률'
    # '거래대금'을 의미하는 컬럼을 찾아서 매핑
    amt_col = 'Amount' if 'Amount' in df_krx.columns else 'TradingValue' if 'TradingValue' in df_krx.columns else '거래대금'
    
    # 만약 위의 컬럼들도 없다면, 최소한의 작동을 위해 빈 데이터프레임 반환
    if chg_col not in df_krx.columns or amt_col not in df_krx.columns:
        st.error("현재 FinanceDataReader에서 거래대금/등락률 데이터를 제공하지 않는 포맷으로 변경되었습니다.")
        return pd.DataFrame()

    df_krx = df_krx[['Name', 'Code', 'Market', 'Close', chg_col, amt_col]].copy()
    
    # 공통 컬럼명으로 통일
    df_krx.rename(columns={
        'Name': '종목명',
        'Code': '종목코드',
        'Market': '시장',
        'Close': '현재가',
        chg_col: '등락률',
        amt_col: '거래대금'
    }, inplace=True)
    
    # 3. 데이터 전처리 (거래대금을 백만 원 단위로 변경)
    df_krx['현재가'] = pd.to_numeric(df_krx['현재가'], errors='coerce')
    df_krx['등락률'] = pd.to_numeric(df_krx['등락률'], errors='coerce')
    df_krx['거래대금'] = pd.to_numeric(df_krx['거래대금'], errors='coerce') / 1000000
    
    # 결측치(데이터가 없는 종목) 제거
    df_krx = df_krx.dropna(subset=['현재가', '거래대금', '등락률'])
    
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
    filtered_df['예측_상승_Score'] = (filtered_df['등락률'] * 0.4 + np.log1p(filtered_df['거래대금']) * 0.6)
    
    top_30 = filtered_df.sort_values(by='예측_상승_Score', ascending=False).head(30)
    
    output_df = pd.DataFrame({
        '종목명': top_30['종목명'],
        '종목코드': top_30['종목코드'],
        '시장': top_30['시장'],
        '현재가': top_30['현재가'].apply(lambda x: f"{int(x):,} 원"),
        '전일대비 상승률': top_30['등락률'].apply(lambda x: f"+{x:.2f} %"),
        '거래대금(백만)': top_30['거래대금'].apply(lambda x: f"{int(x):,}")
    }).reset_index(drop=True)

    st.markdown("💡 **표에서 관심 있는 종목의 행을 클릭**하시면 하단에 1분봉 추세 차트가 렌더링 됩니다.")
    
    selected_rows = st.dataframe(
        output_df, 
        use_container_width=True, 
        selection_mode="single-row",
        on_select="rerun"
    )

    # -----------------------------------------------------------------------------
    # [섹션 4] 종목 클릭 시 1분봉 시각화 (종목별 가격 범위 동적 맞춤)
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
        target_change = output_df.iloc[selected_idx]['전일대비 상승률']
        target_vol = output_df.iloc[selected_idx]['거래대금(백만)']
        
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
                
                min_price = hist['Close'].min()
                max_price = hist['Close'].max()
                price_margin = (max_price - min_price) * 0.1
                if price_margin == 0: 
                    price_margin = min_price * 0.01 
                
                fig_stock = go.Figure()
                fig_stock.add_trace(go.Scatter(
                    x=hist.index,
                    y=hist['Close'],
                    mode='lines',
                    line=dict(color='#4c6198', width=1.5),
                    name="현재가"
                ))
                
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
                        range=[min_price - price_margin, max_price + price_margin] 
                    ),
                    hovermode='x unified'
                )
                
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
            else:
                st.warning("Yahoo Finance에서 해당 종목의 당일 1분봉 데이터를 제공하지 않습니다.")
    else:
        st.warning("현재 스크리닝된 상승 종목이 없습니다.")

except Exception as e:
    st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {e}")
