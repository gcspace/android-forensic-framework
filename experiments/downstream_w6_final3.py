#!/usr/bin/env python3
"""下游验证 W=6：精确文件匹配版（使用实际文件名）"""

import json, numpy as np
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix
from sklearn.preprocessing import StandardScaler

OP_TYPE_MAP = {'UI_CLICK':0,'UI_SWIPE':1,'UI_INPUT':2,'APP_START':3,'APP_STOP':4,
               'FILE_CREATE':5,'FILE_COPY':6,'FILE_DELETE':7,'NET_DOWNLOAD':8}

def load_atoms_from_json(path):
    with open(path) as f:
        data = json.load(f)
    atoms = data.get('atoms', [])
    X = []
    for atom in atoms:
        duration = min(atom.get('duration_ms', 0.0), 5000.0)
        op_type = OP_TYPE_MAP.get(atom.get('op_type', ''), 0)
        ts = atom.get('timestamp_ms', 0) % 1000
        X.append([duration, op_type, ts])
    return np.array(X)

def load_files(file_list, label):
    X_all = []
    for f in file_list:
        X = load_atoms_from_json(f)
        X_all.extend(X)
        print(f"  加载 {f} -> {len(X)} 个原子")
    return np.array(X_all), [label] * len(X_all)

base = 'output/groundtruth/'

# baseline_50（16:02~16:05，5个）
normal_files = [
    f'{base}real_execution_20260822_160250.json',
    f'{base}real_execution_20260822_160323.json',
    f'{base}real_execution_20260822_160356.json',
    f'{base}real_execution_20260822_160428.json',
    f'{base}real_execution_20260822_160500.json',
]

# 隐私窃取（16:17:14~16:17:36，5个）
privacy_files = [
    f'{base}real_execution_20260822_161714.json',
    f'{base}real_execution_20260822_161719.json',
    f'{base}real_execution_20260822_161725.json',
    f'{base}real_execution_20260822_161730.json',
    f'{base}real_execution_20260822_161736.json',
]

# 钓鱼登录（16:17:42~16:18:06，5个）
phishing_files = [
    f'{base}real_execution_20260822_161742.json',
    f'{base}real_execution_20260822_161748.json',
    f'{base}real_execution_20260822_161754.json',
    f'{base}real_execution_20260822_161800.json',
    f'{base}real_execution_20260822_161806.json',
]

# 勒索加密（16:18:12~16:18:34，5个）
ransomware_files = [
    f'{base}real_execution_20260822_161812.json',
    f'{base}real_execution_20260822_161817.json',
    f'{base}real_execution_20260822_161823.json',
    f'{base}real_execution_20260822_161828.json',
    f'{base}real_execution_20260822_161834.json',
]

print("加载数据...")
print("\n【正常场景】")
X_normal, y_normal = load_files(normal_files, 0)
print("\n【隐私窃取】")
X_privacy, y_privacy = load_files(privacy_files, 1)
print("\n【钓鱼登录】")
X_phishing, y_phishing = load_files(phishing_files, 1)
print("\n【勒索加密】")
X_ransom, y_ransom = load_files(ransomware_files, 1)

print(f"\n{'='*50}")
print(f"汇总:")
print(f"正常样本: {len(X_normal)} 个原子")
print(f"隐私窃取: {len(X_privacy)} 个原子")
print(f"钓鱼登录: {len(X_phishing)} 个原子")
print(f"勒索加密: {len(X_ransom)} 个原子")

def run_experiment(name, X, y):
    print(f"\n{'='*50}")
    print(f"实验: {name}")
    print(f"样本数: {len(X)}")
    
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )
    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_test = scaler.transform(X_test)
    
    rf = RandomForestClassifier(n_estimators=200, max_depth=8, min_samples_split=5, random_state=42)
    rf.fit(X_train, y_train)
    y_pred = rf.predict(X_test)
    
    print(f"准确率: {accuracy_score(y_test, y_pred):.4f}")
    print(f"精确率: {precision_score(y_test, y_pred):.4f}")
    print(f"召回率: {recall_score(y_test, y_pred):.4f}")
    print(f"F1: {f1_score(y_test, y_pred):.4f}")
    print(f"混淆矩阵:\n{confusion_matrix(y_test, y_pred)}")
    
    cv_scores = cross_val_score(rf, X, y, cv=5)
    print(f"5折CV准确率: {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")

# 实验1：勒索 vs 正常
X1 = np.vstack([X_normal, X_ransom])
y1 = np.array(y_normal + y_ransom)
run_experiment("勒索场景 vs 正常（5次合并）", X1, y1)

# 实验2：三类恶意合并 vs 正常
X_malicious = np.vstack([X_privacy, X_phishing, X_ransom])
y_malicious = y_privacy + y_phishing + y_ransom
X2 = np.vstack([X_normal, X_malicious])
y2 = np.array(y_normal + y_malicious)
run_experiment("三类恶意合并 vs 正常（5次合并）", X2, y2)
