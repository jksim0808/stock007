import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import FinanceDataReader as fdr
import requests
import json
from datetime import datetime, timedelta, timezone

# -----------------------------------------------------------------------------
# [설정] 한국투자증권 API 키 입력 (실제 발급받은 키로 변경하세요)
# -----------------------------------------------------------------------------
KIS_APP_KEY = "YOUR_APP_KEY_HERE"
KIS_APP_SECRET = "YOUR_APP_SECRET_HERE"

# 실전투자 URL: https://openapi.koreainvestment.com:9443
# 모의투자 URL: https://openapivts.koreainvestment.com:29443
URL_BASE = "https://openapi.koreainvestment.com:9443" 

# 페이지 설정
st.set_page_config(layout="wide", page_title="국내주식 실시간 단타 스캐너 (KIS 연동)")
st.title("🚀 실시간 단타 및 시장 동향 대시보드 (한투 API)")

KST = timezone(timedelta(hours=9))

# -----------------------------------------------------------------------------
# 0. 한투 API 인증 (토큰 발급)
# -----------------------------------------------------------------------------
@st.cache_data(ttl=86000) # 토큰은 보통 24시간 유지되므로 길게 캐싱
def get_kis_token(app_key, app_secret):
    headers = {"content-type": "application/json"}
    body = {
        "grant_type": "client_credentials",
        "appkey": app_key,
        "appsecret": app_secret
    }
    path = "oauth2/tokenP"
    res = requests.post(f"{URL_BASE}/{path}", headers=headers, data=json.dumps(body))
    
    if res.status_code == 200:
        return res.json().get("access_token")
    else:
        st.error(f"⚠️ KIS 토큰 발급 실패: {res.text}")
        return None

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
def get_kis_target_stocks(token):
    """
    FDR 전체 스캔 대신 KIS '거래대금 상위' API를 호출하여 타겟 종목을 추출합니다.
    (실시간성 보장 및 API 호출 횟수 최적화)
    """
    if not token:
        return pd.DataFrame()

    path = "uapi/domestic-stock/v1/quotations/volume-rank"
    headers = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {token}",
        "appKey": KIS_APP_KEY,
        "appSecret": KIS_APP_SECRET,
        "tr_id": "FHPST01710000",
        "custtype": "P"
    }
    
    params = {
        "FID_COND_MRKT_DIV_CODE": "J", # J: 주식
        "FID_COND_SCR_DIV_CODE": "20171",
        "FID_INPUT_ISCD": "0000", # 전체
        "FID_DIV_CLS_CODE": "0",
        "FID_BLNG_CLS_CODE": "0",
        "FID_TRGT_CLS_CODE": "111111111", # 타겟 구분 (전체)
        "FID_TRGT_EXLS_CLS_CODE": "000000",
        "FID_INPUT_PRICE_1": "10000", # 최소 10,000원 이상 (사용자 조건 적용)
        "FID_INPUT_PRICE_2": "10000000",
        "FID_VOL_CNT": "",
        "FID_INPUT_DATE_1": ""
    }

    res = requests.get(f"{URL_BASE}/{path}", headers=headers, params=params)
    
    if res.status_code != 200:
        st.error(f"⚠️ KIS 종목 스크리닝 오류: {res.json().get('msg1')}")
        return pd.DataFrame()

    data = res.json().get('output', [])
    if not data:
        return pd.DataFrame()

    # KIS API 응답을 DataFrame으로 변환
    df = pd.DataFrame(data)
    df = df.rename(columns={
        'hts_kor_isnm': '종목명',
        'mksc_shrn_iscd': '종목코드',
        'stck_prpr': '현재가',
        'prdy_ctrt': '등락률',
        'acml_tr_pbmn': '거래대금', # 누적 거래대금
    })
    
    # 데이터 타입 변환
    df['현재가'] = pd.to_numeric(df['현재가'], errors='coerce')
    df['등락률'] = pd.to_numeric(df['등락률'], errors='coerce')
    # 한투 거래대금은 '원' 단위이므로 백만 단위로 환산
    df['거래대금'] = pd.to_numeric(df['거래대금'], errors='coerce') / 1000000 
    
    # 시가총액은 해당 API에서 바로 주지 않으므로 등수 기반으로 임시 계산(또는 별도 API 필요)
    # 여기서는 기존 로직의 오류를 막기 위해 임의값 할당 후 계산 제외
    df['시가총액'] = 1000 
    df['시장'] = "KRX"
    
    return df

# -----------------------------------------------------------------------------
# [섹션 1] 지수 및 환율 동향 (유지)
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
# [섹션 2] 수급 동향
# -----------------------------------------------------------------------------
st.subheader("💼 시장 수급 및 주도 상태")
if 'foreign_futures_net' not in st.session_state:
    st.session_state.foreign_futures_net = np.random.randint(-5000, 5000)

foreign_futures_net = st.session_state.foreign_futures_net
program_intensity = min(100, int(abs(foreign_futures_net) / 50)) if foreign_futures_net >= 0 else max(0, 100 - min(100, int(abs(foreign_futures_net) / 50)))
trade_signal = "🚀 우량주 단타 추천" if foreign_futures_net >= 0 else "⚠️ 대형주 단타 자제"
delta_msg = "매수 우위" if foreign_futures_net >= 0 else "매도 우위"

