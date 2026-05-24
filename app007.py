import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import json
from datetime import datetime, timedelta, timezone

# 거시경제 지표용 라이브러리 추가
import FinanceDataReader as fdr 

# -----------------------------------------------------------------------------
# [설정] 한국투자증권 API KEY (Streamlit Secrets 활용)
# -----------------------------------------------------------------------------
try:
    KIS_APP_KEY = st.secrets["KIS_APP_KEY"]
    KIS_APP_SECRET = st.secrets["KIS_APP_SECRET"]
    
    # 변수명 통일 (코드 내부에서는 APP_KEY, APP_SECRET 사용)
    APP_KEY = KIS_APP_KEY
    APP_SECRET = KIS_APP_SECRET
except KeyError:
    st.error("⚠️ Streamlit secrets에 'KIS_APP_KEY' 또는 'KIS_APP_SECRET'이 설정되지 않았습니다.")
    st.info("로컬 환경의 경우 프로젝트 폴더 내 `.streamlit/secrets.toml` 파일을 확인해주세요.")
    st.stop()

URL_BASE = "https://openapi.koreainvestment.com:9443" # 실전투자 URL

# 페이지 설정
st.set_page_config(layout="wide", page_title="국내주식 실시간 단타 스캐너 (KIS API)")
st.title("🚀 실시간 단타 및 시장 동향 대시보드")

# 한국 시간(KST) 설정
KST = timezone(timedelta(hours=9))

# -----------------------------------------------------------------------------
# 1. KIS API 인증 및 토큰 발급
# -----------------------------------------------------------------------------
@st.cache_resource(ttl=3600*20) # 토큰 유효기간(24시간) 고려 20시간 캐싱
def get_access_token():
    headers = {"content-type": "application/json"}
    body = {
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET
    }
    url = f"{URL_BASE}/oauth2/tokenP"
    try:
        res = requests.post(url, headers=headers, data=json.dumps(body))
        res.raise_for_status()
        return res.json()["access_token"]
    except Exception as e:
        st.error(f"⚠️ 토큰 발급 실패: {e}")
        return None

def get_common_headers(tr_id):
    token = get_access_token()
    return {
        "Content-Type": "application/json",
        "authorization": f"Bearer {token}",
        "appKey": APP_KEY,
        "appSecret": APP_SECRET,
        "tr_id": tr_id
    }

# -----------------------------------------------------------------------------
# 2. 데이터 로드 함수
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
def get_kis_top_volume_stocks():
    """
    한국투자증권 '거래대금 상위' API를 호출하여 시장의 주도주를 스크리닝 (ETF, ETN, 스팩 제외)
    """
    url = f"{URL_BASE}/uapi/domestic-stock/v1/quotations/volume-rank"
    headers = get_common_headers("FHPST01710000")
    
    params = {
        "FID_COND_MRKT_DIV_CODE": "J", 
        "FID_COND_SCR_DIV_CODE": "20171",
        "FID_INPUT_ISCD": "0000",
        "FID_DIV_CLS_CODE": "1", # 1: 보통주(ETF 제외)
        "FID_BLNG_CLS_CODE": "0",
        "FID_TRGT_CLS_CODE": "111111111", 
        "FID_TRGT_EXLS_CLS_CODE": "111111", 
        "FID_INPUT_PRICE_1": "1000", # 1000원 이상
        "FID_INPUT_PRICE_2": "1000000",
        "FID_VOL_CNT": "",
        "FID_INPUT_DATE_1": ""
    }
    
    try:
        res = requests.get(url, headers=headers, params=params)
        res.raise_for_status()
        data = res.json()
        
        if data['rt_cd'] != '0':
            st.error(f"⚠️ KIS API 에러: {data['msg1']}")
            return pd.DataFrame()
            
        items = data['output']
        
        df = pd.DataFrame(items)
        df = df[['hts_kor_isnm', 'mksc_shrn_iscd', 'stck_prpr', 'prdy_ctrt', 'acml_tr_pbmn']]
        df.columns = ['종목명', '종목코드', '현재가', '등락률', '거래대금']
        
        # 2차 텍스트 필터링 (완벽한 차단)
        exclude_keywords = ['KODEX', 'TIGER', 'KBSTAR', 'ACE', 'ARIRANG', 'HANARO', 'KOSEF', 'SOL', 'TIMEFOLIO', 'WOORI', '히어로즈', '마이티', '스팩', 'ETN']
        pattern = '|'.join(exclude_keywords)
        df = df[~df['종목명'].str.contains(pattern, case=False, regex=True)]
        
        df['시장'] = 'KRX'
        df['현재가'] = pd.to_numeric(df['현재가'], errors='coerce')
        df['등락률'] = pd.to_numeric(df['등락률'], errors='coerce')
        df['거래대금'] = pd.to_numeric(df['거래대금'], errors='coerce') / 1000000 
        df['시가총액'] = 10000 # KIS API에 시총이 없으므로 가중치용 기본값
        
        return df.dropna()
    except Exception as e:
        st.error(f"⚠️ KIS 데이터 호출 실패: {e}")
        return pd.DataFrame()

