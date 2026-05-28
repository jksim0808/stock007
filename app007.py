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
    for theme, keywords in THEME_DICT.items():
        if any(keyword in stock_name for keyword in keywords):
            return theme
    return "▪️ 개별주"

# -----------------------------------------------------------------------------
# 1. KIS API 인증 및 토큰 발급
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
    if not token:
        get_access_token.clear()
        token = get_access_token()
    return {
        "Content-Type": "application/json", "authorization": f"Bearer {token}",
        "appKey": APP_KEY, "appSecret": APP_SECRET, "tr_id": tr_id
    }

# -----------------------------------------------------------------------------
# 2. 데이터 로드 함수 (대형 우량주 포함 거래대금 중심)
# -----------------------------------------------------------------------------
@st.cache_data(ttl=60)
def get_market_indices():
    today = datetime.now(KST).strftime('%Y-%m-%d')
    start_date = (datetime.now(KST) - timedelta(days=30)).strftime('%Y-%m-%d')

    # 1. 코스피 & 코스닥
    try:
        kospi = fdr.DataReader('KS11', start_date, today)
    except Exception:
        kospi = pd.DataFrame()
        
    try:
        kosdaq = fdr.DataReader('KQ11', start_date, today)
    except Exception:
        kosdaq = pd.DataFrame()
        
    # 2. 원/달러 환율 (네이버 금융)
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        df_list = []
        
        for page in range(1, 4):
            url = f"https://finance.naver.com/marketindex/exchangeDailyQuote.naver?marketindexCd=FX_USDKRW&page={page}"
            res = requests.get(url, headers=headers)
            
            # ✨ 한글 깨짐을 방지하기 위해 응답 데이터의 인코딩을 명시
            res.encoding = 'cp949'
            
            # ✨ 핵심 해결: res.text를 바로 넣지 않고 io.StringIO()로 감싸줍니다!
            df = pd.read_html(io.StringIO(res.text))[0]
            df_list.append(df)
            
        usd_krw = pd.concat(df_list, ignore_index=True)
        usd_krw = usd_krw.iloc[:, [0, 1]] 
        usd_krw.columns = ['Date', 'Close']
        
        usd_krw = usd_krw.dropna()
        usd_krw['Date'] = pd.to_datetime(usd_krw['Date'].str.replace('.', '-', regex=False))
        usd_krw['Close'] = pd.to_numeric(usd_krw['Close'].astype(str).str.replace(',', ''), errors='coerce')
        usd_krw = usd_krw.set_index('Date').sort_index()
        
    except Exception as e:
        st.error(f"⚠️ 네이버 환율 수집 실패: {e}")
        usd_krw = pd.DataFrame()
        
    return kospi, kosdaq, usd_krw
    
@st.cache_data(ttl=30)
def get_kis_top_trading_value_stocks():
    url = f"{URL_BASE}/uapi/domestic-stock/v1/quotations/volume-rank"
    headers = get_common_headers("FHPST01710000")
    
    # 1. 중소형주 포착 (1만 원 ~ 8만 원)
    params_mid = {
        "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171",
        "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "1", 
        "FID_BLNG_CLS_CODE": "0", "FID_TRGT_CLS_CODE": "111111111", 
        "FID_TRGT_EXLS_CLS_CODE": "111111", 
        "FID_INPUT_PRICE_1": "10000", "FID_INPUT_PRICE_2": "80000", 
        "FID_VOL_CNT": "", "FID_INPUT_DATE_1": ""
    }
    
    # 2. 대형 우량주 포착 (8만 원 ~ 200만 원)
    params_large = {
        "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171",
        "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "1", 
        "FID_BLNG_CLS_CODE": "0", "FID_TRGT_CLS_CODE": "111111111", 
        "FID_TRGT_EXLS_CLS_CODE": "111111", 
        "FID_INPUT_PRICE_1": "80000", "FID_INPUT_PRICE_2": "2000000", 
        "FID_VOL_CNT": "", "FID_INPUT_DATE_1": ""
    }
    
    df_list = []
    for params in [params_mid, params_large]:
        try:
            res = requests.get(url, headers=headers, params=params)
            res.raise_for_status()
            data = res.json()
            if data['rt_cd'] == '0' and 'output' in data:
                df_temp = pd.DataFrame(data['output'])[['hts_kor_isnm', 'mksc_shrn_iscd', 'stck_prpr', 'prdy_ctrt', 'acml_tr_pbmn']]
                df_list.append(df_temp)
        except Exception as e:
            continue
            
    if not df_list:
        return pd.DataFrame()
        
    df = pd.concat(df_list, ignore_index=True)
    df.columns = ['종목명', '종목코드', '현재가', '등락률', '거래대금']
    
    exclude_keywords = ['KODEX', 'TIGER', 'KBSTAR', 'ACE', 'ARIRANG', 'HANARO', 'KOSEF', 'SOL', 'TIMEFOLIO', 'WOORI', '히어로즈', '마이티', '스팩', 'ETN']
    pattern = '|'.join(exclude_keywords)
    df = df[~df['종목명'].str.contains(pattern, case=False, regex=True)]
    
    df['시장'] = 'KRX'
    df['현재가'] = pd.to_numeric(df['현재가'], errors='coerce')
    df['등락률'] = pd.to_numeric(df['등락률'], errors='coerce')
    df['거래대금'] = pd.to_numeric(df['거래대금'], errors='coerce') / 1000000 
    
    df = df.sort_values(by='거래대금', ascending=False).drop_duplicates(subset=['종목코드'])
    return df.dropna()

