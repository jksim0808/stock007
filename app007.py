import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import json
from datetime import datetime, timedelta, timezone
import FinanceDataReader as fdr 

# -----------------------------------------------------------------------------
# [설정] 한국투자증권 API KEY (Streamlit Secrets 활용)
# -----------------------------------------------------------------------------
try:
    KIS_APP_KEY = st.secrets["KIS_APP_KEY"]
    KIS_APP_SECRET = st.secrets["KIS_APP_SECRET"]
    
    APP_KEY = KIS_APP_KEY
    APP_SECRET = KIS_APP_SECRET
except KeyError:
    st.error("⚠️ Streamlit secrets에 'KIS_APP_KEY' 또는 'KIS_APP_SECRET'이 설정되지 않았습니다.")
    st.stop()

URL_BASE = "https://openapi.koreainvestment.com:9443" 

# 페이지 설정
st.set_page_config(layout="wide", page_title="국내주식 실시간 단타 스캐너 (KIS API)")
st.title("🚀 실시간 단타 및 시장 동향 대시보드")

KST = timezone(timedelta(hours=9))

# -----------------------------------------------------------------------------
# 💡 주요 테마주 딕셔너리
# -----------------------------------------------------------------------------
THEME_DICT = {
    "🤖 로봇": ["두산로보틱스", "레인보우로보틱스", "뉴로메카", "에스피지", "로보티즈", "이랜시스"],
    "💾 반도체": ["한미반도체", "SK하이닉스", "삼성전자", "HPSP", "이수페타시스", "제우스", "가온칩스", "리노공업", "디아이"],
    "🔋 2차전지": ["에코프로", "에코프로비엠", "에코프로머티", "포스코홀딩스", "POSCO홀딩스", "LG에너지솔루션", "엘앤에프", "금양"],
    "🧬 바이오": ["알테오젠", "HLB", "삼성바이오로직스", "셀트리온", "삼천당제약", "리가켐바이오", "휴젤"],
    "⚡ 전력기기": ["HD현대일렉트릭", "LS일렉트릭", "효성중공업", "제룡전기", "일진전기"],
    "💄 화장품": ["실리콘투", "브이티", "코스메카코리아", "씨앤씨인터내셔널", "아모레퍼시픽", "클리오"]
}

def get_theme_icon(stock_name):
    """종목명을 바탕으로 테마 아이콘을 반환하는 함수"""
    for theme, keywords in THEME_DICT.items():
        if any(keyword in stock_name for keyword in keywords):
            return theme
    return "▪️ 개별주" # 테마에 속하지 않은 종목

# -----------------------------------------------------------------------------
# 1. KIS API 인증 및 토큰 발급 (캐시 만료 방어 로직 추가)
# -----------------------------------------------------------------------------
@st.cache_resource(ttl=3600*20)
def get_access_token():
    headers = {"content-type": "application/json"}
    body = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
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
    # 토큰이 유효하지 않을 경우 캐시를 지우고 재시도
    if not token:
        get_access_token.clear()
        token = get_access_token()
        
    return {
        "Content-Type": "application/json", "authorization": f"Bearer {token}",
        "appKey": APP_KEY, "appSecret": APP_SECRET, "tr_id": tr_id
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
    url = f"{URL_BASE}/uapi/domestic-stock/v1/quotations/volume-rank"
    headers = get_common_headers("FHPST01710000")
    params = {
        "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171",
        "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "1", # 보통주(ETF 제외)
        "FID_BLNG_CLS_CODE": "0", "FID_TRGT_CLS_CODE": "111111111", 
        "FID_TRGT_EXLS_CLS_CODE": "111111", "FID_INPUT_PRICE_1": "1000", 
        "FID_INPUT_PRICE_2": "1000000", "FID_VOL_CNT": "", "FID_INPUT_DATE_1": ""
    }
    
    try:
        res = requests.get(url, headers=headers, params=params)
        res.raise_for_status()
        data = res.json()
        if data['rt_cd'] != '0': return pd.DataFrame()
        
        df = pd.DataFrame(data['output'])[['hts_kor_isnm', 'mksc_shrn_iscd', 'stck_prpr', 'prdy_ctrt', 'acml_tr_pbmn']]
        df.columns = ['종목명', '종목코드', '현재가', '등락률', '거래대금']
        
        exclude_keywords = ['KODEX', 'TIGER', 'KBSTAR', 'ACE', 'ARIRANG', 'HANARO', 'KOSEF', 'SOL', 'TIMEFOLIO', 'WOORI', '히어로즈', '마이티', '스팩', 'ETN']
        pattern = '|'.join(exclude_keywords)
        df = df[~df['종목명'].str.contains(pattern, case=False, regex=True)]
        
        df['시장'] = 'KRX'
        df['현재가'] = pd.to_numeric(df['현재가'], errors='coerce')
        df['등락률'] = pd.to_numeric(df['등락률'], errors='coerce')
        df['거래대금'] = pd.to_numeric(df['거래대금'], errors='coerce') / 1000000
