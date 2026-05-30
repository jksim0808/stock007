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
    
    params_mid = {"FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171", "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "1", "FID_BLNG_CLS_CODE": "0", "FID_TRGT_CLS_CODE": "111111111", "FID_TRGT_EXLS_CLS_CODE": "111111", "FID_INPUT_PRICE_1": "10000", "FID_INPUT_PRICE_2": "80000", "FID_VOL_CNT": "", "FID_INPUT_DATE_1": ""}
    params_large = {"FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171", "FID_INPUT_ISCD": "0000", "FID_DIV_CLS_CODE": "1", "FID_BLNG_CLS_CODE": "0", "FID_TRGT_CLS_CODE": "111111111", "FID_TRGT_EXLS_CLS_CODE": "111111", "FID_INPUT_PRICE_1": "80000", "FID_INPUT_PRICE_2": "2000000", "FID_VOL_CNT": "", "FID_INPUT_DATE_1": ""}
    
    df_list = []
    for params in [params_mid, params_large]:
        try:
            res = requests.get(url, headers=headers, params=params)
            data = res.json()
            if data['rt_cd'] == '0' and 'output' in data:
                df_list.append(pd.DataFrame(data['output'])[['hts_kor_isnm', 'mksc_shrn_iscd', 'stck_prpr', 'prdy_ctrt', 'acml_tr_pbmn']])
        except: continue
            
    if not df_list: return pd.DataFrame()
        
    df = pd.concat(df_list, ignore_index=True)
    df.columns = ['종목명', '종목코드', '현재가', '등락률', '거래대금']
    pattern = '|'.join(['KODEX', 'TIGER', 'KBSTAR', 'ACE', 'ARIRANG', 'HANARO', 'KOSEF', 'SOL', 'TIMEFOLIO', 'WOORI', '히어로즈', '마이티', '스팩', 'ETN'])
    df = df[~df['종목명'].str.contains(pattern, case=False, regex=True)]
    
    df['현재가'] = pd.to_numeric(df['현재가'], errors='coerce')
    df['등락률'] = pd.to_numeric(df['등락률'], errors='coerce')
    df['거래대금'] = pd.to_numeric(df['거래대금'], errors='coerce') / 1000000 
    return df.sort_values(by='거래대금', ascending=False).drop_duplicates(subset=['종목코드']).dropna()

@st.cache_data(ttl=60)
def get_foreign_investor_trend():
    try:
        url = "https://finance.naver.com/sise/sise_trans_style.naver"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.content.decode('euc-kr', 'replace'), 'html.parser')
        
        for row in soup.find_all('tr'):
            cols = row.find_all('td')
            if len(cols) >= 4:
                row_name = cols[0].text.replace(' ', '').replace('\n', '')
                if '외국인' in row_name:
                    val_str = cols[3].text.replace(',', '').strip()
                    if val_str: return float(val_str)
        return 0.0
    except: return 0.0

@st.cache_data(ttl=60)
def get_market_indices_v2():
    end = datetime.now(KST).strftime('%Y-%m-%d')
    start = (datetime.now(KST) - timedelta(days=20)).strftime('%Y-%m-%d')
    try: ks = fdr.DataReader('KS11', start, end)
    except: ks = pd.DataFrame()
    try: kq = fdr.DataReader('KQ11', start, end)
    except: kq = pd.DataFrame()
    try: usd = fdr.DataReader('USD/KRW', start, end)
    except: usd = pd.DataFrame()
    return ks, kq, usd

def create_pro_chart(df, title, color_hex):
    if df.empty: return go.Figure().update_layout(title="데이터 없음")
    current_val, prev_val = df['Close'].iloc[-1], (df['Close'].iloc[-2] if len(df)>1 else df['Close'].iloc[-1])
    delta = current_val - prev_val
    delta_percent = (delta / prev_val) * 100

    fig = go.Figure(go.Scatter(x=df.index, y=df['Close'], mode='lines', line=dict(color=color_hex, width=2), fill='tozeroy', fillcolor=f"rgba({int(color_hex[1:3],16)}, {int(color_hex[3:5],16)}, {int(color_hex[5:7],16)}, 0.1)"))
    # 모바일에 맞게 높이 축소
    fig.update_layout(
        title=dict(text=f"<b>{title}</b> <span style='font-size:12px; color:{'#ff4b4b' if delta>=0 else '#0068c9'}'>{current_val:,.2f} ({delta_percent:+.2f}%)</span>", x=0.05, y=0.85),
        height=180, margin=dict(l=0, r=0, t=40, b=0), template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False), yaxis=dict(visible=False)
    )
    return fig