@st.cache_data(ttl=60)
def get_foreign_investor_trend():
    """
    네이버 금융 '투자자별 매매동향' 외국인 선물 순매수 크롤링 (강화 버전)
    """
    try:
        url = "https://finance.naver.com/sise/sise_trans_style.naver"
        # 봇 차단을 막기 위해 더 디테일한 User-Agent 사용
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')
        
        rows = soup.find_all('tr')
        
        for row in rows:
            cols = row.find_all('td')
            # 열이 4개 이상 존재하는 유의미한 행인지 검사
            if len(cols) >= 4:
                # 텍스트 내부의 모든 공백, 탭, 줄바꿈 완전 제거 후 비교
                row_name = cols[0].text.replace(' ', '').replace('\n', '').replace('\t', '')
                
                if '외국인' in row_name:
                    # 선물 데이터는 4번째 칸(index 3)
                    val_str = cols[3].text.replace(',', '').strip()
                    if val_str:
                        return float(val_str)
                        
        return 0.0 # 데이터를 못 찾았을 경우
        
    except Exception as e:
        print(f"외국인 선물 데이터 크롤링 에러: {e}")
        return 0.0
# -----------------------------------------------------------------------------
# [섹션 1 & 2] 시장 동향 및 수급
# -----------------------------------------------------------------------------
st.subheader("📊 주요 시장 지수 및 환율 동향")
kospi, kosdaq, usd_krw = get_market_indices()
col1, col2, col3 = st.columns(3)

def create_chart(df, title, color):
    fig = go.Figure(go.Scatter(x=df.index, y=df['Close'], mode='lines', name=title, line=dict(color=color, width=2)))
    fig.update_layout(title=title, height=250, margin=dict(l=20, r=20, t=40, b=20), template="plotly_dark")
    return fig

if not kospi.empty: col1.plotly_chart(create_chart(kospi, "KOSPI 지수", "#FF4B4B"), use_container_width=True)
if not kosdaq.empty: col2.plotly_chart(create_chart(kosdaq, "KOSDAQ 지수", "#00CC96"), use_container_width=True)
if not usd_krw.empty: col3.plotly_chart(create_chart(usd_krw, "원/달러 환율", "#636EFA"), use_container_width=True)

st.markdown("---")
st.subheader("💼 외국인 선물 수급 및 시장 주도 상태")

st.markdown("---")
st.subheader("💼 외국인 선물 수급 및 시장 주도 상태")

if 'foreign_futures_net' not in st.session_state:
    st.session_state.foreign_futures_net = get_foreign_investor_trend()

foreign_futures_net = st.session_state.foreign_futures_net

# ✨ 값이 양수, 음수, 0일 때를 명확히 3단계로 분리하고 기호(+/-)를 명시적으로 추가
if foreign_futures_net > 0:
    value_str = f"+{foreign_futures_net:,} 억 원" # 매수 우위 시 '+' 기호 강제 추가
    program_intensity = min(100, int(foreign_futures_net / 50))
    trade_signal = "🚀 우량주 단타 적극 추천 (바스켓 매수 유입)"
    delta_msg = "매수 우위 (시장 주도)"
    score_color = "normal"
