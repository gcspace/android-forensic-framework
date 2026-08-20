#!/usr/bin/env python3
"""
下游任务验证：时序异常检测模型
使用生成的数据集训练分类器，区分恶意与正常行为
"""

import json
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
import glob
import os

print("=" * 60)
print("下游任务验证：时序异常检测模型")
print("=" * 60)

DATA_DIR = "output/groundtruth"

# 操作类型映射
OP_MAP = {
    'UI_CLICK': 0, 'UI_SWIPE': 1, 'UI_INPUT': 2,
    'FILE_CREATE': 3, 'FILE_DELETE': 4, 'FILE_COPY': 5,
    'APP_START': 6, 'APP_STOP': 7, 'NET_DOWNLOAD': 8
}

def extract_features(json_path):
    with open(json_path, 'r') as f:
        data = json.load(f)
    features = []
    for ev in data.get('evidence', []):
        dur = ev.get('duration_ms', 0)
        op = ev.get('op_type', 'UNKNOWN')
        ts = ev.get('timestamp', 0)
        op_code = OP_MAP.get(op, -1)
        features.append([dur, op_code, ts % 1000])
    return np.array(features)

# 获取所有恶意场景文件（勒索加密）
malicious_patterns = [
    "real_execution_20260818_153407.json",  # 勒索加密（修正前）
    "real_execution_20260818_155932.json",  # 勒索加密
    "real_execution_20260818_165523.json",  # 钓鱼登录
    "real_execution_20260818_164449.json",  # 隐私窃取
]
# 实际存在的恶意文件
malicious_files = []
for p in malicious_patterns:
    full_path = os.path.join(DATA_DIR, p)
    if os.path.exists(full_path):
        malicious_files.append(full_path)

# 获取所有基准场景文件
baseline_files = sorted(glob.glob(os.path.join(DATA_DIR, "real_execution_20260818_11*.json")))

print(f"找到 {len(malicious_files)} 个恶意场景文件")
for f in malicious_files:
    print(f"  - {os.path.basename(f)}")
print(f"找到 {len(baseline_files)} 个基准场景文件")
for f in baseline_files:
    print(f"  - {os.path.basename(f)}")

X_all, y_all = [], []

# 加载恶意样本
for f in malicious_files:
    X = extract_features(f)
    if len(X) > 0:
        X_all.append(X)
        y_all.append(np.ones(len(X)))

# 加载正常样本
for f in baseline_files:
    X = extract_features(f)
    if len(X) > 0:
        X_all.append(X)
        y_all.append(np.zeros(len(X)))

if len(X_all) == 0:
    print("❌ 未找到任何数据文件！")
    exit(1)

X_all = np.vstack(X_all)
y_all = np.concatenate(y_all)

print(f"\n总样本: {len(X_all)}, 恶意: {int(sum(y_all))}, 正常: {int(len(y_all)-sum(y_all))}")

# 训练/测试划分 (8:2)
X_train, X_test, y_train, y_test = train_test_split(
    X_all, y_all, test_size=0.2, random_state=42, stratify=y_all
)

# 训练
clf = RandomForestClassifier(n_estimators=100, random_state=42, max_depth=10)
clf.fit(X_train, y_train)
y_pred = clf.predict(X_test)

# 评估
acc = accuracy_score(y_test, y_pred)
prec = precision_score(y_test, y_pred)
rec = recall_score(y_test, y_pred)
f1 = f1_score(y_test, y_pred)

print("\n" + "=" * 60)
print("模型评估结果 (8:2 划分):")
print("=" * 60)
print(f"准确率 (Accuracy):  {acc:.2%}")
print(f"精确率 (Precision): {prec:.2%}")
print(f"召回率 (Recall):    {rec:.2%}")
print(f"F1 分数:            {f1:.2f}")

# 交叉验证
cv_scores = cross_val_score(clf, X_all, y_all, cv=5)
print(f"\n5折交叉验证平均准确率: {cv_scores.mean():.2%} ± {cv_scores.std():.2%}")
