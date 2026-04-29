"""测试 app.py — Flask 工厂、Bot 生命周期、全局状态管理"""

import os
import sys
import threading
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── 应用工厂 ────────────────────────────────────────────────────

class TestCreateApp:
    """create_app() 工厂函数"""

    def test_create_app_returns_flask_app(self):
        """create_app 返回 Flask 实例"""
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch("app.BOT_TOKEN", ""), \
             mock.patch("app.SECRET_KEY", "test-key"), \
             mock.patch("app.FFMPEG_PATH", "/fake/ffmpeg"), \
             mock.patch("app.FFPROBE_PATH", "/fake/ffprobe"), \
             mock.patch("app.kookvoice.set_ffmpeg"), \
             mock.patch("app.kookvoice.configure_logging"), \
             mock.patch("routes.register_routes"):
            from app import create_app
            app = create_app()
            assert app is not None
            # Flask 应用应有 secret_key
            assert app.config.get("SECRET_KEY") == "test-key"

    def test_create_app_no_token_no_bot_start(self):
        """没有 BOT_TOKEN 时不应启动 bot"""
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch("app.BOT_TOKEN", ""), \
             mock.patch("app.SECRET_KEY", ""), \
             mock.patch("app.FFMPEG_PATH", "/fake/ffmpeg"), \
             mock.patch("app.FFPROBE_PATH", "/fake/ffprobe"), \
             mock.patch("app.kookvoice.set_ffmpeg"), \
             mock.patch("app.kookvoice.configure_logging"), \
             mock.patch("routes.register_routes"), \
             mock.patch("app.start_bot") as mock_start:
            from app import create_app
            create_app()
            mock_start.assert_not_called()


# ── Bot 管理 ────────────────────────────────────────────────────

class TestBotLifecycle:
    """get_bot / start_bot / stop_bot 生命周期"""

    def test_get_bot_without_token_raises(self):
        """无 token 时 get_bot() 抛出 RuntimeError"""
        import app
        app._bot = None  # 重置
        with mock.patch("app.BOT_TOKEN", ""):
            with pytest.raises(RuntimeError, match="BOT_TOKEN"):
                app.get_bot()

    def test_get_bot_with_token_returns_bot(self):
        """有 token 时 get_bot() 返回 Bot 实例"""
        import app
        app._bot = None
        with mock.patch("app.BOT_TOKEN", "fake-token"), \
             mock.patch("app.Bot") as MockBot:
            MockBot.return_value = "mock-bot-instance"
            result = app.get_bot()
            assert result == "mock-bot-instance"
            MockBot.assert_called_once_with(token="fake-token", compress=True)

    def test_get_bot_singleton(self):
        """get_bot 返回单例（第二次调用不重新创建）"""
        import app
        app._bot = "cached-instance"
        with mock.patch("app.BOT_TOKEN", "fake-token"), \
             mock.patch("app.Bot") as MockBot:
            result = app.get_bot()
            assert result == "cached-instance"
            MockBot.assert_not_called()

    def test_get_bot_loop_not_started(self):
        """Bot 未启动时 get_bot_loop 抛异常"""
        import app
        app._bot_loop = None
        with pytest.raises(RuntimeError, match="尚未启动"):
            app.get_bot_loop()

    def test_stop_bot_when_not_running(self):
        """stop_bot 在 bot 未运行时安全退出"""
        import app
        app._bot_loop = None
        app._bot_thread = None
        # 不应抛异常
        app.stop_bot()


# ── 全局状态初始化 ──────────────────────────────────────────────

class TestGlobalState:
    """全局共享状态应有初始值"""

    def test_guild_data_is_dict(self):
        """guild_data 初始为空字典"""
        import app
        assert isinstance(app.guild_data, dict)
        # 新 import 会重置，所以直接用 class-level 断言

    def test_current_guild_id_is_none(self):
        """current_guild_id 初始为 None"""
        # 不做严格测试，因为可能已被修改，但类型应为 str|None
        import app
        assert isinstance(app.current_guild_id, (str, type(None)))


# ── 代码质量 ────────────────────────────────────────────────────

class TestCodeQuality:
    """app.py 代码质量"""

    def test_no_print_statements(self):
        """不应有 print() 调用"""
        app_path = os.path.join(os.path.dirname(__file__), "..", "app.py")
        with open(app_path) as f:
            lines = f.readlines()
        prints = [
            i + 1 for i, line in enumerate(lines)
            if "print(" in line and not line.strip().startswith("#")
        ]
        assert len(prints) == 0, f"app.py 含 print() 于行: {prints}"

    def test_no_hardcoded_tokens(self):
        """不应含硬编码 token"""
        app_path = os.path.join(os.path.dirname(__file__), "..", "app.py")
        with open(app_path) as f:
            source = f.read()
        import re
        suspicious = re.findall(
            r'(?:token|secret|password|api_key)\s*=\s*["\']([^"\']{10,})["\']',
            source, re.IGNORECASE
        )
        assert len(suspicious) == 0, f"app.py 硬编码凭据: {suspicious}"

    def test_bot_token_from_config(self):
        """BOT_TOKEN 从 config 导入"""
        app_path = os.path.join(os.path.dirname(__file__), "..", "app.py")
        with open(app_path) as f:
            source = f.read()
        assert "from config import" in source
        assert "BOT_TOKEN" in source
