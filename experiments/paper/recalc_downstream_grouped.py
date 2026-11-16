# -*- coding: utf-8 -*-
"""下游检测复算：按运行批次分组划分，输出准确率/精确率/召回率/F1。

用法:
    python recalc_downstream_grouped.py --dir results_dir     # 目录内全部 *.json
    python recalc_downstream_grouped.py --tar results.tar.gz  # 打包结果

说明:
  * 特征: duration_ms(截断5000) / op_type编码 / timestamp_start % 1000
  * 正常样本: 场景名含 baseline_50 的前 12 轮运行
  * 恶意样本: 场景名含 ransomware / phishing / privacy 的运行
  * 划分: 随机分层8:2 与 按运行批次分组(同run不跨集合, 逐场景留最后一轮作测试)
  * 分类器: 随机森林(200树, 最大深度8, 最小分裂5, 随机种子42)
"""
import argparse, glob, json, os, tarfile

import numpy as np

OP = {'UI_CLICK': 0, 'UI_SWIPE': 1, 'UI_INPUT': 2, 'APP_START': 3, 'APP_STOP': 4,
      'FILE_CREATE': 5, 'FILE_COPY': 6, 'FILE_DELETE': 7, 'NET_DOWNLOAD': 8,
      'UI_LONG_CLICK': 9, 'UI_ALERT_HANDLE': 10, 'MULTI_TOUCH': 11, 'FILE_MODIFY': 12,
      'MEDIA_SAF_ACCESS': 13, 'APP_INSTALL': 14, 'APP_UNINSTALL': 15}


def load_runs(args):
    runs = []
    if args.tar:
        with tarfile.open(args.tar) as tf:
            for n in tf.getnames():
                if n.endswith('.json'):
                    obj = json.loads(tf.extractfile(n).read().decode('utf-8'))
                    runs.append({'name': os.path.basename(n), 'sc': obj.get('scenario', ''),
                                 'w': obj.get('max_concurrency'), 'atoms': obj.get('atoms', [])})
    else:
        for p in sorted(glob.glob(os.path.join(args.dir, '**', '*.json'), recursive=True)):
            if not os.path.isfile(p):          # 打包约定里运行目录名可能以 .json 结尾，需跳过目录
                continue
            with open(p, encoding='utf-8') as f:
                obj = json.load(f)
            runs.append({'name': os.path.basename(p), 'sc': obj.get('scenario', ''),
                         'w': obj.get('max_concurrency'), 'atoms': obj.get('atoms', [])})
    return runs


def gini(y):
    if len(y) == 0:
        return 0.0
    p = y.mean()
    return 2 * p * (1 - p)


def best_split(X, y, feats):
    best = (None, None, 2e9)
    for f in feats:
        v = X[:, f]
        o = np.argsort(v)
        vs, ys = v[o], y[o]
        cut = np.where(np.diff(vs) > 0)[0]
        for c in cut:
            th = (vs[c] + vs[c + 1]) / 2
            l = v <= th
            nl, nr = int(l.sum()), int((~l).sum())
            if nl < 2 or nr < 2:
                continue
            g = (gini(y[l]) * nl + gini(y[~l]) * nr) / len(y)
            if g < best[2]:
                best = (f, th, g)
    return best


def grow(X, y, depth, rng, nfeat):
    if depth >= 8 or len(y) < 5 or y.min() == y.max():
        return ('leaf', float(y.mean()))
    feats = rng.choice(nfeat, max(1, int(np.sqrt(nfeat))), replace=False)
    f, th, _ = best_split(X, y, feats)
    if f is None:
        return ('leaf', float(y.mean()))
    l = X[:, f] <= th
    return ('node', f, th, grow(X[l], y[l], depth + 1, rng, nfeat),
            grow(X[~l], y[~l], depth + 1, rng, nfeat))


def pred_tree(t, x):
    while t[0] == 'node':
        t = t[3] if x[t[1]] <= t[2] else t[4]
    return t[1]


class RF:
    def __init__(self, n=200, seed=42):
        self.n, self.seed = n, seed

    def fit(self, X, y):
        rng = np.random.RandomState(self.seed)
        self.trees = [grow(X[i], y[i], 0, rng, X.shape[1])
                      for i in (rng.randint(0, len(y), len(y)) for _ in range(self.n))]
        return self

    def predict(self, X):
        out = np.zeros(len(X))
        for t in self.trees:
            out += np.array([pred_tree(t, x) for x in X])
        return (out / len(self.trees)) >= 0.5


def metrics(y, p):
    tp = int(((y == 1) & p).sum()); fp = int(((y == 0) & p).sum())
    fn = int(((y == 1) & (~p)).sum()); tn = int(((y == 0) & (~p)).sum())
    acc = (tp + tn) / len(y)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return acc, prec, rec, f1