# -----------------------------------------------------------------------------
# [섹션 1] 지수 및 환율 차트
# -----------------------------------------------------------------------------
st.subheader("📊 주요 시장 지수 및 환율 동향")
kospi, kosdaq, usd_krw = get_market_indices()

col1, col2, col3 = st.columns(3)

def create_chart(df, title, color):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df['Close'], mode='lines', name=title, line=dict(color=color, width=2)))
    fig.update_layout(title=title, height=250, margin=dict(l=20, r=20, t=40, b=20), template="plotly_dark")
    return fig

if not kospi.empty:
    with col1: st.plotly_chart(create_chart(kospi, "KOSPI 지수", "#FF4B4B"), use_container_width=True)
if not kosdaq.empty:
    with col2: st.plotly_chart(create_chart(kosdaq, "KOSDAQ 지수", "#00CC96"), use_container_width=True)
if not usd_krw.empty:
    with col3: st.plotly_chart(create_chart(usd_krw, "원/달러 환율", "#636EFA"), use_container_width=True)

st.markdown("---")

# -----------------------------------------------------------------------------
# [섹션 2] 외국인 수급 및 시장 상태
# -----------------------------------------------------------------------------
st.subheader("💼 외국인 선물 수급 및 시장 주도 상태")

if 'foreign_futures_net' not in st.session_state:
    st.session_state.foreign_futures_net = np.random.randint(-5000, 5000)

foreign_futures_net = st.session_state.foreign_futures_net

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
    st.metric(label="외국인 주식선물 순매수 금액 (시뮬레이션)", value=f"{foreign_futures_net:,} 억 원", delta=delta_msg, delta_color=score_color)
with col_m2:
    st.metric(label="시장 전체 우량주 매력도 환경 (100점 만점)", value=f"{program_intensity} 점", delta=trade_signal, delta_color=score_color)

if st.button("🔄 실시간 데이터 업데이트 (수동)"):
    st.session_state.foreign_futures_net = np.random.randint(-5000, 5000)
    get_kis_top_volume_stocks.clear()
    st.rerun()

st.markdown("---")

# -----------------------------------------------------------------------------
# [섹션 3] 개별 종목 스크리닝
# -----------------------------------------------------------------------------
st.subheader("🎯 단타 타겟 Top 30 (우량주 매력도 점수 랭킹 순)")

df_universe = get_kis_top_volume_stocks()

if not df_universe.empty:
    cond_price = df_universe['현재가'] >= 10000
    cond_rise = df_universe['등락률'] > 0
    filtered_df = df_universe[cond_price & cond_rise].copy()

    filtered_df['우량주_매력도_점수'] = (
        (filtered_df['등락률'] * 1.5) + 
        (np.log1p(filtered_df['거래대금']) * 2.5)
    ).round(1)

    top_30 = filtered_df.sort_values(by='우량주_매력도_점수', ascending=False).head(30)

    output_df = pd.DataFrame({
        '매력도 점수': top_30['우량주_매력도_점수'].apply(lambda x: f"{x} 점"),
        '종목명': top_30['종목명'],
        '현재가': top_30['현재가'].apply(lambda x: f"{int(x):,} 원"),
        '전일대비 상승률': top_30['등락률'].apply(lambda x: f"+{x:.2f} %"),
        '거래대금(백만)': top_30['거래대금'].apply(lambda x: f"{int(x):,}"),
        '종목코드': top_30['종목코드'],
        '시장': top_30['시장']
    }).reset_index(drop=True)

    st.markdown("💡 **표에서 관심 있는 종목의 행을 클릭**하시면 하단에 1분봉 차트가 생성됩니다.")

    selected_rows = st.dataframe(
        output_df, 
        use_container_width=True, 
        selection_mode="single-row",
        on_select="rerun"
    )
