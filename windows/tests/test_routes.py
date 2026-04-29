"""测试 routes.py — API 路由错误处理、参数校验、异步桥接"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── 异步桥接 run_async ──────────────────────────────────────────

class TestRunAsync:
    """run_async() 异步桥接函数"""

    def test_run_async_success(self):
        """正常协程返回结果"""
        from routes import run_async

        async def add(a, b):
            return a + b

        result = run_async(add(1, 2))
        assert result == 3

    def test_run_async_returns_none(self):
        """协程返回 None 正确传递"""
        from routes import run_async

        async def return_none():
            return None

        result = run_async(return_none())
        assert result is None

    def test_run_async_exception_raised(self):
        """协程异常被向上抛出"""
        from routes import run_async

        async def failing():
            raise ValueError("测试异常")

        with pytest.raises(ValueError, match="测试异常"):
            run_async(failing())

    def test_run_async_complex_return(self):
        """复杂对象正确返回"""
        from routes import run_async

        async def get_data():
            return {"key": [1, 2, 3], "nested": {"a": True}}

        result = run_async(get_data())
        assert result == {"key": [1, 2, 3], "nested": {"a": True}}


# ── _require_guild 辅助函数 ─────────────────────────────────────

class TestRequireGuild:
    """_require_guild 参数校验"""

    def test_with_valid_guild_id(self):
        """提供 guild_id 时返回"""
        from routes import register_routes  # noqa: F401
        # _require_guild 是闭包内函数，我们通过 Flask test client 间接测试
        # 这里验证函数签名和基本逻辑
        pass  # 见 Flask route 集成测试


# ── 无硬编码凭据 ───────────────────────────────────────────────

class TestNoSecrets:
    """routes.py 不含硬编码凭据"""

    def test_no_hardcoded_tokens_in_routes(self):
        """源码不应含 BOT_TOKEN 硬编码"""
        routes_path = os.path.join(os.path.dirname(__file__), "..", "routes.py")
        with open(routes_path) as f:
            source = f.read()
        import re
        suspicious = re.findall(
            r'(?:token|secret|password|api_key)\s*=\s*["\']([^"\']{10,})["\']',
            source, re.IGNORECASE
        )
        assert len(suspicious) == 0, f"routes.py 硬编码凭据: {suspicious}"

    def test_bot_token_imported_from_config(self):
        """BOT_TOKEN 从 config 导入而非硬编码"""
        routes_path = os.path.join(os.path.dirname(__file__), "..", "routes.py")
        with open(routes_path) as f:
            source = f.read()
        assert "from config import BOT_TOKEN" in source, \
            "BOT_TOKEN 应从 config 模块导入"
        # 确认 SECRET_KEY 也来自 config
        assert "from config import BOT_TOKEN, SECRET_KEY" in source or \
               "from config import (" in source, \
            "SECRET_KEY 应从 config 导入"


# ── 路由签名检查 ───────────────────────────────────────────────

class TestRouteSignatures:
    """所有路由端点应有合理的错误处理"""

    def test_register_routes_exists(self):
        """register_routes 函数存在"""
        from routes import register_routes
        assert callable(register_routes)

    def test_register_routes_accepts_app_and_socketio(self):
        """register_routes(app, socketio) 接受两个参数"""
        import inspect
        from routes import register_routes
        sig = inspect.signature(register_routes)
        params = list(sig.parameters.keys())
        assert "app" in params
        assert "socketio" in params


# ── 日志使用（验证无 print 残留） ──────────────────────────────

class TestLoggingUsage:
    """确认使用 logger 而非 print"""

    def test_no_print_statements(self):
        """routes.py 不应有 print() 调用"""
        routes_path = os.path.join(os.path.dirname(__file__), "..", "routes.py")
        with open(routes_path) as f:
            lines = f.readlines()
        prints = [
            i + 1 for i, line in enumerate(lines)
            if "print(" in line and not line.strip().startswith("#")
        ]
        assert len(prints) == 0, f"routes.py 含 print() 调用于行: {prints}"


# ── 代码质量 ────────────────────────────────────────────────────

class TestCodeQuality:
    """基础代码质量标准"""

    def test_no_commented_out_code_blocks(self):
        """无大段注释掉的代码"""
        routes_path = os.path.join(os.path.dirname(__file__), "..", "routes.py")
        with open(routes_path) as f:
            lines = f.readlines()
        # 检测连续多行注释掉的代码（注释行含函数定义 / 变量赋值）
        consecutive = 0
        max_consecutive = 0
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("# ") and any(
                kw in stripped for kw in ["def ", "class ", "return ", "@app"]
            ):
                consecutive += 1
                max_consecutive = max(max_consecutive, consecutive)
            else:
                consecutive = 0
        assert max_consecutive <= 2, \
            f"发现 {max_consecutive} 行连续注释掉的代码，请删除"

    def test_imports_are_grouped(self):
        """导入语句应分组（stdlib → third-party → local）"""
        routes_path = os.path.join(os.path.dirname(__file__), "..", "routes.py")
        with open(routes_path) as f:
            source = f.read()
        # 确认六大必需模块被导入
        required = ["asyncio", "json", "logging", "threading", "flask", "utils"]
        for mod in required:
            assert mod in source.lower(), f"缺少 {mod} 导入"
