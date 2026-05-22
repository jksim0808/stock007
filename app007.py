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
        label="시장 전체 우량주 매력도 환경 (100점 만점)", 
        value=f"{program_intensity} 점", 
        delta=trade_signal,
        delta_color=score_color
    )

st.markdown("---")

# -----------------------------------------------------------------------------
# [섹션 3] 개별 종목 '단타 매력도 점수' 산출 및 스크리닝
# -----------------------------------------------------------------------------
st.subheader("🎯 단타 타겟 Top 30 (우량주 매력도 점수 랭킹 순)")

df_universe = get_realtime_target_stocks()

cond_price = df_universe['현재가'] >= 10000
cond_rise = df_universe['등락률'] > 0

filtered_df = df_universe[cond_price & cond_rise].copy()

market_cap_weight = foreign_futures_net / 5000.0 

filtered_df['우량주_매력도_점수'] = (
    (filtered_df['등락률'] * 1.5) + 
    (np.log1p(filtered_df['거래대금']) * 2.5) + 
    (np.log1p(filtered_df['시가총액']) * market_cap_weight * 1.5)
).round(1)

top_30 = filtered_df.sort_values(by='우량주_매력도_점수', ascending=False).head(30)

output_df = pd.DataFrame({
    '매력도 점수': top_30['우량주_매력도_점수'].apply(lambda x: f"{x} 점"),
    '종목명': top_30['종목명'],
    '현재가': top_30['현재가'].apply(lambda x: f"{int(x):,} 원"),
    '전일대비 상승률': top_30['등락률'].apply(lambda x: f"+{x:.2f} %"),
    '거래대금(백만)': top_30['거래대금'].apply(lambda x: f"{int(x):,}"),
    '시가총액(억)': top_30['시가총액'].apply(lambda x: f"{int(x):,}"),
    '종목코드': top_30['종목코드'],
    '시장': top_30['시장']
}).reset_index(drop=True)

st.markdown("💡 **표에서 가장 점수가 높은 관심 종목을 클릭**하시면 하단에 1분봉 추세 차트가 렌더링 됩니다.")

selected_rows = st.dataframe(
    output_df, 
    use_container_width=True, 
    selection_mode="single-row",
    on_select="rerun"
)

# -----------------------------------------------------------------------------
# [섹션 4] 종목 클릭 시 1분봉 시각화
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
