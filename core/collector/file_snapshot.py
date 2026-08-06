"""
毫秒级文件痕迹差分采集模块
- 时间戳来源: CLOCK_BOOTTIME (内核启动时间，不受系统时间调整影响)
- 采集粒度: 文件级 (路径, mtime, size, MD5, inode)
- 差分对比: 识别新增/修改/删除
"""

import os
import hashlib
import json
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class FileEntry:
    """单个文件的痕迹信息"""
    path: str
    mtime: float       # 修改时间（毫秒级）
    size: int
    md5: str
    inode: int
    is_dir: bool = False
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'FileEntry':
        return cls(**data)


class ClockBootTime:
    """CLOCK_BOOTTIME 时间戳封装"""
    
    @staticmethod
    def get() -> float:
        """
        获取 CLOCK_BOOTTIME 毫秒级时间戳
        返回: 从内核启动到现在的毫秒数（float）
        """
        try:
            # 使用 time.monotonic() 获取单调时间（等同于CLOCK_BOOTTIME）
            # 在Linux上，time.monotonic() 基于 CLOCK_MONOTONIC
            # 如果需要精确的 CLOCK_BOOTTIME，使用 ctypes 调用 clock_gettime
            import ctypes
            from ctypes import c_int, c_long, c_uint, POINTER
            
            class timespec(ctypes.Structure):
                _fields_ = [("tv_sec", c_long), ("tv_nsec", c_long)]
            
            CLOCK_BOOTTIME = 7  # 定义常量
            libc = ctypes.CDLL("libc.so.6")
            clock_gettime = libc.clock_gettime
            clock_gettime.argtypes = [c_int, POINTER(timespec)]
            
            ts = timespec()
            ret = clock_gettime(CLOCK_BOOTTIME, ctypes.byref(ts))
            if ret == 0:
                return ts.tv_sec * 1000.0 + ts.tv_nsec / 1_000_000.0
            else:
                # 降级方案：使用 time.monotonic()
                return time.monotonic() * 1000.0
        except Exception:
            # 降级方案
            return time.monotonic() * 1000.0
    
    @staticmethod
    def get_human_readable() -> str:
        """返回人类可读的时间字符串（用于日志）"""
        ms = ClockBootTime.get()
        return f"{ms:.3f}ms (boot time)"


