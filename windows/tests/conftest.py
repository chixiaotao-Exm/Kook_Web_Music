"""pytest 配置 — 为 windows 目录设置 sys.path"""

import os
import sys

# 确保 tests/ 的父目录（windows/）在 sys.path 中
_windows_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _windows_dir not in sys.path:
    sys.path.insert(0, _windows_dir)