def to_X(rs, with_ts=True):
    X = []
    for r in rs:
        for a in r['atoms']:
            row = [min(a.get('duration_ms', 0.0), 5000.0), OP.get(a.get('op_type', ''), -1)]
            if with_ts:
                row.append(a.get('timestamp_start', 0) % 1000)
            X.append(row)
    return np.array(X, dtype=float)


def four_class(runs):
    """四分类(正常/隐私/钓鱼/勒索)：一对多森林 + 按运行批次留一轮，输出准确率与各类召回。"""
    normal = sorted([r for r in runs if 'baseline_50' in r['sc']],
                    key=lambda x: (x['w'] if x['w'] else 99, x['name']))[:12]
    groups = [normal,
              [r for r in runs if 'privacy' in r['sc']],
              [r for r in runs if 'phishing' in r['sc']],
              [r for r in runs if 'ransomware' in r['sc']]]
    X, y, grp = [], [], []
    for cls, gp in enumerate(groups):
        X.append(to_X(gp, True))
        y += [cls] * int(sum(len(r['atoms']) for r in gp))
        grp += [r['name'] for r in gp for _ in r['atoms']]
    X, y = np.vstack(X), np.array(y)
    grp = np.array(grp)

    test_runs = {sorted(gp, key=lambda z: z['name'])[-1]['name'] for gp in groups if gp}
    spi = np.array([x in test_runs for x in grp])
    score = np.zeros((int(spi.sum()), 4))
    for cls in range(4):
        rf = RF().fit(X[~spi], (y[~spi] == cls).astype(float))
        score[:, cls] = np.mean([[pred_tree(t, x) for x in X[spi]] for t in rf.trees], axis=0)
    pred = score.argmax(axis=1)
    print('\n== 四分类(按运行批次留一轮) 样本 %d, 测试 %d ==' % (len(y), int(spi.sum())))
    print('  准确率 acc=%.4f' % float((pred == y[spi]).mean()))
    for c, name in enumerate(['正常', '隐私窃取', '钓鱼登录', '勒索加密']):
        m = y[spi] == c
        if m.sum():
            print('  %s 召回=%.4f (n=%d)' % (name, float((pred[m] == c).mean()), int(m.sum())))


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--dir')
    g.add_argument('--tar')
    ap.add_argument('--four-class', action='store_true',
                    help='输出四分类(正常/隐私/钓鱼/勒索)的分组划分配置')
    args = ap.parse_args()

    runs = load_runs(args)
    if getattr(args, 'four_class', False):
        four_class(runs)
        return
    normal = sorted([r for r in runs if 'baseline_50' in r['sc']],
                    key=lambda x: (x['w'] if x['w'] else 99, x['name']))[:12]
    mr = [r for r in runs if 'ransomware' in r['sc']]
    mp = [r for r in runs if 'phishing' in r['sc']]
    mv = [r for r in runs if 'privacy' in r['sc']]
    print('正常 %d 轮 %d 原子 | 勒索 %d | 钓鱼 %d | 隐私 %d'
          % (len(normal), sum(len(r['atoms']) for r in normal), len(mr), len(mp), len(mv)))

    for tag, mals in (('勒索 vs 正常', mr), ('三类合并 vs 正常', mr + mp + mv)):
        rs = normal + mals
        y = np.array([0] * sum(len(r['atoms']) for r in normal)
                     + [1] * sum(len(r['atoms']) for r in mals))
        grp = np.array([r['name'] for r in rs for _ in r['atoms']])
        X, Xn = to_X(rs, True), to_X(rs, False)

        rng = np.random.RandomState(42)
        idx = rng.permutation(len(y))
        tr, te = [], []
        for cls in (0, 1):
            ii = idx[y[idx] == cls]
            k = int(round(len(ii) * 0.8))
            tr += list(ii[:k]); te += list(ii[k:])
        mA = metrics(y[te], RF().fit(X[tr], y[tr]).predict(X[te]))

        test_runs = {sorted(gp, key=lambda z: z['name'])[-1]['name']
                     for gp in (normal, mr, mp, mv) if gp}
        spi = np.array([x in test_runs for x in grp])
        mB = metrics(y[spi], RF().fit(X[~spi], y[~spi]).predict(X[spi]))
        mC = metrics(y[spi], RF().fit(Xn[~spi], y[~spi]).predict(Xn[spi]))

        print('\n== %s 样本 %d ==' % (tag, len(y)))
        print('  随机8:2            acc=%.4f P=%.4f R=%.4f F1=%.4f' % mA)
        print('  按批次分组          acc=%.4f P=%.4f R=%.4f F1=%.4f' % mB)
        print('  分组+去时间戳特征   acc=%.4f P=%.4f R=%.4f F1=%.4f' % mC)


if __name__ == '__main__':
    main()
