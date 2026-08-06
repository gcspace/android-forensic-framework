"""
ADB会话池管理器
- 最大并发会话数: 8 (与论文W=8一致)
- 自动重试: 最多2次
- 线程安全: 使用queue管理空闲会话
"""

import subprocess
import queue
import threading
import time
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class ADBSession:
    """单个ADB会话封装"""
    
    def __init__(self, serial: str = None):
        self.serial = serial
        self._is_available = True
    
    def execute(self, command: str, timeout: int = 30) -> Tuple[str, str, int]:
        if self.serial:
            cmd = f"adb -s {self.serial} shell {command}"
        else:
            cmd = f"adb shell {command}"
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            return result.stdout.strip(), result.stderr.strip(), result.returncode
        except subprocess.TimeoutExpired:
            return "", f"Command timeout after {timeout}s", -1
    
    def is_available(self) -> bool:
        return self._is_available
    
    def mark_unavailable(self):
        self._is_available = False


class ADBSessionPool:
    def __init__(self, max_sessions: int = 8, max_retries: int = 2, retry_delay: float = 1.0):
        self.max_sessions = max_sessions
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._devices: List[str] = []
        self._refresh_devices()
        self._pool: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._active_sessions = 0
        self._init_pool()
    
    def _refresh_devices(self):
        try:
            result = subprocess.run("adb devices", shell=True, capture_output=True, text=True, timeout=10)
            lines = result.stdout.strip().split('\n')[1:]
            self._devices = []
            for line in lines:
                if line.strip() and 'device' in line:
                    serial = line.split()[0]
                    if 'offline' not in line:
                        self._devices.append(serial)
            logger.info(f"Detected devices: {self._devices}")
        except Exception as e:
            logger.error(f"Failed to refresh devices: {e}")
            self._devices = []
    
    def _init_pool(self):
        with self._lock:
            for _ in range(self.max_sessions):
                self._pool.put(ADBSession())
            self._active_sessions = 0
            logger.info(f"ADB session pool initialized with {self.max_sessions} sessions")
    
    def acquire(self, timeout: float = 30.0) -> Optional[ADBSession]:
        try:
            session = self._pool.get(timeout=timeout)
            with self._lock:
                self._active_sessions += 1
            return session
        except queue.Empty:
            logger.error(f"Failed to acquire ADB session after {timeout}s")
            return None
    
    def release(self, session: ADBSession):
        if session:
            with self._lock:
                self._active_sessions -= 1
            self._pool.put(session)
    
    def execute_with_retry(self, command: str, serial: str = None) -> Tuple[str, str, int]:
        session = None
        try:
            session = self.acquire()
            if session is None:
                return "", "No ADB session available", -1
            if serial:
                session.serial = serial
            else:
                session.serial = self._devices[0] if self._devices else None
            for attempt in range(self.max_retries + 1):
                stdout, stderr, rc = session.execute(command)
                if rc == 0:
                    return stdout, stderr, rc
                logger.warning(f"Command failed (attempt {attempt+1}/{self.max_retries+1}): {stderr}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
                    self._refresh_devices()
            return stdout, stderr, -1
        finally:
            if session:
                self.release(session)
    
    def get_device_list(self) -> List[str]:
        self._refresh_devices()
        return self._devices
    
    def get_active_count(self) -> int:
        with self._lock:
            return self._active_sessions
    
    def get_available_count(self) -> int:
        return self._pool.qsize()
    
    def close_all(self):
        with self._lock:
            while not self._pool.empty():
                try:
                    self._pool.get_nowait()
                except queue.Empty:
                    break
            self._active_sessions = 0
            for _ in range(self.max_sessions):
                self._pool.put(ADBSession())
            logger.info("ADB session pool reset")


_default_pool = None


def get_pool(max_sessions: int = 8) -> ADBSessionPool:
    global _default_pool
    if _default_pool is None:
        _default_pool = ADBSessionPool(max_sessions=max_sessions)
    return _default_pool

    def push_file(self, local_path: str, remote_path: str, timeout: int = 30) -> Tuple[str, str, int]:
        """使用 adb push 上传文件"""
        if self.serial:
            cmd = f"adb -s {self.serial} push {local_path} {remote_path}"
        else:
            cmd = f"adb push {local_path} {remote_path}"
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            return result.stdout.strip(), result.stderr.strip(), result.returncode
        except subprocess.TimeoutExpired:
            return "", f"adb push timeout after {timeout}s", -1