elif foreign_futures_net < 0:
    value_str = f"{foreign_futures_net:,} 억 원" # 매도 우위 시 '-' 기호는 자동으로 붙음
    program_intensity = max(0, 100 - min(100, int(abs(foreign_futures_net) / 50)))
    trade_signal = "⚠️ 대형주 단타 자제 (프로그램 매물 압력)"
    delta_msg = "매도 우위 (시장 압박)"
    score_color = "inverse"
else:
    value_str = "0.0 억 원"
    program_intensity = 50 
    trade_signal = "⏸️ 수급 데이터 대기 중 (장 마감 또는 집계 지연)"
    delta_msg = "데이터 없음"
    score_color = "off"

col_m1, col_m2 = st.columns(2)
col_m1.metric(label="외국인 주식선물 순매수 금액", value=value_str, delta=delta_msg, delta_color=score_color)
col_m2.metric(label="시장 전체 우량주 매력도 환경 (100점 만점)", value=f"{program_intensity} 점", delta=trade_signal, delta_color=score_color)

if st.button("🔄 실시간 데이터 업데이트 (수동)"):
    st.session_state.foreign_futures_net = get_foreign_investor_trend()
    get_kis_top_trading_value_stocks.clear()
    st.rerun()

st.markdown("---")
# -----------------------------------------------------------------------------
# ⏱️ [자동 새로고침 스위치] 함수 정의가 모두 끝난 안전한 곳에 위치
# -----------------------------------------------------------------------------
col_t1, col_t2 = st.columns([1, 4])
with col_t1:
    auto_refresh = st.toggle("⏱️ 1분 자동 스캐닝 켜기", value=False)

if auto_refresh:
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=60000, limit=1000, key="auto_scanner_refresh")
        st.toast("🔄 스캐너가 실시간(1분 단위)으로 감시 중입니다!", icon="👀")
        get_kis_top_trading_value_stocks.clear()
    except ImportError:
        st.error("⚠️ streamlit-autorefresh 라이브러리가 설치되지 않았습니다. requirements.txt를 확인해주세요.")

# -----------------------------------------------------------------------------
# [섹션 3] 개별 종목 스크리닝 및 🤖 AI 상승 예측 스코어링
# -----------------------------------------------------------------------------
st.subheader("🎯 단타 타겟 Top 30 (AI 상승 예측 랭킹 순)")

df_universe = get_kis_top_trading_value_stocks()

if not df_universe.empty:
    cond_rise = df_universe['등락률'] > -2.0
    filtered_df = df_universe[cond_rise].copy()