class FileSnapshotCollector:
    """文件快照差分采集器"""
    
    def __init__(self, base_path: str = "/sdcard", follow_symlinks: bool = False):
        """
        Args:
            base_path: 要监控的根目录（默认 /sdcard）
            follow_symlinks: 是否跟踪软链接（默认 False）
        """
        self.base_path = base_path
        self.follow_symlinks = follow_symlinks
    
    def create_snapshot(self, target_path: str = None) -> Dict[str, FileEntry]:
        """
        创建目标路径的完整文件快照
        返回: {相对路径: FileEntry}
        """
        if target_path is None:
            target_path = self.base_path
        
        if not os.path.exists(target_path):
            return {}
        
        snapshot = {}
        for root, dirs, files in os.walk(target_path):
            for name in files + dirs:
                full_path = os.path.join(root, name)
                rel_path = os.path.relpath(full_path, target_path)
                
                try:
                    if self.follow_symlinks:
                        stat = os.stat(full_path)
                    else:
                        stat = os.lstat(full_path)
                    
                    is_dir = os.path.isdir(full_path)
                    
                    # 计算MD5（仅对文件，目录跳过）
                    md5_hash = ""
                    if not is_dir:
                        md5_hash = self._calculate_md5(full_path)
                    
                    entry = FileEntry(
                        path=rel_path,
                        mtime=stat.st_mtime * 1000.0,  # 转为毫秒
                        size=stat.st_size if not is_dir else 0,
                        md5=md5_hash,
                        inode=stat.st_ino,
                        is_dir=is_dir
                    )
                    snapshot[rel_path] = entry
                except (OSError, PermissionError):
                    # 跳过无法访问的文件
                    continue
        
        return snapshot
    
    def _calculate_md5(self, file_path: str, chunk_size: int = 8192) -> str:
        """计算文件的MD5哈希值"""
        try:
            md5 = hashlib.md5()
            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    md5.update(chunk)
            return md5.hexdigest()
        except (OSError, PermissionError):
            return ""
    
    def diff_snapshots(self, before: Dict[str, FileEntry], after: Dict[str, FileEntry]) -> dict:
        """
        对比两个快照，返回变更摘要
        返回: {
            'created': [FileEntry, ...],    # 新增的文件
            'modified': [FileEntry, ...],   # 修改的文件
            'deleted': [FileEntry, ...],    # 删除的文件
            'unchanged': [FileEntry, ...]   # 未变更的文件
        }
        """
        created = []
        modified = []
        deleted = []
        unchanged = []
        
        before_paths = set(before.keys())
        after_paths = set(after.keys())
        
        # 新增：在after中存在，在before中不存在
        for path in after_paths - before_paths:
            created.append(after[path])
        
        # 删除：在before中存在，在after中不存在
        for path in before_paths - after_paths:
            deleted.append(before[path])
        
        # 可能修改：两边都存在
        for path in before_paths & after_paths:
            b_entry = before[path]
            a_entry = after[path]
            
            # 判断是否修改：mtime变化 或 size变化 或 MD5变化
            is_modified = (
                b_entry.mtime != a_entry.mtime or
                b_entry.size != a_entry.size or
                b_entry.md5 != a_entry.md5
            )
            
            if is_modified:
                modified.append({
                    'before': b_entry,
                    'after': a_entry
                })
            else:
                unchanged.append(a_entry)
        
        return {
            'created': created,
            'modified': modified,
            'deleted': deleted,
            'unchanged': unchanged
        }
    
    def capture_atomic(self, target_path: str = None) -> Tuple[Dict, float]:
        """
        捕获当前快照，并返回快照数据和时间戳
        用于原子操作的痕迹采集
        """
        if target_path is None:
            target_path = self.base_path
        
        timestamp = ClockBootTime.get()
        snapshot = self.create_snapshot(target_path)
        return snapshot, timestamp
    
    def diff_atomic(self, before_snapshot: Dict, before_ts: float, target_path: str = None) -> dict:
        """
        执行原子操作后的差分对比
        返回: {
            'timestamp_start': float,
            'timestamp_end': float,
            'duration_ms': float,
            'changes': diff_results,
            'target_path': str
        }
        """
        if target_path is None:
            target_path = self.base_path
        
        after_snapshot, after_ts = self.capture_atomic(target_path)
        diff_result = self.diff_snapshots(before_snapshot, after_snapshot)
        
        return {
            'timestamp_start_ms': before_ts,
            'timestamp_end_ms': after_ts,
            'duration_ms': after_ts - before_ts,
            'changes': diff_result,
            'target_path': target_path,
            'before_count': len(before_snapshot),
            'after_count': len(after_snapshot)
        }
    
    def save_snapshot(self, snapshot: Dict[str, FileEntry], filepath: str):
        """保存快照到JSON文件"""
        data = {path: entry.to_dict() for path, entry in snapshot.items()}
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def load_snapshot(self, filepath: str) -> Dict[str, FileEntry]:
        """从JSON文件加载快照"""
        with open(filepath, 'r') as f:
            data = json.load(f)
        return {path: FileEntry.from_dict(entry) for path, entry in data.items()}


# 全局单例
_default_collector = None


def get_collector(base_path: str = "/sdcard") -> FileSnapshotCollector:
    global _default_collector
    if _default_collector is None:
        _default_collector = FileSnapshotCollector(base_path=base_path)
    return _default_collector


# 便捷函数：获取当前CLOCK_BOOTTIME时间戳
def get_boot_time_ms() -> float:
    return ClockBootTime.get()
