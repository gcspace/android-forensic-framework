#!/usr/bin/env bash
# Linux 侧开机自检：挂盘、代码、依赖、adb、AVD、空间。
# 用法：bash experiments/paper/preflight.sh
# 任一项失败都会以非零退出，避免"以为跑起来了其实没跑"。
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$HERE/rev.env" ] && . "$HERE/rev.env"
SHARE="${SHARE:-${REV_SHARE_LINUX:-/mnt/revshare}}"
REPO="${REPO:-${REV_REPO:-$(cd "$HERE/../.." && pwd)}}"
FAIL=0

ok()   { echo "  [OK]   $1"; }
bad()  { echo "  [FAIL] $1"; FAIL=1; }

echo "== 1. 系统"
uname -sr
echo "  用户：$(whoami)   时间：$(date '+%F %T %Z')"

echo "== 2. 共享盘"
BASE="$SHARE/${REV_ROOT_SUBDIR:-REV}"
if mountpoint -q "$SHARE"; then
  ok "$SHARE 已挂载"
  if touch "$BASE/${REV_DIR_TMP:-90_tmp}/.write_test" 2>/dev/null; then ok "可写"; rm -f "$BASE/${REV_DIR_TMP:-90_tmp}/.write_test"; else bad "不可写（NTFS 可能被 Windows 快速启动锁定）"; fi
  [ -d "$BASE/${REV_DIR_RESULTS:-10_results}" ] && ok "目录树 $BASE 已就绪" || bad "目录树缺失，先跑 setup_share.sh"
else
  bad "$SHARE 未挂载，先执行：sudo bash experiments/paper/setup_share.sh"
fi
echo "  剩余空间：$(df -h "$SHARE" 2>/dev/null | awk 'NR==2{print $4}')"

echo "== 3. 代码目录"
if [ -d "$REPO" ]; then
  ok "$REPO"
  echo "  文件数：$(find "$REPO" -type f | wc -l)"
  if [ -d "$REPO/.git" ]; then echo "  git: $(git -C "$REPO" rev-parse --short HEAD 2>/dev/null)"; else echo "  git: 无（zip 快照）"; fi
else
  bad "$REPO 不存在"
fi

echo "== 4. Python 依赖"
python3 -V 2>/dev/null || bad "缺少 python3"
python3 - <<'PY' 2>/dev/null
import networkx, yaml, docx
print("  [OK]   networkx %s / pyyaml %s" % (networkx.__version__, yaml.__version__))
PY
[ $? -ne 0 ] && bad "缺少 networkx 或 pyyaml：python3 -m pip install networkx pyyaml"

echo "== 5. adb 与设备"
command -v adb >/dev/null && ok "adb $(adb version | head -1 | awk '{print $NF}')" || bad "adb 不在 PATH"
adb devices | sed -n '2,$p' | grep -q "device$" && ok "在线设备：$(adb devices | sed -n '2,$p' | awk '$2=="device"{print $1}' | tr '\n' ' ')" || bad "无在线设备"

echo "== 6. AVD"
if command -v emulator >/dev/null; then
  list=$(emulator -list-avds 2>/dev/null | grep -c 'rev_api' || true)
  [ "${list:-0}" -ge 7 ] && ok "rev_api* 共 $list 套" || bad "rev_api* 只有 ${list:-0} 套，先跑 make_avds.sh"
else
  bad "emulator 不在 PATH"
fi

echo "== 7. 磁盘余量（~ 与 /tmp）"
df -h "$HOME" /tmp | awk 'NR>1{print "  "$6" 剩余 "$4}'

echo
[ "$FAIL" -eq 0 ] && echo "自检通过，可以开始实验" || echo "自检未通过，先按上面提示修复"
exit "$FAIL"
