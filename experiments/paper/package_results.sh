#!/usr/bin/env bash
# Linux 侧收尾打包：把指定范围的结果打成包，写到共享盘供 Windows 读取。
# 用法：bash experiments/paper/package_results.sh --tag api30r2
#        bash experiments/paper/package_results.sh --tag api30r2 --only 'output/paper/rerun_api30/*.json'
# 产物：$BASE/10_results/rev_YYYYmmdd_HHMM_<tag>/{results.tar.gz, manifest.json, SHA256SUMS, files.txt}
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$HERE/rev.env" ] && . "$HERE/rev.env"
REPO="${REPO:-${REV_REPO:-$(cd "$HERE/../.." && pwd)}}"
SHARE="${SHARE:-${REV_SHARE_LINUX:-/mnt/revshare}}"
TAG="session"
ONLY=""

while [ $# -gt 0 ]; do
  case "$1" in
    --tag) TAG="$2"; shift 2 ;;
    --repo) REPO="$2"; shift 2 ;;
    --share) SHARE="$2"; shift 2 ;;
    --only) ONLY="$2"; shift 2 ;;
    *) echo "未知参数 $1"; exit 2 ;;
  esac
done

STAMP=$(date '+%Y%m%d_%H%M')
BASE="$SHARE/${REV_ROOT_SUBDIR:-REV}"
DEST="$BASE/${REV_DIR_RESULTS:-10_results}/rev_${STAMP}_${TAG}"
mkdir -p "$DEST"

RES="$REPO/output/paper"
[ -d "$RES" ] || { echo "没有实验结果目录：$RES"; exit 1; }

CODE_HASH=$(find "$REPO" -type f \( -name '*.py' -o -name '*.yaml' -o -name '*.sh' \) -print0 \
  | sort -z | xargs -0 sha256sum | sha256sum | awk '{print $1}')

# 先确定打包范围，避免每个 fix 包都变成整份快照
python3 - "$REPO" "$RES" "$DEST" "$TAG" "$CODE_HASH" "$ONLY" <<'PY'
import glob, json, os, subprocess, sys
repo, res, dest, tag, code_hash, only = sys.argv[1:7]

def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception:
        return ""

if only:
    files = []
    for pat in only.split(","):
        pat = pat.strip()
        if pat:
            files += glob.glob(os.path.join(repo, pat))
else:
    files = [p for p in glob.glob(os.path.join(res, "**", "*"), recursive=True) if os.path.isfile(p)]
files = sorted(set(files))
rels = [os.path.relpath(p, repo) for p in files]
open(os.path.join(dest, "files.txt"), "w", encoding="utf-8").write("\n".join(rels) + "\n")

runs, probes, jitters = {}, 0, 0
for p in files:
    name = os.path.basename(p)
    if "/runs/" in p and name.endswith(".json") and "warmup" not in name:
        try:
            j = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        runs.setdefault(str(j.get("api")), []).append(name)
    if name.startswith("probe_api"):
        probes += 1
    if name.startswith("jitter_api"):
        jitters += 1

manifest = {
    "tag": tag,
    "created": sh("date '+%F %T %Z'"),
    "host": sh("hostname"),
    "kernel": sh("uname -sr"),
    "code_sha256": code_hash,
    "adb": sh("adb version | head -1"),
    "avds": sh("emulator -list-avds | grep rev_api | tr '\\n' ','"),
    "python": sh("python3 -V"),
    "scope": ("only:" + only) if only else "full:output/paper",
    "file_count": len(rels),
    "runs_per_api": {k: len(v) for k, v in sorted(runs.items())},
    "probe_files": probes,
    "jitter_files": jitters,
    "outputs": rels,
}
open(os.path.join(dest, "manifest.json"), "w", encoding="utf-8").write(
    json.dumps(manifest, ensure_ascii=False, indent=2))
print("scope=%s 文件=%d 运行=%d 探针=%d 抖动=%d" % (
    manifest["scope"], len(rels), sum(manifest["runs_per_api"].values()), probes, jitters))
PY

tar czf "$DEST/results.tar.gz" -C "$REPO" -T "$DEST/files.txt"
( cd "$DEST" && sha256sum results.tar.gz manifest.json > SHA256SUMS )

SIZE=$(du -h "$DEST/results.tar.gz" | awk '{print $1}')
echo
echo "已打包：$DEST"
echo "  results.tar.gz  $SIZE"
echo "  manifest.json   代码指纹、打包范围与计数"
echo "  files.txt       本包实际包含的文件清单"
echo "  SHA256SUMS      回到 Windows 后用 verify_results.py 校验"
