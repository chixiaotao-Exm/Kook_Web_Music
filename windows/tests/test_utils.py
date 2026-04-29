"""测试 utils.py — 备用 API 容错、歌词解析 split、配置持久化"""

import json
import os
import sys
import tempfile
from unittest import mock

import pytest


# 确保 windows 目录在 sys.path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestBackupAPI:
    """备用 API 容错测试 — 无 BACKUP_MUSIC_API 时不应崩溃"""

    def test_search_music_without_backup_api(self):
        """search_music 在 BACKUP_MUSIC_API=None 时不崩溃，返回空"""
        with mock.patch.dict("sys.modules", {}):
            import config
            # 模拟 BACKUP_MUSIC_API 未定义
            config.MUSIC_API_BASE = "https://fake.example.com"

            with mock.patch("utils.BACKUP_MUSIC_API", None), \
                 mock.patch("utils.requests.get") as mock_get:
                mock_get.side_effect = Exception("主 API 挂了")
                from utils import search_music
                result = search_music("test")
                assert result == []

    def test_get_music_url_without_backup_api(self):
        """get_music_url 在 BACKUP_MUSIC_API=None 时返回空字符串"""
        with mock.patch("utils.BACKUP_MUSIC_API", None), \
             mock.patch("utils.requests.get") as mock_get:
            mock_get.side_effect = Exception("主 API 挂了")
            from utils import get_music_url
            result = get_music_url("12345")
            assert result == ""

    def test_get_playlist_without_backup_api(self):
        """get_playlist 在 BACKUP_MUSIC_API=None 时返回空字典"""
        with mock.patch("utils.BACKUP_MUSIC_API", None), \
             mock.patch("utils.requests.get") as mock_get:
            mock_get.side_effect = Exception("主 API 挂了")
            from utils import get_playlist
            result = get_playlist("12345")
            assert result == {}


class TestSplitColonFix:
    """冒号分割修正 — split(":", 3) 防止歌名含冒号时截断"""

    def test_split_song_with_colon_in_name(self):
        """歌名含冒号时不会截断"""
        from utils import format_playlist_data
        play_list_data = {
            "now_playing": None,
            "play_list": [
                {
                    "file": "PLAYLIST_SONG|||123|||歌:名字|||艺术家",
                    "extra": {},
                }
            ],
        }
        result = format_playlist_data(play_list_data)
        assert len(result) == 1
        assert result[0]["id"] == "123"
        assert result[0]["name"] == "歌:名字"
        assert result[0]["artist"] == "艺术家"

    def test_split_song_with_multiple_colons(self):
        """歌名含多个冒号"""
        from utils import format_playlist_data
        play_list_data = {
            "now_playing": None,
            "play_list": [
                {
                    "file": "PLAYLIST_SONG|||456|||A:B:C|||歌手D",
                    "extra": {},
                }
            ],
        }
        result = format_playlist_data(play_list_data)
        assert result[0]["name"] == "A:B:C"
        assert result[0]["artist"] == "歌手D"

    def test_split_normal_song(self):
        """正常歌名不受影响"""
        from utils import format_playlist_data
        play_list_data = {
            "now_playing": None,
            "play_list": [
                {
                    "file": "PLAYLIST_SONG|||789|||简单歌名|||张三",
                    "extra": {},
                }
            ],
        }
        result = format_playlist_data(play_list_data)
        assert result[0]["id"] == "789"
        assert result[0]["name"] == "简单歌名"
        assert result[0]["artist"] == "张三"

    def test_now_playing_with_colon(self):
        """当前播放歌曲含冒号"""
        from utils import format_playlist_data
        play_list_data = {
            "now_playing": {
                "file": "PLAYLIST_SONG|||111|||花:海|||周杰伦",
                "extra": {},
                "duration": 240,
                "ss": 30,
                "start": 1700000000,
            },
            "play_list": [],
        }
        result = format_playlist_data(play_list_data)
        assert result[0]["name"] == "花:海"
        assert result[0]["artist"] == "周杰伦"
        assert result[0]["playing"] is True
        assert result[0]["position"] == 30

    def test_incomplete_marker(self):
        """不完整的 PLAYLIST_SONG 标记安全处理"""
        from utils import format_playlist_data
        play_list_data = {
            "now_playing": None,
            "play_list": [
                {
                    "file": "PLAYLIST_SONG|||only_two",
                    "extra": {},
                }
            ],
        }
        result = format_playlist_data(play_list_data)
        # 不完整标记被跳过，不会落入普通文件分支
        assert len(result) == 0