else:
    st.error("데이터를 불러오지 못했습니다. 장외 시간이거나 API 호출 초과일 수 있습니다.")
    output_df = pd.DataFrame()

# -----------------------------------------------------------------------------
# [섹션 4] 종목 클릭 시 KIS 1분봉 시각화
# -----------------------------------------------------------------------------
st.markdown("---")

selected_idx = 0
if hasattr(selected_rows, 'selection') and len(selected_rows.selection.rows) > 0:
    selected_idx = selected_rows.selection.rows[0]

if not output_df.empty:
    target_code = output_df.iloc[selected_idx]['종목코드']
    target_name = output_df.iloc[selected_idx]['종목명']
    target_price = output_df.iloc[selected_idx]['현재가']
    target_change = output_df.iloc[selected_idx]['전일대비 상승률']
    target_vol = output_df.iloc[selected_idx]['거래대금(백만)']
    
    st.markdown(f"""
    <div style='padding: 10px 0; border-bottom: 1px solid #ddd; margin-bottom: 15px;'>
        <span style='font-size: 20px; font-weight: bold;'>{target_name}</span> 
        <span style='font-size: 14px; font-weight: bold;'>{target_price}</span>
        <span style='font-size: 14px; color: #e12929; margin-left: 5px;'>{target_change}</span>
        <span style='font-size: 14px; color: #888; margin-left: 10px;'>거래대금 {target_vol}백만</span>
    </div>
    """, unsafe_allow_html=True)
    
    with st.spinner(f"[{target_name}] KIS 1분봉 데이터를 불러오는 중입니다..."):
        url = f"{URL_BASE}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
        headers = get_common_headers("FHKST03010200")
        
        now_time = datetime.now(KST).strftime("%H%M%S")
        params = {
            "FID_ETC_CLS_CODE": "",
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": target_code,
            "FID_INPUT_HOUR_1": now_time,
            "FID_PW_DATA_INCU_YN": "Y"
        }
        
        try:
            res = requests.get(url, headers=headers, params=params)
            res_data = res.json()
            
            if res_data['rt_cd'] == '0' and 'output2' in res_data:
                min_data = res_data['output2'][::-1] 
                
                times = [f"{m['stck_bsop_date']} {m['stck_cntg_hour']}" for m in min_data]
                closes = [float(m['stck_prpr']) for m in min_data]
                
                date_idx = pd.to_datetime(times, format="%Y%m%d %H%M%S")
                
                df_min = pd.DataFrame({"Close": closes}, index=date_idx)
                df_min = df_min[df_min['Close'] > 0]
                
                if not df_min.empty:
                    min_price = df_min['Close'].min()
                    max_price = df_min['Close'].max()
                    price_margin = (max_price - min_price) * 0.1 if max_price != min_price else min_price * 0.01
                    
                    fig_stock = go.Figure()
                    fig_stock.add_trace(go.Scatter(
                        x=df_min.index, y=df_min['Close'], mode='lines', 
                        line=dict(color='#4c6198', width=1.5), name="현재가"
                    ))
                    
                    fig_stock.update_layout(
                        template="plotly_white", height=500, margin=dict(l=10, r=60, t=20, b=20),
                        xaxis=dict(showgrid=True, gridcolor='#f0f0f0', type='date', tickformat='%H:%M'),
                        yaxis=dict(side='right', showgrid=True, gridcolor='#f0f0f0', tickformat=',', range=[min_price - price_margin, max_price + price_margin]),
                        hovermode='x unified'
                    )
                    st.plotly_chart(fig_stock, use_container_width=True)
                else:
                    st.warning("유효한 분봉 데이터가 없습니다.")
            else:
                st.error(f"분봉 조회 실패: {res_data.get('msg1', '알 수 없는 오류')}")
        except Exception as e:
            st.error(f"분봉 API 호출 중 에러 발생: {e}")
