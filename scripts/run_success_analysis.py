import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import statsmodels.api as sm
import os
import re
from datetime import datetime

# Set Korean font for matplotlib (Mac default is AppleGothic)
plt.rcParams['font.family'] = 'AppleGothic'
plt.rcParams['axes.unicode_minus'] = False

os.makedirs('results/figures/analysis', exist_ok=True)

# 1. Load Data
# Master data containing image-level DNA
df_master = pd.read_csv('data/processed/webtoon_master_data.csv')

# Success results (No header in original file)
df_success = pd.read_csv('data/processed/Webtoon_Success_Results.csv', header=None)
df_success.columns = ["title", "platform", "raw_views", "date_range", "rating1", "rating2", "interest", "success_score"]

# 2. Data Preprocessing & Normalization
def calculate_duration_months(date_str):
    if pd.isna(date_str):
        return 1.0 # Default to 1 month
    
    dates = str(date_str).split('~')
    try:
        if len(dates) == 2:
            start = datetime.strptime(dates[0].strip(), '%Y.%m.%d')
            end = datetime.strptime(dates[1].strip(), '%Y.%m.%d')
            months = (end.year - start.year) * 12 + (end.month - start.month)
            return max(1.0, months)
        else:
            return 1.0 # Single date
    except:
        return 1.0

# Normalize Views
# If raw_views is just a number string, convert it, if it contains '만' or '억', we'd need parsing, but from our inspection it's just '1', '155' etc.
df_success['months'] = df_success['date_range'].apply(calculate_duration_months)
df_success['raw_views'] = pd.to_numeric(df_success['raw_views'], errors='coerce').fillna(0)
# Velocity = raw_views / months
df_success['views_velocity'] = df_success['raw_views'] / df_success['months']
df_success['views_velocity_log'] = np.log1p(df_success['views_velocity'])

# 3. Aggregate DNA Features per Webtoon
# df_master has multiple rows per title. We will calculate the proportion of each DNA class per title.
dna_columns = ['lighting', 'shot', 'angle']
agg_df_list = []

for title, group in df_master.groupby('title'):
    genre = group['genre'].iloc[0] if not group['genre'].empty else 'Unknown'
    row_dict = {'title': title, 'genre': genre}
    
    # For each categorical DNA, calculate proportion of its values
    for col in dna_columns:
        counts = group[col].value_counts(normalize=True)
        for cat, prop in counts.items():
            row_dict[f'{col}_{cat}'] = prop
            
    agg_df_list.append(row_dict)

df_dna_agg = pd.DataFrame(agg_df_list).fillna(0)

# Merge DNA data with Success metrics
df_merged = pd.merge(df_dna_agg, df_success, on='title', how='inner')

print(f"Merged Dataset Shape: {df_merged.shape}")

# 4. Filter by Genre (Let's select the most common genre for analysis, e.g., '로맨스' or '판타지')
# Find top genre
top_genre = df_merged['genre'].value_counts().index[0]
df_genre = df_merged[df_merged['genre'] == top_genre].copy()
print(f"Analyzing Top Genre: {top_genre} with {len(df_genre)} samples.")

# Prepare X and y
feature_cols = [c for c in df_genre.columns if any(c.startswith(dna + '_') for dna in dna_columns)]
X = df_genre[feature_cols]
y = df_genre['views_velocity_log']  # Target Variable

# 5. Multiple Regression (Statsmodels) to find P-values
# Add constant for intercept
X_sm = sm.add_constant(X)
model = sm.OLS(y, X_sm).fit()
print("\n--- Regression Results ---")
print(model.summary())

# Extract significant features (p < 0.1)
p_values = model.pvalues[1:] # Exclude const
significant_features = p_values[p_values < 0.1].index.tolist()

# 6. Random Forest for Feature Importance
rf = RandomForestRegressor(n_estimators=100, random_state=42)
rf.fit(X, y)
importances = rf.feature_importances_
feat_imp = pd.Series(importances, index=feature_cols).sort_values(ascending=False).head(10)

# ==================== VISUALIZATIONS ==================== #

# Visual 1: Correlation Heatmap (Top 10 features + Target)
plt.figure(figsize=(10, 8))
top_corr_features = list(feat_imp.index)
corr_matrix = df_genre[top_corr_features + ['views_velocity_log', 'rating1']].corr()

sns.heatmap(corr_matrix, annot=True, cmap='coolwarm', fmt=".2f", vmin=-1, vmax=1)
plt.title(f'[{top_genre}] DNA 특성과 성공 지표 간의 상관관계 히트맵', fontsize=15)
plt.tight_layout()
plt.savefig('results/figures/analysis/1_correlation_heatmap.png')
plt.close()

# Visual 2: Boxplot for Top DNA Feature
# Let's take the most important feature that is binary-like or we can binarize (high vs low proportion)
top_feature = feat_imp.index[0]
df_genre['top_feature_group'] = pd.qcut(df_genre[top_feature], q=2, labels=['낮은 비율', '높은 비율'], duplicates='drop')
try:
    plt.figure(figsize=(8, 6))
    sns.boxplot(x='top_feature_group', y='views_velocity', data=df_genre, palette='Set2')
    plt.yscale('log') # Log scale for better visibility if skewed
    plt.title(f"[{top_genre}] '{top_feature}' 비중에 따른 월평균 조회수(Velocity) 차이", fontsize=14)
    plt.ylabel("월평균 조회수 (Log Scale)")
    plt.xlabel(f"{top_feature} 포함 비중")
    plt.tight_layout()
    plt.savefig('results/figures/analysis/2_boxplot_performance.png')
    plt.close()
except Exception as e:
    print(f"Could not generate Boxplot: {e}")

# Visual 3: Feature Importance Bar Chart
plt.figure(figsize=(10, 6))
sns.barplot(x=feat_imp.values, y=feat_imp.index, palette='viridis')
plt.title(f"[{top_genre}] 신작 성과 예측을 위한 핵심 DNA 변수 중요도 (Random Forest)", fontsize=15)
plt.xlabel("상대적 중요도 (Feature Importance)")
plt.ylabel("웹툰 DNA 피처")
plt.tight_layout()
plt.savefig('results/figures/analysis/3_feature_importance.png')
plt.close()

print("\nAnalysis completed. Visualizations saved to results/figures/analysis/.")

# Export a short success report
with open('results/figures/analysis/regression_summary.txt', 'w') as f:
    f.write(f"Analyzed Genre: {top_genre}\n")
    f.write(f"Sample Size: {len(df_genre)}\n\n")
    f.write(model.summary().as_text())
