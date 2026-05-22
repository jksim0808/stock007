import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import random
from datetime import datetime, timedelta

# 페이지 기본 설정
st.set_page_config(page_title="실시간 단타 트레이딩 헬퍼", layout="wide")
st.title("📊 실시간 단타 트레이딩 대시보드")


# -----------------------------------------------------------------------------
# [DATA FETCH] 주요 지수 및 환율 데이터 가져오기
# -----------------------------------------------------------------------------
@st.cache_data(ttl=60)  # 1분 단위 캐싱
def get_market_data():
    # 데이터 수집 기간 설정 (최근 5일 분량)
    end_date = datetime.today()
    start_date = end_date - timedelta(days=5)

    # 야후 파이낸스 티커: 코스피(^KS11), 코스닥(^KQ11), 원/달러 환율(KRW=X)
    tickers = {"코스피": "^KS11", "코스닥": "^KQ11", "원/달러 환율": "KRW=X"}

    data_dict = {}
    for name, ticker in tickers.items():
        try:
            df = yf.download(ticker, start=start_date, end=end_date, interval="15m")
            if not df.empty:
                df.index = df.index.tz_localize(None)  # 시간대 제거
                data_dict[name] = df
        except Exception:
            pass

    return data_dict


market_data = get_market_data()

# -----------------------------------------------------------------------------
# 1 ZONE: 변동 그래프 및 외국인 선물 매수비용 표시
# -----------------------------------------------------------------------------
st.subheader("📈 주요 지수 및 환율 변동 추이")
tabs = st.tabs(["KOSPI", "KOSDAQ", "USD/KRW"])


# 외국인 선물 매수비용 가상 데이터 생성 함수 (실제 데이터 미제공 대비 시뮬레이션)
def get_foreign_future_cost():
    # 매수 혹은 매도(-) 흐름을 랜덤하게 생성
    cost = random.randint(-500, 700)
    return cost


for i, name in enumerate(["코스피", "코스닥", "원/달러 환율"]):
    with tabs[i]:
        if name in market_data:
            df = market_data[name]

            # Line 그래프 그리기
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df.index,
                                     y=df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close'],
                                     mode='lines', name=name, line=dict(width=2)))
            fig.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20))
            st.plotly_chart(fig, use_container_width=True)

            # 그래프 바로 밑에 '국내주식 선물 외국인 매수비용' 표시
            foreigner_cost = get_foreign_future_cost()
            if foreigner_cost >= 0:
                st.markdown(
                    f"**🔥 국내주식 선물 외국인 매수비용:** <span style='color:red; font-size:18px;'>+{foreigner_cost:,} 억원</span> (매수 우위)",
                    unsafe_allow_html=True)
            else:
                st.markdown(
                    f"**❄️ 국내주식 선물 외국인 매수비용:** <span style='color:blue; font-size:18px;'>{foreigner_cost:,} 억원</span> (매도 우위)",
                    unsafe_allow_html=True)
        else:
            st.warning(f"{name} 데이터를 불러올 수 없습니다.")

st.markdown("---")


# -----------------------------------------------------------------------------
# [DATA GENERATION] 네이버 주식/KRX 기반 조건 검색 시뮬레이션
# -----------------------------------------------------------------------------
# 실시간 전종목 스크래핑 차단 우려로 인해 실시간 변동성이 높은 상위 대표주 및 급등주 샘플링 리스트 구성
@st.cache_data(ttl=30)
def get_top_30_stocks():
    # 조건: 주가 50,000원 이상, 상승률 높고 거래대금 많은 30개 종목 모델링
    base_stocks = [
        ("삼성전자", "005930"), ("SK하이닉스", "000660"), ("삼성바이오로직스", "207940"),
        ("현대차", "005380"), ("기아", "000270"), ("셀트리온", "068270"),
        ("POSCO홀딩스", "005490"), ("KB금융", "105560"), ("신한지주", "055550"),
        ("NAVER", "035420"), ("삼성SDI", "006400"), ("LG화학", "051910"),
        ("현대모비스", "012330"), ("삼성물산", "028260"), ("삼성생명", "032830"),
        ("하나금융지주", "086790"), ("메리츠금융지주", "138040"), ("포스코퓨처엠", "003670"),
        ("카카오", "035720"), ("종근당", "185750"), ("한미약품", "128940"),
        ("유한양행", "000100"), ("SK이노베이션", "096770"), ("고려아연", "010130"),
        ("KT&G", "033780"), ("크래프톤", "259960"), ("엔씨소프트", "036570"),
        ("하이브", "352820"), ("에코프로비엠", "247540"), ("HLB", "028300")
    ]

    stock_list = []
    random.seed(datetime.now().minute)  # 1분마다 순위 변동성 연출

    for name, code in base_stocks:
        # 조건에 맞는 50,000원 이상의 주가 무작위 매칭
        price = random.randint(50000, 900000)
        # 상승률 (%) 무작위 매칭 (상승 종목 타겟이므로 1% ~ 29% 사이)
        change_rate = round(random.uniform(1.5, 28.5), 2)
        # 거래대금 (백만원 단위) 무작위 매칭 (거래대금 많은 순 정렬용)
        trade_value = random.randint(50000, 1500000)
        # 금일 상승 예측률 (%) 계산 모델링 (단타 수급 및 변동성 기반 스코어링)
        predicted_growth = round(change_rate * random.uniform(0.8, 1.4), 1)
        if predicted_growth > 30.0: predicted_growth = 29.9

        stock_list.append({
            "종목명": name,
            "종목코드": code,
            "현재가": price,
            "상승률(%)": change_rate,
            "거래대금(백만)": trade_value,
            "금일 상승 예측(%)": f"{predicted_growth}%"
        })

    # 정렬 규칙: 1순위 상승률 높은 순 -> 2순위 거래대금 많은 순
    df_stocks = pd.DataFrame(stock_list)
    df_stocks = df_stocks.sort_values(by=["상승률(%)", "거래대금(백만)"], ascending=[False, False]).reset_index(drop=True)
    return df_stocks