# =============================================================================
# 📱 탭(Tab) 기반 모바일 UI 구성
# =============================================================================
tab1, tab2, tab3 = st.tabs(["🎯 종목 스캐너", "📊 시장 동향", "⚙️ 설정/가이드"])

# -----------------------------------------------------------------------------
# 탭 1: 핵심! AI 단타 스캐너 (모바일 테이블 & 차트)
# -----------------------------------------------------------------------------
with tab1:
    df_universe = get_kis_top_trading_value_stocks()
    if not df_universe.empty:
        filtered_df = df_universe[df_universe['등락률'] > -2.0].copy()

        # 🧠 AI 모델 로드
        X_live = filtered_df[['등락률', '거래대금', '현재가']].fillna(0)
        model_path = "stock_dual_model.pkl" 
        
        if os.path.exists(model_path):
            try:
                dual_models = joblib.load(model_path)
                filtered_df['10분_상승예측(%)'] = np.round(dual_models['model_10min'].predict(X_live), 2)
                filtered_df['종가_상승예측(%)'] = np.round(dual_models['model_close'].predict(X_live), 2)
            except:
                filtered_df['10분_상승예측(%)'], filtered_df['종가_상승예측(%)'] = 0.0, 0.0
        else:
            filtered_df['10분_상승예측(%)'] = ((filtered_df['등락률'] * 0.5) + np.log1p(filtered_df['거래대금'])).round(2)
            filtered_df['종가_상승예측(%)'] = 0.0

        filtered_df['테마'] = filtered_df['종목명'].apply(get_theme_icon)

        def detect_signal(row):
            if row['등락률'] >= 7.0 and row['거래대금'] > 50000: return "🔥돌파"
            elif 1.0 <= row['등락률'] < 5.0 and row['거래대금'] > 20000: return "💧눌림"
            return "▪️관망"
        filtered_df['상태'] = filtered_df.apply(detect_signal, axis=1)

        top_30 = filtered_df.sort_values(by='10분_상승예측(%)', ascending=False).head(30)

        # 모바일용으로 열(Column) 갯수 대폭 축소
        output_df = pd.DataFrame({
            '상태': top_30['상태'],
            '종목명': top_30['종목명'].str.slice(0, 8), # 이름이 길면 자름
            'AI(10분)': top_30['10분_상승예측(%)'].apply(lambda x: f"+{x}%"), 
            '현재가': top_30['현재가'].apply(lambda x: f"{int(x):,}"),
            '등락률': top_30['등락률'].apply(lambda x: f"{x:.1f}%"),
            '종목코드': top_30['종목코드'],
            '종가AI': top_30['종가_상승예측(%)'],
            '테마': top_30['테마']
        }).reset_index(drop=True)

        st.caption("👇 종목을 터치하면 아래에 1분봉 차트가 열립니다.")
        
        # 모바일용 간소화된 데이터프레임
        selected_rows = st.dataframe(
            output_df[['상태', '종목명', 'AI(10분)', '현재가', '등락률']], # 모바일엔 핵심만!
            use_container_width=True, 
            selection_mode="single-row",
            on_select="rerun",
            hide_index=True
        )

        # 종목 클릭 시 차트 렌더링
        if hasattr(selected_rows, 'selection') and len(selected_rows.selection.rows) > 0:
            selected_idx = selected_rows.selection.rows[0]
            target_code = output_df.iloc[selected_idx]['종목코드']
            target_name = output_df.iloc[selected_idx]['종목명']
            
            st.markdown(f"### 📊 {target_name} 1분봉")
            
            with st.spinner("차트 로딩중..."):
                url = f"{URL_BASE}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
                headers = get_common_headers("FHKST03010200")
                params = {"FID_ETC_CLS_CODE": "", "FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": target_code, "FID_INPUT_HOUR_1": datetime.now(KST).strftime("%H%M%S"), "FID_PW_DATA_INCU_YN": "Y"}
                
                try:
                    res = requests.get(url, headers=headers, params=params)
                    res_data = res.json()
                    
                    if res_data['rt_cd'] == '0' and 'output2' in res_data:
                        min_data = res_data['output2'][::-1] 
                        times = [f"{m['stck_bsop_date']} {m['stck_cntg_hour']}" for m in min_data]
                        df_min = pd.DataFrame({
                            "Open": [float(m['stck_oprc']) for m in min_data],
                            "High": [float(m['stck_hgpr']) for m in min_data],
                            "Low": [float(m['stck_lwpr']) for m in min_data],
                            "Close": [float(m['stck_prpr']) for m in min_data],
                            "Volume": [float(m['cntg_vol']) for m in min_data]
                        }, index=pd.to_datetime(times, format="%Y%m%d %H%M%S"))
                        df_min = df_min[df_min['Close'] > 0]
                        
                        if not df_min.empty:
                            df_min['MA5'] = df_min['Close'].rolling(5).mean()
                            df_min['MA20'] = df_min['Close'].rolling(20).mean()
                            
                            fig_stock = go.Figure(data=[go.Candlestick(x=df_min.index, open=df_min['Open'], high=df_min['High'], low=df_min['Low'], close=df_min['Close'], increasing_line_color='#ff4b4b', decreasing_line_color='#0068c9')])
                            fig_stock.add_trace(go.Scatter(x=df_min.index, y=df_min['MA5'], mode='lines', line=dict(color='#ff9900', width=1.5)))
                            
                            # 모바일 환경에 맞춘 차트 설정 (높이 400으로 대폭 축소, 좌우 여백 삭제)
                            fig_stock.update_layout(
                                height=380, margin=dict(l=0, r=40, t=10, b=10),
                                xaxis=dict(rangeslider=dict(visible=False), showgrid=False),
                                yaxis=dict(side='right', showgrid=True),
                                showlegend=False
                            )
                            st.plotly_chart(fig_stock, use_container_width=True)
                except Exception as e:
                    st.error("차트 로딩 실패")
    else:
        st.warning("데이터가 없습니다.")

