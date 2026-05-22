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
