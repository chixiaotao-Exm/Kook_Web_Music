"""API 路由 — 供 Flask 注册使用"""
import asyncio
import json
import logging
import threading
import requests as req

from flask import render_template, request, jsonify  # type: ignore[import-untyped]

import kookvoice  # type: ignore[import-untyped]
from config import BOT_TOKEN, SECRET_KEY
from utils import (
    search_music,
    get_music_url,
    get_playlist_urls,
    format_playlist_data,
)

logger = logging.getLogger(__name__)


# ── 全局状态引用 ──────────────────────────────────────────────
# 这些变量由 app.create_app() 导入模块后赋值。


# ── 异步桥接（轻量级，不复用 app.py 以防止循环导入） ────────

def run_async(coro):
    """在 Flask 请求线程中安全执行异步协程。
    使用单独线程+事件循环，超时 15 秒。"""
    result: list = [None]
    exc: list = [None]

    def _target():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result[0] = loop.run_until_complete(coro)
        except Exception as e:
            exc[0] = e
        finally:
            loop.close()

    t = threading.Thread(target=_target)
    t.start()
    t.join(timeout=15)
    if t.is_alive():
        logger.warning("异步函数执行超时")
        return None
    if exc[0]:
        raise exc[0]
    return result[0]


# ── 路由注册 ──────────────────────────────────────────────────

