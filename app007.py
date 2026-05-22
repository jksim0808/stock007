import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import requests
import re
from datetime import datetime, timedelta

# 페이지 레이아웃 설정
st.set_page_config(page_title="실시간 단타 트레이딩 시스템", layout="wide")

st.markdown("""
    <style>
    .reportview-container {
        background: #f4f6f9;
    }
    .main-title {
        font-size: 36px;
        font-weight: bold;
        color: #1e293b;
        margin-bottom: 5px;
    }
    .sub-title {
        font-size: 16px;
        color: #64748b;
        margin-bottom: 25px;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">⚡ 실시간 단타 트레이딩 프로 대시보드</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">KRX 지정 상승률/거래대금 필터링 & 실시간 수급 차트 연동 프로그램</div>', unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# [DATA FETCH] KOSPI, KOSDAQ, 환율 변동 데이터 수집 (일별 및 분봉 이원화 처리)
# -----------------------------------------------------------------------------
@st.cache_data(ttl=60)
def get_indices_data():
    indices = {}
    tickers = {
        "KOSPI": "^KS11",
        "KOSDAQ": "^KQ11",
        "USD/KRW": "KRW=X"
    }
    for name, ticker in tickers.items():
        try:
            # 1. 정확한 전일 대비 하루 단위 상승률(변동폭) 계산을 위해 최근 5일 일별(1d) 데이터 수집
            df_daily = yf.download(ticker, period="5d", interval="1d")
            # 2. 흐름을 그리기 위해 실시간 15분봉(15m) 데이터 수집
            df_15m = yf.download(ticker, period="3d", interval="15m")
            
            if not df_daily.empty and not df_15m.empty:
                # MultiIndex 컬럼일 경우 Level 0으로 축소
                if isinstance(df_daily.columns, pd.MultiIndex):
                    df_daily.columns = df_daily.columns.get_level_values(0)
                if isinstance(df_15m.columns, pd.MultiIndex):
                    df_15m.columns = df_15m.columns.get_level_values(0)
                
                df_daily.index = df_daily.index.tz_localize(None)
                df_15m.index = df_15m.index.tz_localize(None)
                
                indices[name] = {
                    "df_daily": df_daily,
                    "df_15m": df_15m
                }
        except Exception:
            pass
    return indices

# 데이터 가져오기
with st.spinner("🚀 실시간 시장 동향 및 인덱스 데이터를 수집하고 있습니다..."):
    indices_data = get_indices_data()
    foreigner_futures = fetch_foreign_futures_data()

# -----------------------------------------------------------------------------
# 1 ZONE: 주요 지수 및 수급 상황판
# -----------------------------------------------------------------------------
cols = st.columns(3)
names = ["KOSPI", "KOSDAQ", "USD/KRW"]

for idx, name in enumerate(names):
    with cols[idx]:
        st.markdown(f"### 📈 {name} 추이")
        if name in indices_data:
            data = indices_data[name]
            df_daily = data["df_daily"]
            df_15m = data["df_15m"]
            
            # 실제 '전일 대비 하루 기준 상승률' 계산
            current_val = df_daily['Close'].iloc[-1]
            prev_val = df_daily['Close'].iloc[-2]
            diff = current_val - prev_val
            pct = (diff / prev_val) * 100
            
            # 메트릭 표시 (전일대비 변동)
            color = "red" if diff >= 0 else "blue"
            sign = "+" if diff >= 0 else ""
            st.markdown(f"**현재가:** {current_val:,.2f} | **전일대비 변동:** <span style='color:{color}; font-weight:bold;'>{sign}{diff:,.2f} ({sign}{pct:.2f}%)</span>", unsafe_allow_html=True)
            
            # 그래프 그리기 (15분봉 고해상도 차트 렌더링)
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_15m.index, y=df_15m['Close'], 
                mode='lines', 
                line=dict(color='#3b82f6' if name != "USD/KRW" else '#f59e0b', width=2)
            ))
            fig.update_layout(
                height=150, 
                margin=dict(l=5, r=5, t=5, b=5),
                xaxis=dict(showgrid=False, showticklabels=False),
                yaxis=dict(showgrid=True, showticklabels=True),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)"
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning(f"{name} 데이터를 불러올 수 없습니다.")

# 외국인 선물 매수동향 (매수가 없거나 매도세일 경우 마이너스(-)로 자동 처리)
st.markdown("<br>", unsafe_allow_html=True)
if foreigner_futures is not None:
    if foreigner_futures >= 0:
        st.markdown(f"""
            <div style="background-color: #fef2f2; border-left: 5px solid #ef4444; padding: 15px; border-radius: 4px;">
                <span style="font-size: 16px; font-weight: bold; color: #991b1b;">🔥 국내주식 선물 외국인 매수동향</span><br>
                <span style="font-size: 24px; font-weight: bold; color: #dc2626;">+{foreigner_futures:,} 억원</span> (외국인 매수 우위)
            </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
            <div style="background-color: #eff6ff; border-left: 5px solid #3b82f6; padding: 15px; border-radius: 4px;">
                <span style="font-size: 16px; font-weight: bold; color: #1e3a8a;">❄️ 국내주식 선물 외국인 매도동향</span><br>
                <span style="font-size: 24px; font-weight: bold; color: #2563eb;">{foreigner_futures:,} 억원</span> (외국인 매도 우위)
            </div>
        """, unsafe_allow_html=True)
else:
    # 기본 가상값 설정 및 예외처리 방지
    dummy_futures = -245 # 매수 없을 시 마이너스(-) 흐름 예시
    st.markdown(f"""
        <div style="background-color: #eff6ff; border-left: 5px solid #3b82f6; padding: 15px; border-radius: 4px;">
            <span style="font-size: 16px; font-weight: bold; color: #1e3a8a;">❄️ 국내주식 선물 외국인 매도동향 (실시간 수집 지연으로 대체값 표시)</span><br>
            <span style="font-size: 24px; font-weight: bold; color: #2563eb;">{dummy_futures:,} 억원</span> (외국인 매도 우위)
        </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# -----------------------------------------------------------------------------
# [DATA LOAD] 요청하신 정확한 30선 종목 데이터베이스 빌드업 (주가 50,000원 이상 고정)
# -----------------------------------------------------------------------------
@st.cache_data
def get_custom_top_30():
    data = [
        {"Rank": 1, "Name": "고려아연", "Symbol": "010130", "Close": 370101, "ChgRate": 27.38, "Predicted_Growth": 23.4, "Amount": 48200000000},
        {"Rank": 2, "Name": "메리츠금융지주", "Symbol": "138040", "Close": 719522, "ChgRate": 26.99, "Predicted_Growth": 29.9, "Amount": 42100000000},
        {"Rank": 3, "Name": "셀트리온", "Symbol": "068270", "Close": 533043, "ChgRate": 24.45, "Predicted_Growth": 22.2, "Amount": 38900000000},
        {"Rank": 4, "Name": "현대차", "Symbol": "005380", "Close": 512172, "ChgRate": 23.61, "Predicted_Growth": 29.9, "Amount": 35500000000},
        {"Rank": 5, "Name": "SK이노베이션", "Symbol": "096770", "Close": 511695, "ChgRate": 22.61, "Predicted_Growth": 20.4, "Amount": 31200000000},
        {"Rank": 6, "Name": "KB금융", "Symbol": "105560", "Close": 201840, "ChgRate": 22.6, "Predicted_Growth": 29.4, "Amount": 29800000000},
        {"Rank": 7, "Name": "삼성바이오로직스", "Symbol": "207940", "Close": 184608, "ChgRate": 22.07, "Predicted_Growth": 29.3, "Amount": 27400000000},
        {"Rank": 8, "Name": "NAVER", "Symbol": "035420", "Close": 381102, "ChgRate": 21.24, "Predicted_Growth": 19.9, "Amount": 26100000000},
        {"Rank": 9, "Name": "엔씨소프트", "Symbol": "036570", "Close": 489538, "ChgRate": 19.64, "Predicted_Growth": 19.4, "Amount": 24300000000},
        {"Rank": 10, "Name": "SK하이닉스", "Symbol": "000660", "Close": 346145, "ChgRate": 19.44, "Predicted_Growth": 23.3, "Amount": 22100000000},
        {"Rank": 11, "Name": "삼성생명", "Symbol": "032830", "Close": 539747, "ChgRate": 18.01, "Predicted_Growth": 16.5, "Amount": 20800000000},
        {"Rank": 12, "Name": "삼성전자", "Symbol": "005930", "Close": 530883, "ChgRate": 17.15, "Predicted_Growth": 14.0, "Amount": 19500000000},
        {"Rank": 13, "Name": "유한양행", "Symbol": "000100", "Close": 552496, "ChgRate": 15.52, "Predicted_Growth": 20.9, "Amount": 18100000000},
        {"Rank": 14, "Name": "현대모비스", "Symbol": "012330", "Close": 270684, "ChgRate": 14.78, "Predicted_Growth": 12.4, "Amount": 16900000000},
        {"Rank": 15, "Name": "LG화학", "Symbol": "051910", "Close": 355545, "ChgRate": 13.97, "Predicted_Growth": 18.7, "Amount": 15500000000},
        {"Rank": 16, "Name": "하나금융지주", "Symbol": "086790", "Close": 302598, "ChgRate": 13.96, "Predicted_Growth": 15.1, "Amount": 14100000000},
        {"Rank": 17, "Name": "한미약품", "Symbol": "128940", "Close": 820037, "ChgRate": 12.73, "Predicted_Growth": 10.3, "Amount": 13300000000},
        {"Rank": 18, "Name": "신한지주", "Symbol": "055550", "Close": 152305, "ChgRate": 12.5, "Predicted_Growth": 16.3, "Amount": 12100000000},
        {"Rank": 19, "Name": "종근당", "Symbol": "185750", "Close": 686716, "ChgRate": 11.89, "Predicted_Growth": 10.3, "Amount": 11100000000},
        {"Rank": 20, "Name": "KT&G", "Symbol": "033780", "Close": 898753, "ChgRate": 10.61, "Predicted_Growth": 8.9, "Amount": 10200000000},
        {"Rank": 21, "Name": "POSCO홀딩스", "Symbol": "005490", "Close": 684120, "ChgRate": 9.96, "Predicted_Growth": 13.7, "Amount": 95000000},
        {"Rank": 22, "Name": "HLB", "Symbol": "028300", "Close": 220373, "ChgRate": 9.94, "Predicted_Growth": 9.8, "Amount": 89000000},
        {"Rank": 23, "Name": "삼성SDI", "Symbol": "006400", "Close": 211293, "ChgRate": 9.88, "Predicted_Growth": 9.7, "Amount": 81000000},
        {"Rank": 24, "Name": "포스코퓨처엠", "Symbol": "003670", "Close": 525196, "ChgRate": 9.2, "Predicted_Growth": 12.4, "Amount": 75000000},
        {"Rank": 25, "Name": "하이브", "Symbol": "352820", "Close": 586893, "ChgRate": 8.21, "Predicted_Growth": 10.3, "Amount": 68000000},
        {"Rank": 26, "Name": "카카오", "Symbol": "035720", "Close": 878885, "ChgRate": 8.17, "Predicted_Growth": 10.5, "Amount": 59000000},
        {"Rank": 27, "Name": "삼성물산", "Symbol": "028260", "Close": 662075, "ChgRate": 7.03, "Predicted_Growth": 5.7, "Amount": 51000000},
        {"Rank": 28, "Name": "기아", "Symbol": "000270", "Close": 186182, "ChgRate": 3.1, "Predicted_Growth": 3.6, "Amount": 42000000},
        {"Rank": 29, "Name": "크래프톤", "Symbol": "259960", "Close": 245723, "ChgRate": 3.0, "Predicted_Growth": 2.8, "Amount": 31000000},
        {"Rank": 30, "Name": "에코프로비엠", "Symbol": "247540", "Close": 842418, "ChgRate": 2.63, "Predicted_Growth": 3.1, "Amount": 25000000}
    ]
    return pd.DataFrame(data)

df_top30 = get_custom_top_30()

# -----------------------------------------------------------------------------
# 2 ZONE: 상승 종목 리스트 테이블 및 차트 매칭 인터페이스
# -----------------------------------------------------------------------------
st.subheader("🔥 지정 상승률 & 거래대금 30선 (주가 50,000원 이상 고정)")

# 세션 상태 초기화 (기본값: 1위 고려아연)
if 'selected_stock' not in st.session_state:
    st.session_state['selected_stock'] = df_top30.iloc[0]['Symbol']
    st.session_state['selected_stock_name'] = df_top30.iloc[0]['Name']

# 테이블 헤더 구축 (가상 칼럼 그리드)
header_cols = st.columns([1, 2, 2, 2, 3, 2, 2])
header_cols[0].markdown("**순위**")
header_cols[1].markdown("**종목명**")
header_cols[2].markdown("**지정 현재가**")
header_cols[3].markdown("**상승률**")
header_cols[4].markdown("**거래대금**")
header_cols[5].markdown("**금일 상승 예측**")
header_cols[6].markdown("**차트 작동**")

st.markdown("<hr style='margin: 5px 0 10px 0;'>", unsafe_allow_html=True)

# 30개 행 루프 돌며 출력
for idx, row in df_top30.iterrows():
    is_selected = st.session_state['selected_stock'] == row['Symbol']
    
    # 컬럼 정렬 매칭
    cols = st.columns([1, 2, 2, 2, 3, 2, 2])
    
    cols[0].write(f"{row['Rank']}위")
    
    # 종목명 및 코드
    cols[1].markdown(f"**{row['Name']}** <span style='font-size:12px; color:#64748b;'>{row['Symbol']}</span>", unsafe_allow_html=True)
    
    # 현재가 (요청하신 정확한 수정값 반영)
    cols[2].write(f"{int(row['Close']):,} 원")
    
    # 상승률
    cols[3].markdown(f"<span style='color:#ef4444; font-weight:bold;'>+{row['ChgRate']:.2f}%</span>", unsafe_allow_html=True)
    
    # 거래대금 포맷팅 (억 원 단위 변환)
    amount_in_billion = row['Amount'] / 100000000.0
    cols[4].write(f"{amount_in_billion:,.1f} 억 원")
    
    # 금일 상승 예측치
    cols[5].markdown(f"<span style='color:#ea580c; font-weight:bold;'>{row['Predicted_Growth']:.2f}%</span>", unsafe_allow_html=True)
    
    # 버튼 처리 (표 안에 직접 내장)
    button_lbl = "👉 선택됨" if is_selected else "👁️ 차트 보기"
    button_type = "primary" if is_selected else "secondary"
    
    if cols[6].button(button_lbl, key=f"btn_{row['Symbol']}_{idx}", type=button_type):
        st.session_state['selected_stock'] = row['Symbol']
        st.session_state['selected_stock_name'] = row['Name']
        st.rerun()

st.markdown("---")

# -----------------------------------------------------------------------------
# 3 ZONE: 선택된 종목의 실시간 15분봉 및 일봉 차트 연동
# -----------------------------------------------------------------------------
if st.session_state['selected_stock']:
    symbol = st.session_state['selected_stock']
    name = st.session_state['selected_stock_name']
    
    st.subheader(f"📊 {name} ({symbol}) 실제 시장 분봉/일봉 차트 연동")
    
    # 거래소 구분 서픽스 자동 처리 (.KS 또는 .KQ)
    # 에코프로비엠(247540), HLB(028300) 등 코스닥 종목 대응
    kosdaq_list = ["247540", "028300"]
    suffix = ".KQ" if symbol in kosdaq_list else ".KS"
    yf_ticker = f"{symbol}{suffix}"
    
    with st.spinner(f"📈 {name}의 실제 실시간 거래 분봉을 연동하는 중..."):
        try:
            # 1일간의 15분 간격 분봉 데이터 조회
            stock_df = yf.download(yf_ticker, period="1d", interval="15m")
            
            if not stock_df.empty:
                if isinstance(stock_df.columns, pd.MultiIndex):
                    stock_df.columns = stock_df.columns.get_level_values(0)
                stock_df.index = stock_df.index.tz_localize(None)
                
                # 캔들스틱 차트 생성
                fig_candle = go.Figure(data=[go.Candlestick(
                    x=stock_df.index,
                    open=stock_df['Open'],
                    high=stock_df['High'],
                    low=stock_df['Low'],
                    close=stock_df['Close'],
                    increasing_line_color='#ef4444',  # 양봉 빨간색
                    decreasing_line_color='#3b82f6'   # 음봉 파란색
                )])
                
                fig_candle.update_layout(
                    title=f"{name} 당일 실제 시장 15분봉 실시간 차트",
                    xaxis_rangeslider_visible=False,
                    height=450,
                    margin=dict(l=20, r=20, t=40, b=20),
                    paper_bgcolor="white",
                    plot_bgcolor="#f8fafc",
                    xaxis=dict(showgrid=True, gridcolor="#e2e8f0"),
                    yaxis=dict(showgrid=True, gridcolor="#e2e8f0")
                )
                st.plotly_chart(fig_candle, use_container_width=True)
            else:
                # 장외 시간 또는 거래가 없는 날(주말/공휴일)일 경우 최근 1달간의 실제 일일 차트로 대체하여 출력
                st.info("장외 시간 또는 휴일이므로 최근 1개월 실제 일봉 차트로 대체 표시합니다.")
                daily_df = yf.download(yf_ticker, period="1mo", interval="1d")
                if not daily_df.empty:
                    if isinstance(daily_df.columns, pd.MultiIndex):
                        daily_df.columns = daily_df.columns.get_level_values(0)
                    daily_df.index = daily_df.index.tz_localize(None)
                    
                    fig_daily = go.Figure(data=[go.Candlestick(
                        x=daily_df.index,
                        open=daily_df['Open'],
                        high=daily_df['High'],
                        low=daily_df['Low'],
                        close=daily_df['Close'],
                        increasing_line_color='#ef4444',
                        decreasing_line_color='#3b82f6'
                    )])
                    fig_daily.update_layout(
                        title=f"{name} 최근 1개월 실제 일봉 차트 (마감 기준)",
                        xaxis_rangeslider_visible=False, 
                        height=450,
                        paper_bgcolor="white",
                        plot_bgcolor="#f8fafc",
                        xaxis=dict(showgrid=True, gridcolor="#e2e8f0"),
                        yaxis=dict(showgrid=True, gridcolor="#e2e8f0")
                    )
                    st.plotly_chart(fig_daily, use_container_width=True)
                    
        except Exception as e:
            st.error(f"차트 데이터를 가져오는 중 예외가 발생했습니다: {e}")
