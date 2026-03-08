import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score, mean_squared_error
import os
from datetime import datetime

# Set Korean font
plt.rcParams['font.family'] = 'AppleGothic'
plt.rcParams['axes.unicode_minus'] = False

os.makedirs('results/figures/what_if', exist_ok=True)

# 1. Load Data
df_master = pd.read_csv('data/processed/webtoon_master_data.csv')
df_success = pd.read_csv('data/processed/Webtoon_Success_Results.csv', header=None)
df_success.columns = ["title", "platform", "raw_views", "date_range", "rating1", "rating2", "interest", "success_score"]

# 2. Preprocess
def calculate_duration_months(date_str):
    if pd.isna(date_str): return 1.0
    dates = str(date_str).split('~')
    try:
        if len(dates) == 2:
            start = datetime.strptime(dates[0].strip(), '%Y.%m.%d')
            end = datetime.strptime(dates[1].strip(), '%Y.%m.%d')
            return max(1.0, (end.year - start.year) * 12 + (end.month - start.month))
        else: return 1.0
    except: return 1.0

df_success['months'] = df_success['date_range'].apply(calculate_duration_months)
df_success['raw_views'] = pd.to_numeric(df_success['raw_views'], errors='coerce').fillna(0)
df_success['views_velocity'] = df_success['raw_views'] / df_success['months']

# Focus on Top Genre (Romance)
top_genre = '로맨스'
df_master_genre = df_master[df_master['genre'] == top_genre]

dna_columns = ['lighting', 'shot', 'angle']
agg_df_list = []
for title, group in df_master_genre.groupby('title'):
    row_dict = {'title': title}
    for col in dna_columns:
        counts = group[col].value_counts(normalize=True)
        for cat, prop in counts.items():
            row_dict[f'{col}_{cat}'] = prop
    agg_df_list.append(row_dict)

df_dna_agg = pd.DataFrame(agg_df_list).fillna(0)
df_merged = pd.merge(df_dna_agg, df_success, on='title', how='inner')

feature_cols = [c for c in df_merged.columns if any(c.startswith(dna + '_') for dna in dna_columns)]
X = df_merged[feature_cols]
y = df_merged['views_velocity'] # Predict raw velocity directly for understandable numbers

# 3. Train Model & Get Metrics
rf = RandomForestRegressor(n_estimators=100, random_state=42)
rf.fit(X, y)
y_pred = rf.predict(X)

r2 = r2_score(y, y_pred)
rmse = np.sqrt(mean_squared_error(y, y_pred))

print(f"--- Model Metrics (Random Forest) ---")
print(f"R-Squared (설명력): {r2:.3f}")
print(f"RMSE (평균 오차): {rmse:.3f}")

# 4. What-If Simulation
# Let's find an underperforming webtoon to simulate improvements
underperforming_title = df_merged.sort_values('views_velocity').iloc[1]['title'] # Grab the second lowest to avoid absolute 0 if any
current_webtoon = df_merged[df_merged['title'] == underperforming_title]
current_X = current_webtoon[feature_cols]
current_predicted_y = rf.predict(current_X)[0]

# "Growth Hack" Action: Modify DNA based on previous importance (Increase '역광조명' and '아이레벨')
new_X = current_X.copy()
# Assuming the feature exists, we boost it. If it doesn't exist, we add it.
if 'lighting_역광조명' in new_X.columns:
    new_X['lighting_역광조명'] = new_X['lighting_역광조명'].replace(0, 0.1) * 2.0 # Force increase
    if new_X['lighting_역광조명'].iloc[0] > 1.0: new_X['lighting_역광조명'] = 1.0
if 'angle_아이레벨' in new_X.columns:
    new_X['angle_아이레벨'] = new_X['angle_아이레벨'].replace(0, 0.1) * 1.5
    if new_X['angle_아이레벨'].iloc[0] > 1.0: new_X['angle_아이레벨'] = 1.0
    
# Reduce negative traits (e.g. 측면조명)
if 'lighting_측면조명' in new_X.columns:
    new_X['lighting_측면조명'] = new_X['lighting_측면조명'] * 0.2

# Normalize rows back to 1.0 sum per category to be realistic
for cat in dna_columns:
    cat_cols = [c for c in new_X.columns if c.startswith(cat)]
    row_sum = new_X[cat_cols].sum(axis=1)
    for c in cat_cols:
         if row_sum.iloc[0] > 0:
             new_X[c] = new_X[c] / row_sum.iloc[0]

new_predicted_y = rf.predict(new_X)[0]
growth_pct = ((new_predicted_y - current_predicted_y) / current_predicted_y) * 100

print(f"\n--- What-If Simulation Results ---")
print(f"Target Webtoon: {underperforming_title}")
print(f"Current Predicted Velocity: {current_predicted_y:.2f} (10k views/month)")
print(f"New Predicted Velocity (After DNA adjustment): {new_predicted_y:.2f} (10k views/month)")
print(f"Expected Growth: +{growth_pct:.1f}%")

# 5. Visualization (Before vs After)
plt.figure(figsize=(8, 6))
bars = plt.bar(['현재 DNA (Before)', '개선된 DNA (After)'], [current_predicted_y, new_predicted_y], color=['#FF9999', '#66B2FF'])

# Add percentage text
plt.text(1, new_predicted_y + (new_predicted_y*0.02), f"↑ {growth_pct:.1f}% 상승 예상", ha='center', va='bottom', fontsize=12, fontweight='bold', color='blue')

plt.title(f"[{underperforming_title}] 썸네일 DNA 개선에 따른 예상 조회수 변화 (What-If 시뮬레이션)", fontsize=14)
plt.ylabel("월평균 예측 조회수 (단위: 만 회)")

# Add value labels
for bar in bars:
    yval = bar.get_height()
    plt.text(bar.get_x() + bar.get_width()/2, yval/2, f"{yval:.2f}만", ha='center', va='center', fontsize=12, color='white', fontweight='bold')

plt.tight_layout()
plt.savefig('results/figures/what_if/4_simulation_result.png')
plt.close()

# Save metrics for markdown
with open('results/figures/what_if/sim_metrics.txt', 'w') as f:
    f.write(f"{r2:.3f},{rmse:.3f},{underperforming_title},{current_predicted_y:.2f},{new_predicted_y:.2f},{growth_pct:.1f}")

print("Simulation complete. Image saved to results/figures/what_if/4_simulation_result.png.")