class TestSaveLoadConfig:
    """配置持久化测试"""

    def test_save_and_load_roundtrip(self):
        """save_config → load_config 往返一致"""
        from utils import save_config, load_config
        data = {"key1": "value1", "key2": 42, "nested": {"a": 1}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{}")
            tmp_path = f.name
        try:
            assert save_config(data, tmp_path) is True
            loaded = load_config(tmp_path)
            assert loaded == data
        finally:
            os.unlink(tmp_path)

    def test_load_nonexistent_file(self):
        """加载不存在的文件返回空字典"""
        from utils import load_config
        result = load_config("/nonexistent/path/config.json")
        assert result == {}

    def test_save_to_unwritable_path(self):
        """保存到不可写路径返回 False"""
        from utils import save_config
        result = save_config({}, "/root/protected/config.json")
        assert result is False


class TestCookieLoading:
    """Cookie 加载测试"""

    def test_load_cookie_from_file(self):
        """从文件加载 cookie"""
        from utils import load_cookie_header
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("my_cookie=abc123")
            tmp_path = f.name
        try:
            with mock.patch("utils.COOKIE_TXT_PATH", tmp_path):
                result = load_cookie_header()
                assert result == "my_cookie=abc123"
        finally:
            os.unlink(tmp_path)

    def test_load_cookie_file_not_exists(self):
        """Cookie 文件不存在时返回空字符串"""
        from utils import load_cookie_header
        with mock.patch("utils.COOKIE_TXT_PATH", "/nonexistent/cookie.txt"):
            result = load_cookie_header()
            assert result == ""

    def test_build_headers_with_cookie(self):
        """build_headers 包含 cookie 时正确设置"""
        from utils import build_headers
        with mock.patch("utils.load_cookie_header", return_value="session=xyz"):
            headers = build_headers()
            assert headers["Cookie"] == "session=xyz"
            assert "User-Agent" in headers

    def test_build_headers_extra(self):
        """build_headers 合并额外 header"""
        from utils import build_headers
        with mock.patch("utils.load_cookie_header", return_value=""):
            headers = build_headers({"X-Custom": "test"})
            assert headers["X-Custom"] == "test"


class TestPlaylistAllTracks:
    """歌单分页获取测试"""

    def test_empty_playlist(self):
        """空歌单返回空列表"""
        from utils import get_playlist_all_tracks
        with mock.patch("utils.get_playlist", return_value={}):
            result = get_playlist_all_tracks("123")
            assert result == []

    def test_single_page(self):
        """单页歌单"""
        from utils import get_playlist_all_tracks
        mock_playlist = {"trackCount": 3}
        mock_songs = [{"id": i, "name": f"song{i}"} for i in range(3)]

        with mock.patch("utils.get_playlist", return_value=mock_playlist), \
             mock.patch("utils.requests.get") as mock_get:
            mock_resp = mock.MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"songs": mock_songs}
            mock_get.return_value = mock_resp

            result = get_playlist_all_tracks("123")
            assert len(result) == 3

    def test_network_error_during_pagination(self):
        """分页时网络错误不崩溃"""
        from utils import get_playlist_all_tracks
        mock_playlist = {"trackCount": 10}

        with mock.patch("utils.get_playlist", return_value=mock_playlist), \
             mock.patch("utils.requests.get", side_effect=Exception("网络错误")):
            result = get_playlist_all_tracks("123")
            assert result == []


class TestGetPlaylistUrls:
    """get_playlist_urls — 标记生成"""

    def test_marker_format(self):
        """歌单歌曲标记格式正确"""
        from utils import get_playlist_urls
        tracks = [
            {"id": 123, "name": "晴天", "ar": [{"name": "周杰伦"}]},
            {"id": 456, "name": "七里香", "ar": [{"name": "周杰伦"}]},
        ]
        with mock.patch("utils.get_playlist_all_tracks", return_value=tracks):
            result = get_playlist_urls("playlist_1")
            assert len(result) == 2
            assert result[0]["marker"] == "PLAYLIST_SONG|||123|||晴天|||周杰伦"
            assert result[1]["marker"] == "PLAYLIST_SONG|||456|||七里香|||周杰伦"

    def test_song_with_no_artist(self):
        """无艺术家信息的歌曲"""
        from utils import get_playlist_urls
        tracks = [{"id": 999, "name": "纯音乐", "ar": []}]
        with mock.patch("utils.get_playlist_all_tracks", return_value=tracks):
            result = get_playlist_urls("pl")
            assert result[0]["artist"] == ""
            assert result[0]["marker"] == "PLAYLIST_SONG|||999|||纯音乐|||"


# ── 安全：无硬编码敏感信息 ──────────────────────────

class TestNoSecretsHardcoded:
    """确认 utils.py 中不含硬编码凭据"""

    def test_no_api_keys_in_source(self):
        """源码不应含硬编码 API key"""
        utils_path = os.path.join(os.path.dirname(__file__), "..", "utils.py")
        with open(utils_path) as f:
            source = f.read()
        import re
        # 检测类似 "api_key=..." 或 "token=..." 的赋值
        suspicious = re.findall(
            r'(?:api_key|secret|password|token)\s*=\s*["\']([^"\']{8,})["\']',
            source, re.IGNORECASE
        )
        for match in suspicious:
            # 允许占位符和空
            assert match == "" or match == "your-", \
                f"硬编码凭据: {match}"
