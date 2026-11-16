#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分类实验重做：按“运行文件”分组划分，消除同源泄漏，并补 P/R/F1 与混淆矩阵。

对应审1-7（175 vs 600 不平衡只报准确率）与审2-9（随机 8:2 同源泄漏）。
原始数据沿用 output/groundtruth 下的 real_execution_*.json，不重跑模拟器。

用法：
  python experiments/paper/split_by_source.py \
      --malicious 'output/groundtruth/real_execution_20260818_165*.json' \
      --normal    'output/groundtruth/real_execution_20260818_113*.json' \
      --out output/paper/ml/split_summary.json
"""

import argparse
import glob
import json
import os
import sys

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                             precision_score, recall_score)
from sklearn.model_selection import GroupKFold, GroupShuffleSplit, train_test_split

OP_MAP = {'UI_CLICK': 0, 'UI_SWIPE': 1, 'UI_INPUT': 2, 'FILE_CREATE': 3,
          'FILE_DELETE': 4, 'FILE_COPY': 5, 'APP_START': 6, 'APP_STOP': 7,
          'NET_DOWNLOAD': 8}


def extract(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    rows = []
    for ev in data.get("evidence", []) or data.get("atoms", []):
        rows.append([
            float(ev.get("duration_ms", 0) or 0),
            OP_MAP.get(ev.get("op_type"), -1),
            float(ev.get("timestamp", ev.get("timestamp_start", 0)) or 0) % 1000,
        ])
    return np.array(rows) if rows else np.zeros((0, 3))


def load(globs, label):
    X, y, groups = [], [], []
    for pat in globs:
        for f in sorted(glob.glob(pat)):
            m = extract(f)
            if len(m) == 0:
                continue
            X.append(m)
            y += [label] * len(m)
            groups += [os.path.basename(f)] * len(m)
    if not X:
        raise SystemExit("没有读到样本：%s" % ", ".join(globs))
    return np.vstack(X), np.array(y), np.array(groups)


def report(tag, y_true, y_pred):
    return {
        "split": tag,
        "n_test": int(len(y_true)),
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "precision": round(precision_score(y_true, y_pred, zero_division=0), 4),
        "recall": round(recall_score(y_true, y_pred, zero_division=0), 4),
        "f1": round(f1_score(y_true, y_pred, zero_division=0), 4),
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--malicious", nargs="+", required=True)
    ap.add_argument("--normal", nargs="+", required=True)
    ap.add_argument("--out", default="output/paper/ml/split_summary.json")
    args = ap.parse_args()

    Xm, ym, gm = load(args.malicious, 1)
    Xn, yn, gn = load(args.normal, 0)
    X = np.vstack([Xm, Xn])
    y = np.concatenate([ym, yn])
    groups = np.concatenate([gm, gn])
    print("样本 %d（恶意 %d / 正常 %d），来源文件 %d 个" % (len(y), len(ym), len(yn), len(set(groups))))

    clf_kw = dict(n_estimators=100, random_state=42, max_depth=10, class_weight="balanced")

    res = []
    # 旧口径：按事件随机 8:2（会泄漏）
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    clf = RandomForestClassifier(**clf_kw).fit(Xtr, ytr)
    pred = clf.predict(Xte)
    res.append(report("random_8_2(旧口径)", yte, pred))

    # 新口径：按来源文件分组 8:2
    gss = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    tr, te = next(gss.split(X, y, groups))
    clf = RandomForestClassifier(**clf_kw).fit(X[tr], y[tr])
    pred = clf.predict(X[te])
    res.append(report("group_split(按文件)", y[te], pred))

    # 分组交叉验证
    gkf = GroupKFold(n_splits=5)
    accs, f1s = [], []
    for tr, te in gkf.split(X, y, groups):
        clf = RandomForestClassifier(**clf_kw).fit(X[tr], y[tr])
        pred = clf.predict(X[te])
        accs.append(accuracy_score(y[te], pred))
        f1s.append(f1_score(y[te], pred, zero_division=0))
    res.append({"split": "group_kfold_5", "accuracy_mean": round(float(np.mean(accs)), 4),
                "accuracy_sd": round(float(np.std(accs)), 4),
                "f1_mean": round(float(np.mean(f1s)), 4),
                "f1_sd": round(float(np.std(f1s)), 4)})

    # 特征重要性，用于审1-6“timestamp%1000 伪相关”的讨论
    clf = RandomForestClassifier(**clf_kw).fit(X, y)
    imp = clf.feature_importances_.tolist()
    res.append({"feature_importance": {"duration_ms": round(imp[0], 4),
                                      "op_type": round(imp[1], 4),
                                      "timestamp_mod_1000": round(imp[2], 4)}})

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"n_samples": int(len(y)), "n_malicious": int(len(ym)),
                   "n_normal": int(len(yn)), "n_source_files": int(len(set(groups))),
                   "results": res}, fh, ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    print("saved:", args.out)


if __name__ == "__main__":
    main()