# ==========================================================
    # 🧠 [듀얼 AI 모델] 적용 구간
    # ==========================================================
    X_live = filtered_df[['등락률', '거래대금', '현재가']].fillna(0)
    model_path = "stock_dual_model.pkl" # 새로 만든 듀얼 모델 파일명으로 변경
    
    if os.path.exists(model_path):
        try:
            # 두 개의 모델이 담긴 딕셔너리 불러오기
            dual_models = joblib.load(model_path)
            model_10min = dual_models['model_10min']
            model_close = dual_models['model_close']
            
            # 실시간 데이터를 넣어 두 가지 예측 점수 동시 추출
            filtered_df['10분_상승예측(%)'] = np.round(model_10min.predict(X_live), 2)
            filtered_df['종가_상승예측(%)'] = np.round(model_close.predict(X_live), 2)
            
        except Exception as e:
            st.error(f"⚠️ AI 모델 예측 에러: {e}")
            filtered_df['10분_상승예측(%)'] = 0.0
            filtered_df['종가_상승예측(%)'] = 0.0
    else:
        st.info("⚠️ 'stock_dual_model.pkl' 파일이 없습니다. 기본 점수를 띄웁니다.")
        filtered_df['10분_상승예측(%)'] = ((filtered_df['등락률'] * 0.5) + np.log1p(filtered_df['거래대금'])).round(2)
        filtered_df['종가_상승예측(%)'] = 0.0
    # ==========================================================

    filtered_df['테마'] = filtered_df['종목명'].apply(get_theme_icon)
    filtered_df['단기_목표가'] = (filtered_df['현재가'] * 1.03).astype(int)
    filtered_df['손절가'] = (filtered_df['현재가'] * 0.98).astype(int)
    filtered_df['상한가_여력'] = (30.0 - filtered_df['등락률']).round(2)

    def detect_signal(row):
        if row['등락률'] >= 7.0 and row['거래대금'] > 50000: return "🔥 돌파매매"
        elif 1.0 <= row['등락률'] < 5.0 and row['거래대금'] > 20000: return "💧 눌림목"
        return "▪️ 관망"

    filtered_df['매매상태'] = filtered_df.apply(detect_signal, axis=1)

    # 정렬 기준을 가장 중요한 '10분_상승예측(%)'로 변경!
    top_30 = filtered_df.sort_values(by='10분_상승예측(%)', ascending=False).head(30)

    output_df = pd.DataFrame({
        '테마': top_30['테마'],
        '실시간 상태': top_30['매매상태'],
        'AI 10분 단타예측': top_30['10분_상승예측(%)'].apply(lambda x: f"🚀 +{x}%"), # ✨ 메인 타겟
        'AI 종가 홀딩예측': top_30['종가_상승예측(%)'].apply(lambda x: f"📈 +{x}%" if x > 0 else f"📉 {x}%"), # ✨ 보조 타겟
        '종목명': top_30['종목명'],
        '현재가': top_30['현재가'].apply(lambda x: f"{int(x):,} 원"),
        '상승률': top_30['등락률'].apply(lambda x: f"+{x:.2f} %"),
        '단기 목표가(+3%)': top_30['단기_목표가'].apply(lambda x: f"{x:,} 원"),
        '손절가(-2%)': top_30['손절가'].apply(lambda x: f"{x:,} 원"),
        '거래대금(백만)': top_30['거래대금'].apply(lambda x: f"{int(x):,}"),
        '종목코드': top_30['종목코드']
    }).reset_index(drop=True)

    st.markdown("💡 **표에서 관심 있는 종목의 행을 클릭**하시면 하단에 정밀 분석용 1분봉 캔들차트가 생성됩니다.")

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
# [섹션 4] 종목 클릭 시 KIS 1분봉 시각화 (돌파/눌림 신호 및 캔들차트 적용)
# -----------------------------------------------------------------------------
st.markdown("---")

selected_idx = 0
if hasattr(selected_rows, 'selection') and len(selected_rows.selection.rows) > 0:
    selected_idx = selected_rows.selection.rows[0]

