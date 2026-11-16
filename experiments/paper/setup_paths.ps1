# Windows 侧一次性初始化：按卷标找到共享盘、建目录树、打印两个系统的路径对照。
# 用法（本目录下）：powershell -ExecutionPolicy Bypass -File setup_paths.ps1
# 本机约定：数据盘卷标“资源盘”（D:），目录树在 D:\REV 下。
param(
    [string]$Label = "资源盘"
)

$RootSub = "REV"
$Dirs = @("00_handoff", "10_results", "20_paper", "30_images", "90_tmp")

$vols = Get-Volume -ErrorAction SilentlyContinue
$vol = $null
foreach ($v in $vols) {
    if ($v.FileSystemLabel -eq $Label -and $v.DriveLetter) { $vol = $v; break }
}

if ($vol -eq $null) {
    Write-Output "未找到卷标为 $Label 的分区。当前可见卷："
    foreach ($v in $vols) {
        if ($v.DriveLetter) {
            $gb = [math]::Round($v.Size / 1GB, 1)
            Write-Output ("  " + $v.DriveLetter + ":  " + $v.FileSystemLabel + "  " + $v.FileSystem + "  " + $gb + " GB")
        }
    }
    Write-Output "请确认数据盘已接好，或修改 rev.env 的 REV_SHARE_LABEL。"
    exit 1
}

$letter = $vol.DriveLetter + ":"
$root = $letter + "\" + $RootSub
$gb = [math]::Round($vol.Size / 1GB, 1)
Write-Output ("卷标 " + $Label + " 位于 " + $letter + "  文件系统 " + $vol.FileSystem + "  容量 " + $gb + " GB")

if (-not (Test-Path -LiteralPath $root)) {
    New-Item -ItemType Directory -Path $root -Force | Out-Null
}
foreach ($d in $Dirs) {
    $p = $root + "\" + $d
    if (-not (Test-Path -LiteralPath $p)) {
        New-Item -ItemType Directory -Path $p -Force | Out-Null
    }
    Write-Output ("  " + $p)
}

$probe = $root + "\90_tmp\.write_test"
Set-Content -LiteralPath $probe -Value "ok" -Encoding utf8
if (Test-Path -LiteralPath $probe) {
    Remove-Item -LiteralPath $probe -Force
    Write-Output "可写校验：通过"
} else {
    Write-Output "可写校验：失败（磁盘只读或受保护）"
    exit 1
}

Write-Output ""
Write-Output "路径对照："
Write-Output ("  Windows  " + $root + "\10_results\rev_<时间>_<tag>\")
Write-Output ("  Linux    /mnt/revshare/REV/10_results/rev_<时间>_<tag>/")

$resolved = $root + "\00_handoff\paths_windows.txt"
$now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$lines = @("REV_SHARE_LABEL=$Label", "REV_SHARE_WIN=$root", "REV_READY_AT=$now")
Set-Content -LiteralPath $resolved -Value $lines -Encoding utf8
Write-Output ("已写入 " + $resolved)