def register_routes(app, socketio=None):
    """向 Flask app 注册所有路由"""

    # ── 页面 ────────────────────────
    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/dashboard")
    def dashboard():
        return render_template("dashboard.html")

    # ── 服务器 / 频道 ──────────────
    @app.route("/api/guilds", methods=["GET"])
    def get_guilds():
        try:
            if not BOT_TOKEN:
                return jsonify({"success": False, "error": "BOT_TOKEN 未配置"})

            headers = {
                "Authorization": f"Bot {BOT_TOKEN}",
                "Content-Type": "application/json",
            }
            resp = req.get(
                "https://www.kookapp.cn/api/v3/guild/list",
                headers=headers,
                timeout=10,
            )
            if resp.status_code != 200:
                return jsonify({"success": False, "error": f"HTTP {resp.status_code}"})

            data = resp.json()
            if data.get("code") != 0:
                return jsonify({"success": False, "error": data.get("message", "未知错误")})

            guilds = data.get("data", {}).get("items", [])
            formatted = [
                {
                    "id": g.get("id"),
                    "name": g.get("name", "未知服务器"),
                    "icon": g.get("icon"),
                    "master_id": g.get("master_id"),
                }
                for g in guilds
            ]
            return jsonify({"success": True, "guilds": formatted})
        except Exception:
            logger.exception("获取服务器列表失败")
            return jsonify({"success": False, "error": "服务器内部错误"})

    @app.route("/api/channels", methods=["GET"])
    def get_channels():
        guild_id = request.args.get("guild_id")
        if not guild_id:
            return jsonify({"success": False, "error": "缺少 guild_id 参数"})
        if not BOT_TOKEN:
            return jsonify({"success": False, "error": "BOT_TOKEN 未配置"})

        try:
            headers = {
                "Authorization": f"Bot {BOT_TOKEN}",
                "Content-Type": "application/json",
            }
            resp = req.get(
                f"https://www.kookapp.cn/api/v3/channel/list?guild_id={guild_id}",
                headers=headers,
                timeout=10,
            )
            if resp.status_code != 200:
                return jsonify({"success": False, "error": f"HTTP {resp.status_code}"})

            data = resp.json()
            if data.get("code") != 0:
                return jsonify({"success": False, "error": data.get("message")})

            channels = data.get("data", {}).get("items", [])
            formatted = [
                {"id": c.get("id"), "name": c.get("name", "未知频道"), "type": c.get("type")}
                for c in channels
                if c.get("type") == 2  # 仅语音频道
            ]
            return jsonify({"success": True, "channels": formatted})
        except Exception:
            logger.exception("获取频道列表失败")
            return jsonify({"success": False, "error": "服务器内部错误"})

    # ── 语音频道操作 ────────────────
    @app.route("/api/join", methods=["POST"])
    def join_channel():
        data = request.get_json(silent=True) or {}
        guild_id = data.get("guild_id")
        channel_id = data.get("channel_id")
        if not guild_id or not channel_id:
            return jsonify({"success": False, "error": "缺少 guild_id / channel_id"})
        try:
            player = kookvoice.Player(guild_id, channel_id, BOT_TOKEN)
            player.join()
            return jsonify({"success": True})
        except Exception as e:
            logger.exception("加入频道失败")
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/leave", methods=["POST"])
    def leave_channel():
        data = request.get_json(silent=True) or {}
        guild_id = data.get("guild_id")
        if not guild_id:
            return jsonify({"success": False, "error": "缺少 guild_id"})
        try:
            kookvoice.Player(guild_id).stop()
            return jsonify({"success": True})
        except Exception as e:
            logger.exception("离开频道失败")
            return jsonify({"success": False, "error": str(e)})

    # ── 媒体控制 ────────────────────
    def _require_guild():
        data = request.get_json(silent=True) or {}
        gid = data.get("guild_id")
        if not gid:
            return None, jsonify({"success": False, "error": "缺少 guild_id"})
        return gid, None

    @app.route("/api/play", methods=["POST"])
    def play_music():
        data = request.get_json(silent=True) or {}
        guild_id = data.get("guild_id")
        channel_id = data.get("channel_id")
        song_id = data.get("song_id")
        song_name = data.get("song_name", "")
        artist_name = data.get("artist_name", "")
        if not guild_id or not song_id:
            return jsonify({"success": False, "error": "缺少必要参数"})
        try:
            url = get_music_url(song_id)
            if not url:
                return jsonify({"success": False, "error": "无法获取音乐URL"})
            player = kookvoice.Player(guild_id, channel_id, BOT_TOKEN)
            player.add_music(url, {"title": song_name, "artist": artist_name})
            return jsonify({"success": True})
        except Exception as e:
            logger.exception("播放失败")
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/playlist", methods=["POST"])
    def add_playlist():
        data = request.get_json(silent=True) or {}
        guild_id = data.get("guild_id")
        channel_id = data.get("channel_id")
        playlist_id = data.get("playlist_id")
        if not guild_id or not playlist_id:
            return jsonify({"success": False, "error": "缺少必要参数"})
        try:
            songs = get_playlist_urls(playlist_id)
            if not songs:
                return jsonify({"success": False, "error": "歌单为空"})
            player = kookvoice.Player(guild_id, channel_id, BOT_TOKEN)
            for s in songs:
                player.add_music(
                    s["marker"],
                    {"title": s["name"], "artist": s["artist"]},
                )
            return jsonify({"success": True, "count": len(songs)})
        except Exception as e:
            logger.exception("添加歌单失败")
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/skip", methods=["POST"])
    def skip_music():
        gid, err = _require_guild()
        if err:
            return err
        try:
            kookvoice.Player(gid).skip()
            return jsonify({"success": True})
        except Exception as e:
            logger.exception("跳过失败")
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/seek", methods=["POST"])
    def seek_music():
        data = request.get_json(silent=True) or {}
        guild_id = data.get("guild_id")
        position = data.get("position")
        if not guild_id or position is None:
            return jsonify({"success": False, "error": "缺少必要参数"})
        try:
            kookvoice.Player(guild_id).seek(int(position))
            return jsonify({"success": True})
        except Exception as e:
            logger.exception("跳转失败")
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/pause", methods=["POST"])
    def pause_music():
        gid, err = _require_guild()
        if err:
            return err
        try:
            kookvoice.Player(gid).pause()
            return jsonify({"success": True})
        except Exception as e:
            logger.exception("暂停失败")
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/resume", methods=["POST"])
    def resume_music():
        gid, err = _require_guild()
        if err:
            return err
        try:
            kookvoice.Player(gid).resume()
            return jsonify({"success": True})
        except Exception as e:
            logger.exception("继续播放失败")
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/stop", methods=["POST"])
    def stop_music():
        gid, err = _require_guild()
        if err:
            return err
        try:
            kookvoice.Player(gid).stop()
            return jsonify({"success": True})
        except Exception as e:
            logger.exception("停止失败")
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/clear", methods=["POST"])
    def clear_playlist():
        data = request.get_json(silent=True) or {}
        guild_id = data.get("guild_id")
        if not guild_id:
            return jsonify({"success": False, "error": "缺少 guild_id"})
        try:
            if guild_id in kookvoice.play_list:
                kookvoice.play_list[guild_id]["play_list"] = []
            return jsonify({"success": True})
        except Exception as e:
            logger.exception("清空列表失败")
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/remove", methods=["POST"])
    def remove_from_playlist():
        data = request.get_json(silent=True) or {}
        guild_id = data.get("guild_id")
        index = data.get("index")
        if not guild_id or index is None:
            return jsonify({"success": False, "error": "缺少必要参数"})
        try:
            if guild_id in kookvoice.play_list:
                lst = kookvoice.play_list[guild_id]["play_list"]
                idx = int(index)
                if 0 <= idx < len(lst):
                    lst.pop(idx)
                    return jsonify({"success": True})
            return jsonify({"success": False, "error": "索引超出范围"})
        except Exception as e:
            logger.exception("移除歌曲失败")
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/search", methods=["GET"])
    def search():
        keyword = request.args.get("keyword")
        if not keyword:
            return jsonify({"success": False, "error": "缺少 keyword"})
        try:
            songs = search_music(keyword)
            return jsonify({"success": True, "songs": songs})
        except Exception as e:
            logger.exception("搜索失败")
            return jsonify({"success": False, "error": str(e)})

    @app.route("/api/playlist/current", methods=["GET"])
    def get_current_playlist():
        guild_id = request.args.get("guild_id")
        if not guild_id:
            return jsonify({"success": False, "error": "缺少 guild_id"})
        try:
            if guild_id in kookvoice.play_list:
                data = format_playlist_data(kookvoice.play_list[guild_id])
                return jsonify({"success": True, "playlist": data})
            return jsonify({"success": True, "playlist": []})
        except Exception as e:
            logger.exception("获取播放列表失败")
            return jsonify({"success": False, "error": str(e)})

    # ── 调试/状态 ──────────────────
    @app.route("/api/debug")
    def debug():
        try:
            active = len(kookvoice.play_list)
            playing = sum(
                1 for gd in kookvoice.play_list.values() if gd.get("now_playing")
            )
            queued = sum(
                len(gd.get("play_list", []))
                for gd in kookvoice.play_list.values()
            )
            import os
            return jsonify(
                {
                    "status": "success",
                    "bot_running": bool(BOT_TOKEN),
                    "active_guilds": active,
                    "playing_songs": playing,
                    "queued_songs": queued,
                    "ffmpeg_exists": os.path.exists(kookvoice.ffmpeg_bin),
                }
            )
        except Exception as e:
            logger.exception("调试接口失败")
            return jsonify({"status": "error", "error": str(e)})

    # ── SocketIO 事件 ──────────────
    if socketio:
        @socketio.on("connect")
        def handle_connect():
            logger.info("客户端已连接")

        @socketio.on("disconnect")
        def handle_disconnect():
            logger.info("客户端已断开")

        @socketio.on("join_room")
        def handle_join_room(data):
            gid = data.get("guild_id")
            if gid:
                socketio.join_room(gid)
                logger.info("客户端加入房间: %s", gid)

        @socketio.on("leave_room")
        def handle_leave_room(data):
            gid = data.get("guild_id")
            if gid:
                socketio.leave_room(gid)
                logger.info("客户端离开房间: %s", gid)