if not output_df.empty and selected_idx < len(output_df):
    target_code = output_df.iloc[selected_idx]['종목코드']
    target_name = output_df.iloc[selected_idx]['종목명']
    target_theme = output_df.iloc[selected_idx]['테마']
    target_price = output_df.iloc[selected_idx]['현재가']
    target_change = output_df.iloc[selected_idx]['상승률']
    target_vol = output_df.iloc[selected_idx]['거래대금(백만)']
    
    st.markdown(f"""
    <div style='padding: 10px 0; border-bottom: 1px solid #ddd; margin-bottom: 15px;'>
        <span style='font-size: 20px; font-weight: bold;'>{target_name}</span> 
        <span style='font-size: 14px; margin-left: 5px; color: #555;'>[{target_theme}]</span>
        <span style='font-size: 14px; font-weight: bold; margin-left: 15px;'>{target_price}</span>
        <span style='font-size: 14px; color: #e12929; margin-left: 5px;'>{target_change}</span>
        <span style='font-size: 14px; color: #888; margin-left: 10px;'>거래대금 {target_vol}백만</span>
    </div>
    """, unsafe_allow_html=True)
    
    with st.spinner(f"[{target_name}] 1분봉 데이터 및 매매 신호를 분석 중입니다..."):
        url = f"{URL_BASE}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
        headers = get_common_headers("FHKST03010200")
        
        now_time = datetime.now(KST).strftime("%H%M%S")
        params = {
            "FID_ETC_CLS_CODE": "", "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": target_code, "FID_INPUT_HOUR_1": now_time, "FID_PW_DATA_INCU_YN": "Y"
        }
        
        try:
            res = requests.get(url, headers=headers, params=params)
            res_data = res.json()
            
            if res_data['rt_cd'] == '0' and 'output2' in res_data:
                min_data = res_data['output2'][::-1] 
                times = [f"{m['stck_bsop_date']} {m['stck_cntg_hour']}" for m in min_data]
                
                # OHLCV 모두 추출
                opens = [float(m['stck_oprc']) for m in min_data]
                highs = [float(m['stck_hgpr']) for m in min_data]
                lows = [float(m['stck_lwpr']) for m in min_data]
                closes = [float(m['stck_prpr']) for m in min_data]
                volumes = [float(m['cntg_vol']) for m in min_data] 
                
                date_idx = pd.to_datetime(times, format="%Y%m%d %H%M%S")
                df_min = pd.DataFrame({"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes}, index=date_idx)
                df_min = df_min[df_min['Close'] > 0]
                
                if not df_min.empty:
                    # 1. 이동평균선(MA) 및 거래량 평균 계산
                    df_min['MA5'] = df_min['Close'].rolling(window=5).mean()
                    df_min['MA20'] = df_min['Close'].rolling(window=20).mean()
                    df_min['Vol_MA5'] = df_min['Volume'].rolling(window=5).mean()
                    
                    # 2. 🔥 돌파 신호 계산 (20분 전고점 돌파 + 5분 평균 거래량 1.5배 터짐)
                    df_min['Prev_High_20'] = df_min['High'].shift(1).rolling(window=20).max()
                    df_min['Breakout'] = (df_min['Close'] > df_min['Prev_High_20']) & (df_min['Volume'] > df_min['Vol_MA5'] * 1.5)
                    
                    # 3. 💧 눌림목 신호 계산 (20분선 우상향 중 + 주가가 20분선 근접 터치 + 거래량 감소)
                    df_min['Pullback'] = (df_min['MA20'] > df_min['MA20'].shift(3)) & \
                                         (df_min['Low'] <= df_min['MA20'] * 1.005) & \
                                         (df_min['Close'] >= df_min['MA20'] * 0.998) & \
                                         (df_min['Volume'] < df_min['Vol_MA5'])
                    
                    # 차트 시각화
                    df_min['Diff'] = df_min['Close'].diff().fillna(0)
                    colors = ['#ff4b4b' if diff >= 0 else '#4c6198' for diff in df_min['Diff']]
                    min_price, max_price = df_min['Low'].min(), df_min['High'].max()
                    price_margin = (max_price - min_price) * 0.1 if max_price != min_price else min_price * 0.01
                    
                    fig_stock = go.Figure()

                    # 봉차트(Candlestick) 추가
                    fig_stock.add_trace(go.Candlestick(
                        x=df_min.index, open=df_min['Open'], high=df_min['High'], low=df_min['Low'], close=df_min['Close'],
                        increasing_line_color='#ff4b4b', decreasing_line_color='#4c6198', name="주가"
                    ))

                    # 5분선, 20분선 추가
                    fig_stock.add_trace(go.Scatter(x=df_min.index, y=df_min['MA5'], mode='lines', line=dict(color='#ff9900', width=1.5), name="5분선", hoverinfo='skip'))
                    fig_stock.add_trace(go.Scatter(x=df_min.index, y=df_min['MA20'], mode='lines', line=dict(color='#cc00ff', width=1.5), name="20분선", hoverinfo='skip'))

                    # 🔥 돌파 마커 추가
                    breakout_data = df_min[df_min['Breakout']]
                    if not breakout_data.empty:
                        fig_stock.add_trace(go.Scatter(
                            x=breakout_data.index, y=breakout_data['High'] + price_margin*0.2,
                            mode='markers+text', marker=dict(symbol='triangle-down', size=10, color='red'),
                            text="🔥돌파", textposition="top center", textfont=dict(color='red', size=11, weight='bold'), name="돌파"
                        ))

                    # 💧 눌림목 마커 추가
                    pullback_data = df_min[df_min['Pullback']]
                    if not pullback_data.empty:
                        fig_stock.add_trace(go.Scatter(
                            x=pullback_data.index, y=pullback_data['Low'] - price_margin*0.2,
                            mode='markers+text', marker=dict(symbol='triangle-up', size=10, color='blue'),
                            text="💧눌림", textposition="bottom center", textfont=dict(color='blue', size=11, weight='bold'), name="눌림"
                        ))

                    # 거래량 바차트 추가
                    fig_stock.add_trace(go.Bar(
                        x=df_min.index, y=df_min['Volume'], name="거래량",
                        marker_color=colors, opacity=0.7, yaxis='y2'
                    ))
                    
                    fig_stock.update_layout(
                        template="plotly_white", height=650, margin=dict(l=10, r=60, t=30, b=20),
                        xaxis=dict(showgrid=True, gridcolor='#f0f0f0', type='date', tickformat='%H:%M', rangeslider=dict(visible=False)),
                        yaxis=dict(side='right', showgrid=True, gridcolor='#f0f0f0', tickformat=',', range=[min_price - price_margin, max_price + price_margin], domain=[0.3, 1]),
                        yaxis2=dict(side='right', showgrid=False, tickformat=',', domain=[0, 0.2]),
                        hovermode='x unified', showlegend=True,
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                    )
                    st.plotly_chart(fig_stock, use_container_width=True)
                else: st.warning("유효한 분봉 데이터가 없습니다.")
            else: st.error(f"분봉 조회 실패: {res_data.get('msg1', '알 수 없는 오류')}")
        except Exception as e: st.error(f"분봉 API 호출 중 에러 발생: {e}")

# -----------------------------------------------------------------------------
# [섹션 5] 프로그램 로직 및 단타 활용 가이드
# -----------------------------------------------------------------------------
st.markdown("---")
with st.expander("📖 스캐너 작동 로직 및 실전 단타 가이드 (클릭하여 펼치기)", expanded=True):
    st.markdown("""
    ### ⚙️ 1. 스캐너 작동 로직 (대형주 포함 버전)
    * **데이터 소스**: 한국투자증권(KIS) 실전 Open API
    * **1차 스크리닝 (거래대금 중심)**: 거래량 상위 API를 두 번 호출하여 '중소형주(1~8만 원)'와 '대형 우량주(8~200만 원)' 데이터를 수집합니다. 이후 ETF, 스팩(SPAC) 등 불필요한 종목을 제거하고, 오직 **'당일 누적 거래대금'**이 많은 순서대로 기초 유니버스를 구성합니다.
    * **2차 필터링 (리스크 관리)**: 당일 하락폭이 큰 종목을 피하기 위해, **등락률이 -2.0% 이하로 떨어진 종목은 스캐너에서 즉시 제외**시킵니다.
    * **최종 랭킹 (매력도 점수)**: 살아남은 종목들에 대해 `(등락률 × 1.5) + (log(거래대금) × 2.5)` 공식을 적용합니다. 상승 탄력과 돈의 힘이 완벽히 맞아떨어지는 **매력도 점수 상위 30종목**만 최종 스크린에 노출합니다.

    ### 🎯 2. 실전 단타 가이드라인 활용법
    * **실시간 상태**: 상단 메인 표에서 종목의 현재 거래세 및 등락 추이를 분석하여 실시간으로 **🔥 돌파매매** 또는 **💧 눌림목** 상태를 표기해 줍니다. 
    * **단기 목표가 (+3%)**: 해당 종목 진입 시, 감정에 휩쓸리지 않고 기계적으로 분할 매도를 시작해야 할 1차 익절 라인입니다.
    * **손절가 (-2%)**: 단타는 대응이 생명입니다. 진입 후 이 가격을 이탈하면 뒤도 돌아보지 말고 기계적으로 손절해야 하는 마지노선입니다.
    * **상한가까지 여력**: 현재가에서 상한가(30%)까지 얼마나 남았는지를 보여줍니다. 이 수치가 너무 작다면(예: 3% 이하) 먹을 구간이 적고 상승 여력이 부족해 리스크가 크므로 진입을 피하는 것이 좋습니다.

    ### 📈 3. 실전 단타 타점 잡기 (1분봉 차트 활용)
    * 리스트에서 관심 있는 종목을 **클릭**하면 화면 하단에 KIS 실시간 1분봉 차트가 뜹니다.
    * **🔥 돌파 매매**: 1분봉상 직전 20분 고점을 거래량(5분 평균의 1.5배 이상)과 함께 강하게 뚫어줄 때 마커가 표시됩니다.
    * **💧 눌림목 매매**: 급등 후 하락하다가 20분 이동평균선 근처에서 지지를 받으며 거래량이 줄어들 때 마커가 표시됩니다.
    """)
