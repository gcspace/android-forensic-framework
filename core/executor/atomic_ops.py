"""
原子操作执行器
- 四大类操作: UI交互 / 文件操作 / 应用进程 / 网络传输
- API分支适配: global_file (API28) / legacy_mode (API29) / saf_only (API31+)
- 每个原子操作包含: execute() + collect_evidence()
"""

import os
import time
import json
import logging
import subprocess
import tempfile
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field

from core.executor.adb_manager import get_pool
from core.collector.file_snapshot import get_collector, get_boot_time_ms

logger = logging.getLogger(__name__)


@dataclass
class AtomicResult:
    """原子操作执行结果"""
    success: bool
    stdout: str
    stderr: str
    timestamp_start: float
    timestamp_end: float
    duration_ms: float
    evidence: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class AtomicOperation(ABC):
    """原子操作基类"""
    
    def __init__(self, api_level: int, serial: str = None, **kwargs):
        self.api_level = api_level
        self.serial = serial
        self.params = kwargs
        self.pool = get_pool()
        self.collector = get_collector()
        self._api_branch = self._get_api_branch(api_level)
    
    def _get_api_branch(self, api_level: int) -> str:
        if api_level <= 28:
            return "global_file"
        elif api_level == 29:
            return "legacy_mode"
        else:
            return "saf_only"
    
    def _get_media_path(self, subpath: str = "") -> str:
        """根据 API 级别选择可用的文件路径"""
        if self.api_level <= 28:
            return f"/sdcard/{subpath}"
        else:
            # API 29+ 使用 /data/local/tmp/（分区存储限制）
            return f"/data/local/tmp/{subpath}"
    def _execute_adb(self, command: str, timeout: int = 30) -> Tuple[str, str, int]:
        return self.pool.execute_with_retry(command, self.serial)
    
    def _execute_adb_raw(self, command: str, timeout: int = 30) -> Tuple[str, str, int]:
        """执行原始 ADB 命令（不含 shell 前缀）"""
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
            return result.stdout.strip(), result.stderr.strip(), result.returncode
        except subprocess.TimeoutExpired:
            return "", f"Command timeout after {timeout}s", -1
    
    def _get_timestamp(self) -> float:
        return get_boot_time_ms()
    
    @abstractmethod
    def execute(self) -> AtomicResult:
        pass
    
    @abstractmethod
    def collect_evidence(self, result: AtomicResult) -> Dict[str, Any]:
        pass


class UIClick(AtomicOperation):
    def execute(self) -> AtomicResult:
        x = self.params.get('x')
        y = self.params.get('y')
        duration = self.params.get('duration', 50)
        if x is None or y is None:
            return AtomicResult(
                success=False, stdout="", stderr="Missing coordinates",
                timestamp_start=0, timestamp_end=0, duration_ms=0, error="x and y required")
        start_ts = self._get_timestamp()
        cmd = f"input swipe {x} {y} {x} {y} {duration}"
        stdout, stderr, rc = self._execute_adb(cmd)
        end_ts = self._get_timestamp()
        return AtomicResult(
            success=(rc == 0), stdout=stdout, stderr=stderr,
            timestamp_start=start_ts, timestamp_end=end_ts,
            duration_ms=end_ts - start_ts,
            evidence={'x': x, 'y': y, 'duration': duration})
    
    def collect_evidence(self, result: AtomicResult) -> Dict[str, Any]:
        return {'type': 'ui_click', 'coordinates': result.evidence, 'timestamp': result.timestamp_start}