col_m1, col_m2 = st.columns(2)
with col_m1:
    st.metric(label="외국인 순매수(가상)", value=f"{foreign_futures_net:,} 억 원", delta=delta_msg, delta_color="normal" if foreign_futures_net >= 0 else "inverse")
with col_m2:
    st.metric(label="시장 매력도 환경", value=f"{program_intensity} 점", delta=trade_signal, delta_color="normal" if foreign_futures_net >= 0 else "inverse")

if st.button("🔄 실시간 데이터 업데이트"):
    get_market_indices.clear()
    get_kis_target_stocks.clear()
    st.rerun()

st.markdown("---")

# -----------------------------------------------------------------------------
# [섹션 3] 개별 종목 스크리닝 (KIS API 적용)
# -----------------------------------------------------------------------------
st.subheader("🎯 단타 타겟 (KIS 거래대금 상위 기반)")

access_token = get_kis_token(KIS_APP_KEY, KIS_APP_SECRET)
df_universe = get_kis_target_stocks(access_token)

if not df_universe.empty:
    cond_rise = df_universe['등락률'] > 0
    filtered_df = df_universe[cond_rise].copy()
    
    # 시총 데이터가 빠졌으므로 등락률과 거래대금만으로 매력도 산출
    filtered_df['단타_매력도'] = ((filtered_df['등락률'] * 2.0) + (np.log1p(filtered_df['거래대금']) * 3.0)).round(1)
    
    top_30 = filtered_df.sort_values(by='단타_매력도', ascending=False).head(30)
    
    output_df = pd.DataFrame({
        '매력도 점수': top_30['단타_매력도'].apply(lambda x: f"{x} 점"),
        '종목명': top_30['종목명'],
        '현재가': top_30['현재가'].apply(lambda x: f"{int(x):,} 원"),
        '전일대비 상승률': top_30['등락률'].apply(lambda x: f"+{x:.2f} %"),
        '거래대금(백만)': top_30['거래대금'].apply(lambda x: f"{int(x):,}"),
        '종목코드': top_30['종목코드'],
        '시장': top_30['시장']
    }).reset_index(drop=True)

    selected_rows = st.dataframe(output_df, use_container_width=True, selection_mode="single-row", on_select="rerun")
else:
    st.warning("⚠️ 한투 API 데이터를 불러오지 못했습니다. API 키 및 토큰 상태를 확인하세요.")
    output_df = pd.DataFrame()

# -----------------------------------------------------------------------------
# [섹션 4] 한투 API 기반 당일 1분봉 시각화
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
    
    st.markdown(f"### 📈 {target_name} ({target_code}) 실시간 1분봉")
    
    with st.spinner("한투 API에서 실시간 분봉 데이터를 가져오는 중입니다..."):
        # KIS 당일분봉조회 API 호출
        path_chart = "uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
        headers_chart = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {access_token}",
            "appKey": KIS_APP_KEY,
            "appSecret": KIS_APP_SECRET,
            "tr_id": "FHKST03010200",
            "custtype": "P"
        }
        params_chart = {
            "FID_ETC_CLS_CODE": "",
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": target_code,
            "FID_INPUT_HOUR_1": "153000", # 오후 3시 30분 기준 역산
            "FID_PW_DATA_INCU_YN": "N"
        }
        
        res_chart = requests.get(f"{URL_BASE}/{path_chart}", headers=headers_chart, params=params_chart)
        
        if res_chart.status_code == 200:
            chart_data = res_chart.json().get('output2', [])
            
            if chart_data:
                # 데이터를 DataFrame으로 변환 및 역순(과거->현재) 정렬
                df_chart = pd.DataFrame(chart_data)
                df_chart = df_chart[['stck_cntg_hour', 'stck_prpr']].dropna()
                df_chart = df_chart[df_chart['stck_cntg_hour'] != '']
                df_chart['stck_prpr'] = pd.to_numeric(df_chart['stck_prpr'])
                df_chart = df_chart.iloc[::-1].reset_index(drop=True)
                
                # 시간 형식 포맷팅
                df_chart['time'] = pd.to_datetime(df_chart['stck_cntg_hour'], format='%H%M%S').dt.time
                df_chart['time_str'] = df_chart['time'].astype(str)
                
                fig_stock = go.Figure()
                fig_stock.add_trace(go.Scatter(
                    x=df_chart['time_str'],
                    y=df_chart['stck_prpr'],
                    mode='lines',
                    line=dict(color='#4c6198', width=2),
                    name="현재가"
                ))
                
                min_price, max_price = df_chart['stck_prpr'].min(), df_chart['stck_prpr'].max()
                margin = (max_price - min_price) * 0.1 if min_price != max_price else min_price * 0.01
                
                fig_stock.update_layout(
                    template="plotly_white",
                    height=400,
                    margin=dict(l=10, r=40, t=20, b=20),
                    xaxis=dict(showgrid=True, gridcolor='#f0f0f0', tickangle=-45, nticks=15),
                    yaxis=dict(side='right', showgrid=True, gridcolor='#f0f0f0', range=[min_price - margin, max_price + margin]),
                    hovermode='x unified'
                )
                
                st.plotly_chart(fig_stock, use_container_width=True)
            else:
                st.warning("분봉 데이터가 존재하지 않습니다.")
        else:
            st.error(f"차트 데이터 조회 실패: {res_chart.json().get('msg1')}")
