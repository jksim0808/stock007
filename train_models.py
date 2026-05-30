import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
import joblib

print("🚀 [실전형] 듀얼 AI 예측 모델 학습을 시작합니다...")

np.random.seed(777)
n_samples = 3000

X_train = pd.DataFrame({
    '등락률': np.random.uniform(-5.0, 25.0, n_samples),
    '거래대금': np.random.uniform(5000, 150000, n_samples),
    '현재가': np.random.uniform(5000, 150000, n_samples)
})

y_10min = (X_train['등락률'] * 0.1) + (np.log1p(X_train['거래대금']) * 0.5) + np.random.normal(0, 1.5, n_samples)
y_close = (X_train['등락률'] * 0.05) + (np.log1p(X_train['거래대금']) * 0.8) + np.random.normal(0, 3.0, n_samples)

print("⏳ 10분 뒤 단기 예측 모델(단타용) 학습 중...")
model_10min = RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42)
model_10min.fit(X_train, y_10min)

print("⏳ 장 마감 종가 예측 모델(홀딩용) 학습 중...")
model_close = RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42)
model_close.fit(X_train, y_close)

dual_models = {
    'model_10min': model_10min,
    'model_close': model_close
}

file_name = 'stock_dual_model.pkl'
joblib.dump(dual_models, file_name)

print(f"✅ 학습 완료! '{file_name}' 파일이 생성되었습니다.")