class UISwipe(AtomicOperation):
    def execute(self) -> AtomicResult:
        x1 = self.params.get('x1'); y1 = self.params.get('y1')
        x2 = self.params.get('x2'); y2 = self.params.get('y2')
        duration = self.params.get('duration', 300)
        if None in [x1, y1, x2, y2]:
            return AtomicResult(
                success=False, stdout="", stderr="Missing coordinates",
                timestamp_start=0, timestamp_end=0, duration_ms=0, error="x1,y1,x2,y2 required")
        start_ts = self._get_timestamp()
        cmd = f"input swipe {x1} {y1} {x2} {y2} {duration}"
        stdout, stderr, rc = self._execute_adb(cmd)
        end_ts = self._get_timestamp()
        return AtomicResult(
            success=(rc == 0), stdout=stdout, stderr=stderr,
            timestamp_start=start_ts, timestamp_end=end_ts,
            duration_ms=end_ts - start_ts,
            evidence={'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2, 'duration': duration})
    
    def collect_evidence(self, result: AtomicResult) -> Dict[str, Any]:
        return {'type': 'ui_swipe', 'coordinates': result.evidence, 'timestamp': result.timestamp_start}


class UIInput(AtomicOperation):
    def execute(self) -> AtomicResult:
        text = self.params.get('text', '')
        if not text:
            return AtomicResult(
                success=False, stdout="", stderr="Empty text",
                timestamp_start=0, timestamp_end=0, duration_ms=0, error="text required")
        escaped = text.replace(' ', '%s').replace('&', '\\&')
        start_ts = self._get_timestamp()
        cmd = f"input text {escaped}"
        stdout, stderr, rc = self._execute_adb(cmd)
        end_ts = self._get_timestamp()
        return AtomicResult(
            success=(rc == 0), stdout=stdout, stderr=stderr,
            timestamp_start=start_ts, timestamp_end=end_ts,
            duration_ms=end_ts - start_ts,
            evidence={'text': text, 'length': len(text)})
    
    def collect_evidence(self, result: AtomicResult) -> Dict[str, Any]:
        return {'type': 'ui_input', 'text_length': result.evidence.get('length', 0), 'timestamp': result.timestamp_start}


class FileCreate(AtomicOperation):
    def execute(self) -> AtomicResult:
        path = self.params.get('path')
        content = self.params.get('content', '')
        is_media = self.params.get('is_media', False)
        if not path:
            return AtomicResult(
                success=False, stdout="", stderr="Missing path",
                timestamp_start=0, timestamp_end=0, duration_ms=0, error="path required")
        full_path = self._get_media_path(path) if is_media else f"/sdcard/{path}"
        start_ts = self._get_timestamp()
        if content:
            # 使用 adb push 创建文件（避免 shell 重定向权限问题）
            try:
                temp_fd, temp_path = tempfile.mkstemp(text=True)
                with os.fdopen(temp_fd, 'w') as tf:
                    tf.write(content)
                if self.serial:
                    cmd = f"adb -s {self.serial} push {temp_path} {full_path}"
                else:
                    cmd = f"adb push {temp_path} {full_path}"
                stdout, stderr, rc = self._execute_adb_raw(cmd)
                os.unlink(temp_path)
            except Exception as e:
                return AtomicResult(
                    success=False, stdout="", stderr=str(e),
                    timestamp_start=start_ts, timestamp_end=start_ts, duration_ms=0, error=str(e))
        else:
            stdout, stderr, rc = self._execute_adb(f"touch {full_path}")
        end_ts = self._get_timestamp()
        return AtomicResult(
            success=(rc == 0), stdout=stdout, stderr=stderr,
            timestamp_start=start_ts, timestamp_end=end_ts,
            duration_ms=end_ts - start_ts,
            evidence={'path': full_path, 'content_length': len(content)})
    
    def collect_evidence(self, result: AtomicResult) -> Dict[str, Any]:
        return {'type': 'file_create', 'path': result.evidence.get('path'), 'timestamp': result.timestamp_start}


class FileCopy(AtomicOperation):
    def execute(self) -> AtomicResult:
        src = self.params.get('src')
        dst = self.params.get('dst')
        is_media = self.params.get('is_media', False)
        if not src or not dst:
            return AtomicResult(
                success=False, stdout="", stderr="Missing src or dst",
                timestamp_start=0, timestamp_end=0, duration_ms=0, error="src and dst required")
        src_path = self._get_media_path(src) if is_media else f"/sdcard/{src}"
        dst_path = self._get_media_path(dst) if is_media else f"/sdcard/{dst}"
        start_ts = self._get_timestamp()
        # 确保目标目录存在
        dst_dir = '/'.join(dst_path.split('/')[:-1])
        if dst_dir:
            self._execute_adb(f"mkdir -p {dst_dir}")
        cmd = f"cp {src_path} {dst_path}"
        stdout, stderr, rc = self._execute_adb(cmd)
        end_ts = self._get_timestamp()
        return AtomicResult(
            success=(rc == 0), stdout=stdout, stderr=stderr,
            timestamp_start=start_ts, timestamp_end=end_ts,
            duration_ms=end_ts - start_ts,
            evidence={'src': src_path, 'dst': dst_path})
    
    def collect_evidence(self, result: AtomicResult) -> Dict[str, Any]:
        return {'type': 'file_copy', 'src': result.evidence.get('src'), 'dst': result.evidence.get('dst'), 'timestamp': result.timestamp_start}


class FileDelete(AtomicOperation):
    def execute(self) -> AtomicResult:
        path = self.params.get('path')
        is_media = self.params.get('is_media', False)
        recursive = self.params.get('recursive', False)
        if not path:
            return AtomicResult(
                success=False, stdout="", stderr="Missing path",
                timestamp_start=0, timestamp_end=0, duration_ms=0, error="path required")
        full_path = self._get_media_path(path) if is_media else f"/sdcard/{path}"
        start_ts = self._get_timestamp()
        cmd = f"rm {'-rf ' if recursive else ''}{full_path}"
        stdout, stderr, rc = self._execute_adb(cmd)
        end_ts = self._get_timestamp()
        return AtomicResult(
            success=(rc == 0), stdout=stdout, stderr=stderr,
            timestamp_start=start_ts, timestamp_end=end_ts,
            duration_ms=end_ts - start_ts,
            evidence={'path': full_path, 'recursive': recursive})
    
    def collect_evidence(self, result: AtomicResult) -> Dict[str, Any]:
        return {'type': 'file_delete', 'path': result.evidence.get('path'), 'timestamp': result.timestamp_start}


class AppInstall(AtomicOperation):
    def execute(self) -> AtomicResult:
        apk_path = self.params.get('apk_path')
        if not apk_path:
            return AtomicResult(
                success=False, stdout="", stderr="Missing apk_path",
                timestamp_start=0, timestamp_end=0, duration_ms=0, error="apk_path required")
        start_ts = self._get_timestamp()
        cmd = f"pm install -r {apk_path}"
        stdout, stderr, rc = self._execute_adb(cmd, timeout=120)
        end_ts = self._get_timestamp()
        return AtomicResult(
            success=(rc == 0 and "Success" in stdout), stdout=stdout, stderr=stderr,
            timestamp_start=start_ts, timestamp_end=end_ts,
            duration_ms=end_ts - start_ts,
            evidence={'apk_path': apk_path})
    
    def collect_evidence(self, result: AtomicResult) -> Dict[str, Any]:
        return {'type': 'app_install', 'apk': result.evidence.get('apk_path'), 'timestamp': result.timestamp_start}


class AppStart(AtomicOperation):
    def execute(self) -> AtomicResult:
        package = self.params.get('package')
        activity = self.params.get('activity', '')
        if not package:
            return AtomicResult(
                success=False, stdout="", stderr="Missing package",
                timestamp_start=0, timestamp_end=0, duration_ms=0, error="package required")
        start_ts = self._get_timestamp()
        if activity:
            cmd = f"am start -n {package}/{activity}"
        else:
            cmd = f"monkey -p {package} 1"
        stdout, stderr, rc = self._execute_adb(cmd)
        end_ts = self._get_timestamp()
        return AtomicResult(
            success=(rc == 0), stdout=stdout, stderr=stderr,
            timestamp_start=start_ts, timestamp_end=end_ts,
            duration_ms=end_ts - start_ts,
            evidence={'package': package, 'activity': activity})
    
    def collect_evidence(self, result: AtomicResult) -> Dict[str, Any]:
        return {'type': 'app_start', 'package': result.evidence.get('package'), 'timestamp': result.timestamp_start}


class AppStop(AtomicOperation):
    def execute(self) -> AtomicResult:
        package = self.params.get('package')
        if not package:
            return AtomicResult(
                success=False, stdout="", stderr="Missing package",
                timestamp_start=0, timestamp_end=0, duration_ms=0, error="package required")
        start_ts = self._get_timestamp()
        cmd = f"am force-stop {package}"
        stdout, stderr, rc = self._execute_adb(cmd)
        end_ts = self._get_timestamp()
        return AtomicResult(
            success=(rc == 0), stdout=stdout, stderr=stderr,
            timestamp_start=start_ts, timestamp_end=end_ts,
            duration_ms=end_ts - start_ts,
            evidence={'package': package})
    
    def collect_evidence(self, result: AtomicResult) -> Dict[str, Any]:
        return {'type': 'app_stop', 'package': result.evidence.get('package'), 'timestamp': result.timestamp_start}


class NetDownload(AtomicOperation):
    def execute(self) -> AtomicResult:
        url = self.params.get('url')
        dest = self.params.get('dest', '/sdcard/Download/')
        if not url:
            return AtomicResult(
                success=False, stdout="", stderr="Missing url",
                timestamp_start=0, timestamp_end=0, duration_ms=0, error="url required")
        start_ts = self._get_timestamp()
        cmd = f"wget -P {dest} {url}"
        stdout, stderr, rc = self._execute_adb(cmd, timeout=60)
        end_ts = self._get_timestamp()
        return AtomicResult(
            success=(rc == 0), stdout=stdout, stderr=stderr,
            timestamp_start=start_ts, timestamp_end=end_ts,
            duration_ms=end_ts - start_ts,
            evidence={'url': url, 'dest': dest})
    
    def collect_evidence(self, result: AtomicResult) -> Dict[str, Any]:
        return {'type': 'net_download', 'url': result.evidence.get('url'), 'timestamp': result.timestamp_start}


# 原子操作工厂
class AtomicFactory:
    _registry = {
        'UI_CLICK': UIClick,
        'UI_SWIPE': UISwipe,
        'UI_INPUT': UIInput,
        'FILE_CREATE': FileCreate,
        'FILE_COPY': FileCopy,
        'FILE_DELETE': FileDelete,
        'APP_INSTALL': AppInstall,
        'APP_START': AppStart,
        'APP_STOP': AppStop,
        'NET_DOWNLOAD': NetDownload,
    }
    
    @classmethod
    def create(cls, op_type: str, api_level: int, serial: str = None, **kwargs) -> AtomicOperation:
        op_class = cls._registry.get(op_type)
        if op_class is None:
            raise ValueError(f"Unknown operation type: {op_type}")
        return op_class(api_level=api_level, serial=serial, **kwargs)
    
    @classmethod
    def register(cls, op_type: str, op_class):
        cls._registry[op_type] = op_class
