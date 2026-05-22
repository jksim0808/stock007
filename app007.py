import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone

# 1. 페이지 레이아웃 및 KST 표준시 설정
st.set_page_config(page_title="KST 실시간 네이버 금융 단타 트레이딩 시스템", layout="wide")

# KST 시간 도출
KST = timezone(timedelta(hours=9))
kst_now = datetime.now(KST)

# 스타일 커스터마이징
st.markdown("""
    <style>
    .reportview-container {
        background: #f8fafc;
    }
    .main-title {
        font-size: 34px;
        font-weight: 800;
        color: #0f172a;
        margin-bottom: 2px;
    }
    .sub-title {
        font-size: 15px;
        color: #475569;
        margin-bottom: 20px;
    }
    .status-badge {
        background-color: #e2e8f0;
        padding: 5px 12px;
        border-radius: 15px;
        font-size: 13px;
        font-weight: bold;
        color: #334155;
        display: inline-block;
        margin-bottom: 20px;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">⚡ KST 실시간 네이버 금융 단타 트레이딩 대시보드</div>', unsafe_allow_html=True)
st.markdown(f'<div class="status-badge">⏰ 한국 표준시(KST) 실시간 동기화 중 : {kst_now.strftime("%Y-%m-%d %H:%M:%S")}</div>', unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# [DATA FETCH] 네이버 fchart API 기반 차트 데이터 수집
# -----------------------------------------------------------------------------
def get_naver_chart_df(symbol, timeframe="day", count=100):
    """
    네이버 금융 차트 API로부터 데이터를 가져와 DataFrame으로 가공합니다.
    """
    url = f"https://fchart.stock.naver.com/sise.nhn?symbol={symbol}&timeframe={timeframe}&count={count}&requestType=0"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
    }
    try:
        res = requests.get(url, headers=headers, timeout=5)
        root = ET.fromstring(res.text)
        data_list = []
        for item in root.findall(".//item"):
            data_str = item.get("data")
            parts = data_str.split("|")
            if len(parts) >= 6:
                date_val = parts[0]
                if len(date_val) == 8:
                    dt = pd.to_datetime(date_val, format="%Y%m%d")
                elif len(date_val) >= 12:
                    dt = pd.to_datetime(date_val[:12], format="%Y%m%d%H%M")
                else:
                    dt = pd.to_datetime(date_val)
                
                data_list.append({
                    "Date": dt,
                    "Open": float(parts[1]),
                    "High": float(parts[2]),
                    "Low": float(parts[3]),
                    "Close": float(parts[4]),
                    "Volume": float(parts[5])
                })
        df = pd.DataFrame(data_list)
        if not df.empty:
            df.set_index("Date", inplace=True)
        return df
    except Exception:
        return pd.DataFrame()

# -----------------------------------------------------------------------------
# [DATA FETCH] 네이버 실시간 지수 & 환율 수집
# -----------------------------------------------------------------------------
@st.cache_data(ttl=10)
def get_indices_data():
    indices = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
    }
    raw_indices = []
    try:
        res_idx = requests.get("https://polling.finance.naver.com/api/realtime/world/index/KOSPI,KOSDAQ", headers=headers, timeout=5)
        res_ex = requests.get("https://polling.finance.naver.com/api/realtime/world/market/FX_USDKRW", headers=headers, timeout=5)
        idx_data = res_idx.json()['result']['areas'][0]['datas']
        ex_data = res_ex.json()['result']['areas'][0]['datas']
        raw_indices = idx_data + ex_data
    except Exception:
        pass

    targets = {"KOSPI": "KOSPI", "KOSDAQ": "KOSDAQ", "USD/KRW": "FX_USDKRW"}
    
    for name, sym in targets.items():
        cur_price, change_rate, diff = 0.0, 0.0, 0.0
        found = False
        
        for r in raw_indices:
            if r.get('cd') == sym:
                cur_price = float(str(r.get('nv', 0)).replace(",", ""))
                change_rate = float(r.get('cr', 0))
                diff = float(str(r.get('cv', 0)).replace(",", ""))
                rf = r.get('rf', '3')
                if rf in ['4', '5']:
                    change_rate = -abs(change_rate)
                    diff = -abs(diff)
                found = True
                break
        
        # 15분 단위 실시간 차트 수집
        df_15m = get_naver_chart_df(sym, timeframe="15", count=60)
        
        # 장외 시간 등으로 백오프 연산이 필요할 경우 최근 일봉 변동률 적용
        if not found:
            df_daily = get_naver_chart_df(sym, timeframe="day", count=5)
            if not df_daily.empty and len(df_daily) >= 2:
                cur_price = df_daily['Close'].iloc[-1]
                prev_price = df_daily['Close'].iloc[-2]
                diff = cur_price - prev_price
                change_rate = (diff / prev_price) * 100
        
        indices[name] = {
            "current": cur_price,
            "diff": diff,
            "pct": change_rate,
            "df_15m": df_15m
        }
        
    return indices

# -----------------------------------------------------------------------------
# [DATA FETCH] 외국인 선물 순매수동향 크롤링
# -----------------------------------------------------------------------------
def fetch_foreign_futures_data():
    try:
        url = "https://finance.naver.com/sise/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            deal_table = soup.find("table", {"class": "tbl_deal"})
            if deal_table:
                rows = deal_table.find_all("tr")
                for row in rows:
                    if "선물" in row.text:
                        cols = row.find_all("td")
                        # 외국인 순매수동향 추출
                        foreigner_span = cols[0].find("span")
                        if foreigner_span:
                            sign = "-" if "blue" in foreigner_span.get("class", []) else "+"
                            val_text = foreigner_span.text.replace(",", "").replace("+", "").replace("-", "").strip()
                            val = int(val_text)
                            return -val if sign == "-" else val
    except Exception:
        pass
    return None

# -----------------------------------------------------------------------------
# [DATA LOAD] 요청하신 30개 우수 종목의 상승률 및 현재가 고정 데이터 로드
# -----------------------------------------------------------------------------
# 데이터 세션 상태 로딩
with st.spinner("🚀 KST 한국시간 기준 증시 데이터를 실시간으로 수집하고 있습니다..."):
    indices_data = get_indices_data()
    foreigner_futures = fetch_foreign_futures_data()
    df_top30 = get_custom_top_30()

# -----------------------------------------------------------------------------
# 1 ZONE: 코스피 / 코스닥 / 환율 실시간 차트 & 선물 수급 현황
# -----------------------------------------------------------------------------
cols = st.columns(3)
names = ["KOSPI", "KOSDAQ", "USD/KRW"]

for idx, name in enumerate(names):
    with cols[idx]:
        st.markdown(f"### 📈 {name} 추이 (KST)")
        if name in indices_data:
            data = indices_data[name]
            current_val = data["current"]
            diff = data["diff"]
            pct = data["pct"]
            df_15m = data["df_15m"]
            
            color = "#ef4444" if diff >= 0 else "#2563eb"
            sign = "+" if diff >= 0 else ""
            st.markdown(f"**현재가:** {current_val:,.2f} | **전일대비:** <span style='color:{color}; font-weight:bold;'>{sign}{diff:,.2f} ({sign}{pct:.2f}%)</span>", unsafe_allow_html=True)
            
            # 고해상도 15분 선차트
            if not df_15m.empty:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=df_15m.index, y=df_15m['Close'], 
                    mode='lines', 
                    line=dict(color=color, width=2)
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
                st.caption("차트를 연동 중입니다.")
        else:
            st.warning(f"{name} 실시간 데이터를 수집할 수 없습니다.")

st.markdown("<br>", unsafe_allow_html=True)

# 선물 수급 상태 표시 (매수 없을 시 마이너스로 표현)
if foreigner_futures is not None:
    if foreigner_futures >= 0:
        st.markdown(f"""
            <div style="background-color: #fff5f5; border-left: 5px solid #ef4444; padding: 15px; border-radius: 4px;">
                <span style="font-size: 14px; font-weight: bold; color: #b91c1c;">🔥 국내주식 선물 외국인 매수동향 (KST)</span><br>
                <span style="font-size: 24px; font-weight: 800; color: #dc2626;">+{foreigner_futures:,} 억원</span> (외국인 매수 유입 중)
            </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
            <div style="background-color: #f0f7ff; border-left: 5px solid #2563eb; padding: 15px; border-radius: 4px;">
                <span style="font-size: 14px; font-weight: bold; color: #1e40af;">❄️ 국내주식 선물 외국인 매도동향 (KST)</span><br>
                <span style="font-size: 24px; font-weight: 800; color: #2563eb;">{foreigner_futures:,} 억원</span> (외국인 매도 세력 - 마이너스 상태)
            </div>
        """, unsafe_allow_html=True)
else:
    st.info("실시간 외국인 선물 거래동향 정보를 수집하고 있습니다.")

st.markdown("---")

# -----------------------------------------------------------------------------
# 2 ZONE: [상승률 & 거래대금] 실시간 통합 데이터 표 구현 (현재가 5,000원 이상 고정 데이터)
# -----------------------------------------------------------------------------
st.subheader("🔥 실시간 상승률 & 거래대금 상위 30 종목 (현재가 5,000원 이상)")
st.caption("우측의 '👁️ 차트 보기' 버튼을 클릭하면 실시간 일일 분봉/일봉 차트가 아래 화면에 갱신됩니다.")

# 기본 세션 초기화
if 'selected_stock' not in st.session_state and not df_top30.empty:
    st.session_state['selected_stock'] = df_top30.iloc[0]['Symbol']
    st.session_state['selected_stock_name'] = df_top30.iloc[0]['Name']



# -----------------------------------------------------------------------------
# 3 ZONE: 선택된 주 종목 실시간 차트 연동 연출 (KST)
# -----------------------------------------------------------------------------
if st.session_state.get('selected_stock'):
    symbol = st.session_state['selected_stock']
    name = st.session_state['selected_stock_name']
    
    st.subheader(f"📊 {name} ({symbol}) 실시간 일일 차트 분석")
    
    with st.spinner(f"📈 {name} 종목의 15분 단위 KST 실시간 차트를 가져오고 있습니다..."):
        # 실시간 15분 단위 봉 데이터 파싱
        stock_df = get_naver_chart_df(symbol, timeframe="15", count=45)
        
        # 거래시간 외 또는 주말일 경우 일봉으로 자동 전환
        if stock_df.empty:
            st.info("장외 시간 또는 실시간 거래 비활성화 상태입니다. 최근 일봉 차트로 전환합니다.")
            stock_df = get_naver_chart_df(symbol, timeframe="day", count=30)
            
        if not stock_df.empty:
            fig_candle = go.Figure(data=[go.Candlestick(
                x=stock_df.index,
                open=stock_df['Open'],
                high=stock_df['High'],
                low=stock_df['Low'],
                close=stock_df['Close'],
                increasing_line_color='#ef4444',
                decreasing_line_color='#2563eb'
            )])
            
            fig_candle.update_layout(
                title=f"{name} 당일 실시간 캔들스틱 차트 (KST 한국 표준시 기준)",
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
            st.warning("선택된 종목의 차트 데이터를 불러올 수 없습니다. 다시 시도해 주세요.")
