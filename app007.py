import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import json
from datetime import datetime, timedelta, timezone
import FinanceDataReader as fdr
import io
from bs4 import BeautifulSoup
import joblib
import os

# -----------------------------------------------------------------------------
# [설정] 기본 셋팅 (모바일에 맞게 레이아웃 조정)
# -----------------------------------------------------------------------------
# 모바일에서는 'wide'나 'centered'가 큰 차이가 없지만, 여백을 줄이기 위해 centered 권장
st.set_page_config(layout="centered", page_title="📱 단타 스캐너 (모바일)", initial_sidebar_state="collapsed")

# 모바일용 커스텀 CSS (상하단 여백 최소화)
st.markdown("""
    <style>
        .block-container { padding-top: 1rem; padding-bottom: 1rem; }
        h1 { font-size: 1.5rem !important; }
        h2 { font-size: 1.2rem !important; }
        h3 { font-size: 1.1rem !important; }
    </style>
""", unsafe_allow_html=True)

st.title("🚀 실시간 AI 단타 스캐너")

try:
    KIS_APP_KEY = st.secrets["KIS_APP_KEY"]
    KIS_APP_SECRET = st.secrets["KIS_APP_SECRET"]
    APP_KEY = KIS_APP_KEY
    APP_SECRET = KIS_APP_SECRET
except KeyError:
    st.error("⚠️ Secrets에 KIS_APP_KEY / KIS_APP_SECRET 이 없습니다.")
    st.stop()

URL_BASE = "https://openapi.koreainvestment.com:9443" 
KST = timezone(timedelta(hours=9))

THEME_DICT = {
    "🤖 로봇": ["두산로보틱스", "레인보우로보틱스", "뉴로메카", "에스피지", "로보티즈", "이랜시스", "로보틱스"],
    "💾 반도체": ["한미반도체", "SK하이닉스", "삼성전자", "HPSP", "이수페타시스", "제우스", "가온칩스", "리노공업", "디아이"],
    "🔋 2차전지": ["에코프로", "에코프로비엠", "에코프로머티", "포스코홀딩스", "POSCO홀딩스", "LG에너지솔루션", "엘앤에프"],
    "🧬 바이오": ["알테오젠", "HLB", "삼성바이오로직스", "셀트리온", "삼천당제약", "리가켐바이오", "휴젤"],
    "⚡ 전력기기": ["HD현대일렉트릭", "LS일렉트릭", "효성중공업", "제룡전기", "일진전기"],
    "💄 화장품": ["실리콘투", "브이티", "코스메카코리아", "씨앤씨인터내셔널", "아모레퍼시픽", "클리오"]
}

def get_theme_icon(stock_name):
    for theme, keywords in THEME_DICT.items():
        if any(keyword in stock_name for keyword in keywords):
            return theme
    return "▪️ 개별" # 모바일을 위해 글자수 단축

@st.cache_resource(ttl=3600*20)
def get_access_token():
    headers = {"content-type": "application/json"}
    body = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    try:
        res = requests.post(f"{URL_BASE}/oauth2/tokenP", headers=headers, data=json.dumps(body))
        res.raise_for_status()
        return res.json()["access_token"]
    except: return None

def get_common_headers(tr_id):
    token = get_access_token()
    if not token:
        get_access_token.clear()
        token = get_access_token()
    return {"Content-Type": "application/json", "authorization": f"Bearer {token}", "appKey": APP_KEY, "appSecret": APP_SECRET, "tr_id": tr_id}

@st.cache_data(ttl=30)
def get_kis_top_trading_value_stocks():
    url = f"{URL_BASE}/uapi/domestic-stock/v1/quotations/volume-rank"
    headers = get_common_headers("FHPST01710000")
    
    params_mid = {"FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171", "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "1", "FID_BLNG_CLS_CODE": "0", "FID_TRGT_CLS_CODE": "1111111