# -----------------------------------------------------------------------------
# 탭 2: 시장 동향 (지수 & 수급)
# -----------------------------------------------------------------------------
with tab2:
    st.subheader("🌐 지수 현황")
    ks_df, kq_df, usd_df = get_market_indices_v2()
    # 모바일은 세로로 쌓이는 것이 기본이므로 columns 사용 자제
    st.plotly_chart(create_pro_chart(ks_df, "KOSPI", "#FF4B4B"), use_container_width=True)
    st.plotly_chart(create_pro_chart(kq_df, "KOSDAQ", "#00CC96"), use_container_width=True)
    
    st.markdown("---")
    st.subheader("💼 외국인 선물 수급")
    
    if 'foreign_futures_net' not in st.session_state:
        st.session_state.foreign_futures_net = get_foreign_investor_trend()
    net_buy = st.session_state.foreign_futures_net
    
    if net_buy > 0:
        val_str, msg, clr = f"+{net_buy:,}억", "매수 우위 (시장 주도)", "normal"
    elif net_buy < 0:
        val_str, msg, clr = f"{net_buy:,}억", "매도 우위 (하락 압박)", "inverse"
    else:
        val_str, msg, clr = "0억", "데이터 대기중", "off"

    st.metric("실시간 순매수", val_str, msg, delta_color=clr)
    
    if st.button("🔄 수급 새로고침", use_container_width=True):
        get_foreign_investor_trend.clear() 
        st.session_state.foreign_futures_net = get_foreign_investor_trend()
        st.rerun()

# -----------------------------------------------------------------------------
# 탭 3: 자동 새로고침 및 설정
# -----------------------------------------------------------------------------
with tab3:
    st.subheader("⏱️ 시스템 설정")
    auto_refresh = st.toggle("1분 자동 스캐닝 켜기", value=False)
    
    if auto_refresh:
        try:
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=60000, limit=1000, key="auto_refresh")
            st.success("자동 새로고침 작동 중")
        except:
            st.error("streamlit-autorefresh 미설치")
            
    st.markdown("---")
    st.info("""
    **💡 모바일 활용 팁**
    1. **스캐너 탭**에서 종목을 터치해 차트를 봅니다.
    2. 너무 많은 열을 띄우면 스크롤이 불편하므로 핵심만 남겼습니다.
    3. 수동 새로고침 시 화면을 아래로 당기지 마시고, 탭2의 버튼을 이용하세요.
    """)
