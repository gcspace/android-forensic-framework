#!/usr/bin/env bash
# Linux 侧一次性初始化：按卷标找到共享盘、挂载、建目录树、验证可写。
# 用法：sudo bash experiments/paper/setup_share.sh
# 本机约定：卷标“资源盘”（Windows D:），挂到 /mnt/revshare，目录树在 REV 子目录下。
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$HERE/rev.env" ] && . "$HERE/rev.env"
LABEL="${REV_SHARE_LABEL:-资源盘}"
MOUNT="${REV_SHARE_LINUX:-/mnt/revshare}"
BASE="$MOUNT/${REV_ROOT_SUBDIR:-REV}"

echo "== 1. 查找卷标 $LABEL"
DEV=$(lsblk -o LABEL,PATH,FSTYPE -P 2>/dev/null | awk -v l="$LABEL" '
  { lab=""; p=""; fs=""
    for (i=1;i<=NF;i++) { split($i,a,"="); gsub(/"/,"",a[2]);
      if (a[1]=="LABEL") lab=a[2]; if (a[1]=="PATH") p=a[2]; if (a[1]=="FSTYPE") fs=a[2] }
    if (lab==l) { print p" "fs; exit } }')
if [ -z "$DEV" ]; then
  echo "  未找到卷标为 $LABEL 的分区。当前清单："
  lsblk -o NAME,LABEL,FSTYPE,SIZE,MOUNTPOINT
  echo "  确认 Windows 侧数据盘已正常关机（非休眠），或改 rev.env 的 REV_SHARE_LABEL"
  exit 1
fi
echo "  设备：$DEV"

echo "== 2. 挂载到 $MOUNT"
mkdir -p "$MOUNT"
if mountpoint -q "$MOUNT"; then
  echo "  已挂载，跳过"
else
  FSTYPE=$(echo "$DEV" | awk '{print $2}')
  sudo mount -t "${FSTYPE:-ntfs3}" -L "$LABEL" "$MOUNT" || {
    echo "  挂载失败：多为 Windows 未正常关机或开启了快速启动"
    echo "  只读兜底：sudo mount -t ntfs3 -o ro -L $LABEL $MOUNT"
    exit 1
  }
fi

echo "== 3. 建目录树 $BASE"
for d in "${REV_DIR_HANDOFF:-00_handoff}" "${REV_DIR_RESULTS:-10_results}" \
         "${REV_DIR_PAPER:-20_paper}" "${REV_DIR_IMAGES:-30_images}" "${REV_DIR_TMP:-90_tmp}"; do
  mkdir -p "$BASE/$d" && echo "  $BASE/$d"
done

echo "== 4. 可写校验"
if touch "$BASE/${REV_DIR_TMP:-90_tmp}/.write_test" 2>/dev/null; then
  rm -f "$BASE/${REV_DIR_TMP:-90_tmp}/.write_test"; echo "  可写"
else
  echo "  不可写：NTFS 被 Windows 锁定，或挂载为只读"; exit 1
fi

echo "== 5. 记录解析结果"
{
  echo "REV_SHARE_LABEL=$LABEL"
  echo "REV_SHARE_LINUX=$MOUNT"
  echo "REV_BASE=$BASE"
  echo "REV_DEVICE=$(echo "$DEV" | awk '{print $1}')"
  echo "REV_READY_AT=$(date '+%F %T')"
} > "$BASE/${REV_DIR_HANDOFF:-00_handoff}/paths.resolved"
cat "$BASE/${REV_DIR_HANDOFF:-00_handoff}/paths.resolved"

echo
echo "共享盘就绪：$BASE"
echo "结果目录：$BASE/${REV_DIR_RESULTS:-10_results}/rev_<时间>_<tag>"