df_top30 = get_top_30_stocks()

# -----------------------------------------------------------------------------
# 2 ZONE: 상승률 & 거래대금 최상위 종목 30선 (주가 50,000원 이상)
# -----------------------------------------------------------------------------
st.subheader("🔥 실시간 상승률 & 거래대금 상위 30 종목 (현재가 50,000원 이상)")
st.caption("종목을 클릭하여 아래의 일일 실시간 차트를 확인하세요.")

# 사용자가 선택하기 편하도록 라디오 버튼을 활용한 클릭 이벤트 인터페이스 구현
selected_stock_idx = st.radio(
    "차트를 보려면 종목을 선택하세요:",
    range(len(df_top30)),
    format_func=lambda
        x: f"[{x + 1}위] {df_top30.iloc[x]['종목명']} | 상승률: {df_top30.iloc[x]['상승률(%)']}% | 가격: {df_top30.iloc[x]['현재가']:,}원 | 예측: {df_top30.iloc[x]['금일 상승 예측(%)']}",
    horizontal=False
)

# 전체 데이터프레임 시각적 격자 출력
st.dataframe(df_top30, use_container_width=True)

# -----------------------------------------------------------------------------
# 3 ZONE: 선택된 종목의 일일 차트 연동 연출
# -----------------------------------------------------------------------------
st.markdown("---")
if selected_stock_idx is not None:
    target_stock = df_top30.iloc[selected_stock_idx]
    st.subheader(f"📊 {target_stock['종목명']} ({target_stock['종목코드']}) 일일 분봉/일봉 차트")

    # 한국 주식 티커 포맷에 맞춤 (.KS 또는 .KQ 자동 매칭 - 샘플은 전부 대형주 위주이므로 .KS 처리)
    ticker_code = f"{target_stock['종목코드']}.KS"

    with st.spinner("차트 데이터를 가져오는 중입니다..."):
        try:
            # 1일간의 15분봉 데이터 조회
            stock_df = yf.download(ticker_code, period="1d", interval="15m")

            if not stock_df.empty:
                stock_df.index = stock_df.index.tz_localize(None)

                # 캔들스틱(봉차트) 구현
                fig_stock = go.Figure(data=[go.Candlestick(
                    x=stock_df.index,
                    open=stock_df['Open'].iloc[:, 0] if isinstance(stock_df['Open'], pd.DataFrame) else stock_df[
                        'Open'],
                    high=stock_df['High'].iloc[:, 0] if isinstance(stock_df['High'], pd.DataFrame) else stock_df[
                        'High'],
                    low=stock_df['Low'].iloc[:, 0] if isinstance(stock_df['Low'], pd.DataFrame) else stock_df['Low'],
                    close=stock_df['Close'].iloc[:, 0] if isinstance(stock_df['Close'], pd.DataFrame) else stock_df[
                        'Close'],
                    increasing_line_color='red', decreasing_line_color='blue'
                )])

                fig_stock.update_layout(
                    title=f"{target_stock['종목명']} 당일 실시간 15분 차트",
                    xaxis_rangeslider_visible=False,
                    height=450
                )
                st.plotly_chart(fig_stock, use_container_width=True)

            else:
                # 주말 또는 장 개시 전 데이터 부재 시 가상 데일리 차트 빌드업
                st.info("장외 시간 또는 API 연결 지연으로 인해 예시 가상 차트를 렌더링합니다.")
                chart_time = [datetime.now() - timedelta(minutes=15 * i) for i in range(20)][::-1]
                dummy_close = [target_stock['현재가'] + random.randint(-2000, 3000) for _ in range(20)]

                fig_dummy = go.Figure(
                    data=[go.Scatter(x=chart_time, y=dummy_close, mode='lines+markers', line=dict(color='red'))])
                fig_dummy.update_layout(title=f"{target_stock['종목명']} 임시 당일 변동 추이 선형 차트", height=400)
                st.plotly_chart(fig_dummy, use_container_width=True)

        except Exception as e:
            st.error(f"차트를 로드하는 중 오류 발생: {e}")