"""测试 config.py — 环境变量读取、默认值、类型转换"""

import os
import sys
from unittest import mock


class TestConfigDefaults:
    """配置默认值测试 — 无环境变量时的行为"""

    def test_debug_defaults_to_false(self):
        """DEBUG 默认应为 False"""
        with mock.patch.dict(os.environ, {}, clear=True):
            import importlib
            import config
            importlib.reload(config)
            assert config.DEBUG is False

    def test_host_defaults_to_all_interfaces(self):
        """HOST 默认应为 0.0.0.0"""
        with mock.patch.dict(os.environ, {}, clear=True):
            import importlib
            import config
            importlib.reload(config)
            assert config.HOST == "0.0.0.0"

    def test_port_defaults_to_5000_int(self):
        """PORT 默认应为整数 5000"""
        with mock.patch.dict(os.environ, {}, clear=True):
            import importlib
            import config
            importlib.reload(config)
            assert config.PORT == 5000
            assert isinstance(config.PORT, int)

    def test_bot_token_defaults_empty(self):
        """BOT_TOKEN 默认应为空字符串"""
        with mock.patch.dict(os.environ, {}, clear=True):
            import importlib
            import config
            importlib.reload(config)
            assert config.BOT_TOKEN == ""

    def test_music_api_base_has_default(self):
        """MUSIC_API_BASE 即使无环境变量也应有默认值"""
        with mock.patch.dict(os.environ, {}, clear=True):
            import importlib
            import config
            importlib.reload(config)
            assert config.MUSIC_API_BASE.startswith("https://")

    def test_backup_music_api_has_default(self):
        """BACKUP_MUSIC_API 有默认备用 API"""
        with mock.patch.dict(os.environ, {}, clear=True):
            import importlib
            import config
            importlib.reload(config)
            assert config.BACKUP_MUSIC_API.startswith("https://")


class TestConfigFromEnv:
    """从环境变量读取配置"""

    def test_debug_true_via_env(self):
        """DEBUG=true 环境变量应为 True"""
        with mock.patch.dict(os.environ, {"DEBUG": "true"}, clear=True):
            import importlib
            import config
            importlib.reload(config)
            assert config.DEBUG is True

    def test_debug_1_via_env(self):
        """DEBUG=1 应为 True"""
        with mock.patch.dict(os.environ, {"DEBUG": "1"}, clear=True):
            import importlib
            import config
            importlib.reload(config)
            assert config.DEBUG is True

    def test_port_from_env_as_int(self):
        """PORT 从环境变量读取应为整数"""
        with mock.patch.dict(os.environ, {"PORT": "8080"}, clear=True):
            import importlib
            import config
            importlib.reload(config)
            assert config.PORT == 8080
            assert isinstance(config.PORT, int)

    def test_bot_token_from_env(self):
        """BOT_TOKEN 应从环境变量读取"""
        with mock.patch.dict(os.environ, {"BOT_TOKEN": "test-token-123"}, clear=True):
            import importlib
            import config
            importlib.reload(config)
            assert config.BOT_TOKEN == "test-token-123"

    def test_custom_ffmpeg_path(self):
        """FFMPEG_PATH 可被环境变量覆盖"""
        with mock.patch.dict(os.environ, {"FFMPEG_PATH": "/custom/ffmpeg"}, clear=True):
            import importlib
            import config
            importlib.reload(config)
            assert config.FFMPEG_PATH == "/custom/ffmpeg"

    def test_custom_host(self):
        """HOST 从环境变量读取"""
        with mock.patch.dict(os.environ, {"HOST": "127.0.0.1"}, clear=True):
            import importlib
            import config
            importlib.reload(config)
            assert config.HOST == "127.0.0.1"

    def test_secret_key_from_env(self):
        """SECRET_KEY 从环境变量读取"""
        with mock.patch.dict(os.environ, {"SECRET_KEY": "my-secret"}, clear=True):
            import importlib
            import config
            importlib.reload(config)
            assert config.SECRET_KEY == "my-secret"


class TestConfigNoSecretsHardcoded:
    """安全：确认配置不存在硬编码的敏感信息"""

    def test_no_token_in_source(self):
        """config.py 源码中不含真实 token"""
        config_path = os.path.join(os.path.dirname(__file__), "..", "config.py")
        with open(config_path, "r") as f:
            source = f.read()
        # 不应包含看起来像真实 token 的长字符串
        import re
        quoted_strings = re.findall(r'"([^"]{20,})"', source)
        for s in quoted_strings:
            # 允许 URL
            assert not s.startswith(("1/", "Bot ")), f"可疑字符串: {s}"
