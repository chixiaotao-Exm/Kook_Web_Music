"""
KOOK Web Music — Flask 应用工厂
"""
import os
import sys
import asyncio
import threading
import logging
from flask import Flask

from khl import Bot, Message  # type: ignore[import-untyped]
import kookvoice  # type: ignore[import-untyped]
from config import (
    SECRET_KEY,
    BOT_TOKEN,
    FFMPEG_PATH,
    FFPROBE_PATH,
    MUSIC_API_BASE,
    DEBUG,
)
from utils import (
    search_music,
    get_music_url,
    get_playlist,
    get_playlist_urls,
)

logger = logging.getLogger(__name__)

# ── 全局共享状态 ──────────────────────────────────────────────
guild_data: dict = {}
current_guild_id: str | None = None

# ── Bot 持有者（延迟实例化） ─────────────────────────────────
_bot: Bot | None = None
_bot_thread: threading.Thread | None = None
_bot_loop: asyncio.AbstractEventLoop | None = None


def get_bot() -> Bot:
    """线程安全地获取 Bot 实例。第一次调用时实例化。"""
    global _bot
    if _bot is None:
        if not BOT_TOKEN:
            raise RuntimeError("BOT_TOKEN 未设置，请在 .env 文件中配置")
        _bot = Bot(token=BOT_TOKEN, compress=True)
    return _bot


def get_bot_loop() -> asyncio.AbstractEventLoop:
    """获取 bot 所在的事件循环。"""
    global _bot_loop
    if _bot_loop is None:
        raise RuntimeError("Bot 尚未启动，请先调用 start_bot()")
    return _bot_loop


# ── Bot 管理 ──────────────────────────────────────────────────

async def _verify_token(bot: Bot) -> bool:
    try:
        resp = await bot.client.gate.request("GET", "guild/list")
        if not isinstance(resp, dict):
            raise ValueError("API 响应格式错误")
        items = resp.get("items", [])
        logger.info("Token 验证成功，可访问 %d 个服务器", len(items))
        return True
    except Exception:
        logger.exception("Token 验证失败")
        return False


async def _bot_main(bot: Bot) -> None:
    """bot 的主协程。"""
    if not await _verify_token(bot):
        logger.critical("Token 验证失败，请检查配置")
        sys.exit(1)

    # ── 注册 bot 命令 ─────────────────
    register_bot_commands(bot)

    logger.info("机器人开始运行...")
    await bot.start()
    logger.info("机器人已成功启动")


def _bot_thread_target() -> None:
    global _bot_loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _bot_loop = loop
    try:
        loop.run_until_complete(_bot_main(get_bot()))
    except Exception:
        logger.exception("Bot 线程异常退出")
    finally:
        loop.close()
        _bot_loop = None


def start_bot() -> None:
    """在后台线程启动 KOOK bot。调用本函数前不会联网。"""
    global _bot_thread
    if _bot_thread is not None and _bot_thread.is_alive():
        logger.warning("Bot 已在运行中")
        return
    _bot_thread = threading.Thread(target=_bot_thread_target, daemon=True)
    _bot_thread.start()
    logger.info("Bot 线程已启动")


def stop_bot() -> None:
    """停止 bot（通过关闭事件循环）。"""
    global _bot_loop, _bot_thread
    if _bot_loop and _bot_loop.is_running():
        _bot_loop.call_soon_threadsafe(_bot_loop.stop)
    if _bot_thread:
        _bot_thread.join(timeout=5)


# ── KOOK 辅助函数 ─────────────────────────────────────────────

async def find_user_voice_channel(
    guild_id: str,
    author_id: str,
) -> str | None:
    bot = get_bot()
    try:
        resp = await bot.client.gate.request(
            "GET",
            "channel-user/get-joined-channel",
            params={"guild_id": guild_id, "user_id": author_id},
        )
        if resp and "items" in resp and resp["items"]:
            return resp["items"][0]["id"]
    except Exception:
        logger.exception("获取用户语音频道失败")
    return None


# ── Bot 命令注册 ──────────────────────────────────────────────

def register_bot_commands(bot: Bot) -> None:
    """注册所有 KOOK 机器人命令。"""

    @bot.command(name="ping")
    async def ping_cmd(msg: Message):
        await msg.reply("pong!")

    @bot.command(name="加入")
    async def join_cmd(msg: Message):
        try:
            channel = await find_user_voice_channel(
                msg.ctx.guild.id, msg.author_id
            )
            if channel:
                player = kookvoice.Player(
                    msg.ctx.guild.id, channel, BOT_TOKEN
                )
                player.join()
                vc = await bot.client.fetch_public_channel(channel)
                await msg.reply(f"✅ 已加入语音频道 #{vc.name}")
            else:
                await msg.reply("❌ 您当前不在语音频道中")
        except Exception:
            logger.exception("加入命令失败")
            await msg.reply("⚠️ 加入失败，请检查权限或稍后再试")

    @bot.command(name="wy")
    async def play_music(msg: Message, music_input: str):
        try:
            channel = await find_user_voice_channel(
                msg.ctx.guild.id, msg.author_id
            )
            if not channel:
                await msg.reply("❌ 请先加入语音频道")
                return

            if music_input.startswith("http"):
                music_url = music_input
                song_name = "直链音乐"
            else:
                import requests as req

                songs = search_music(music_input)
                if not songs:
                    await msg.reply("❌ 未搜索到歌曲")
                    return
                song = songs[0]
                song_name = song.get("name", music_input)
                artist = song.get("ar", [{}])[0].get("name", "未知")
                song_id = song["id"]

                music_url = get_music_url(song_id)
                if not music_url:
                    await msg.reply("❌ 获取直链失败，可能是VIP歌曲")
                    return

            player = kookvoice.Player(
                msg.ctx.guild.id, channel, BOT_TOKEN
            )
            player.add_music(
                music_url,
                {"音乐名字": song_name, "点歌人": msg.author_id,
                 "文字频道": msg.ctx.channel.id},
            )
            await msg.reply(f"✅ {song_name} 已加入播放队列")
        except Exception:
            logger.exception("播放音乐失败")
            await msg.reply("⚠️ 播放失败，请稍后再试")

    @bot.command(name="停止")
    async def stop_music(msg: Message):
        try:
            kookvoice.Player(msg.ctx.guild.id).stop()
            await msg.reply("⏹️ 已停止播放")
        except Exception:
            logger.exception("停止失败")
            await msg.reply("⚠️ 停止失败")

    @bot.command(name="跳过")
    async def skip_music(msg: Message):
        try:
            kookvoice.Player(msg.ctx.guild.id).skip()
            await msg.reply("⏭️ 已跳过当前歌曲")
        except Exception:
            logger.exception("跳过失败")
            await msg.reply("⚠️ 跳过失败")

    @bot.command(name="暂停")
    async def pause_music(msg: Message):
        try:
            kookvoice.Player(msg.ctx.guild.id).pause()
            await msg.reply("⏸️ 已暂停播放")
        except Exception:
            logger.exception("暂停失败")
            await msg.reply("⚠️ 暂停失败")

    @bot.command(name="继续")
    async def resume_music(msg: Message):
        try:
            kookvoice.Player(msg.ctx.guild.id).resume()
            await msg.reply("▶️ 已继续播放")
        except Exception:
            logger.exception("继续失败")
            await msg.reply("⚠️ 继续播放失败")

    @bot.command(name="wygd")
    async def playlist_play(msg: Message, playlist_input: str):
        try:
            channel = await find_user_voice_channel(
                msg.ctx.guild.id, msg.author_id
            )
            if not channel:
                await msg.reply("❌ 请先加入语音频道")
                return

            import re
            import requests as req

            m = re.search(
                r"id=(\d+)|playlist/(\d+)|(\d{6,})",
                playlist_input,
            )
            playlist_id = m.group(1) or m.group(2) or m.group(3) if m else playlist_input

            await msg.reply(f"🎶 正在获取歌单 {playlist_id} ...")
            playlist = get_playlist(playlist_id)
            if not playlist:
                await msg.reply("❌ 获取歌单失败")
                return

            playlist_name = playlist.get("name", "未知歌单")
            track_ids = [
                str(t["id"]) for t in playlist.get("trackIds", [])
            ]
            if not track_ids:
                track_ids = [
                    str(t["id"]) for t in playlist.get("tracks", [])
                ]

            if not track_ids:
                await msg.reply("❌ 歌单为空")
                return

            player = kookvoice.Player(
                msg.ctx.guild.id, channel, BOT_TOKEN
            )
            added = 0
            for sid in track_ids[:50]:
                url = get_music_url(sid)
                if url:
                    player.add_music(
                        url,
                        {"歌单来源": playlist_name,
                         "点歌人": msg.author_id,
                         "文字频道": msg.ctx.channel.id},
                    )
                    added += 1

            if added:
                await msg.reply(
                    f"✅ 已添加 {added} 首歌曲\n📋 歌单: {playlist_name}"
                )
            else:
                await msg.reply("❌ 没有成功添加任何歌曲")
        except Exception:
            logger.exception("歌单播放失败")
            await msg.reply("⚠️ 播放歌单失败，请稍后再试")


# ── Flask 应用工厂 ────────────────────────────────────────────

def create_app() -> Flask:
    """创建并配置 Flask 应用（懒加载模式，不自动启动 bot）。"""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = SECRET_KEY

    # SocketIO（可选）
    socketio = None
    try:
        from flask_socketio import SocketIO  # type: ignore[import-untyped]
        socketio = SocketIO(app, cors_allowed_origins="*")
    except ImportError:
        logger.warning("flask_socketio 未安装，WebSocket 功能不可用")

    # FFMPEG 初始化
    try:
        kookvoice.set_ffmpeg(FFMPEG_PATH)
        kookvoice.configure_logging(True)
        logger.info("FFMPEG: %s / FFPROBE: %s", FFMPEG_PATH, FFPROBE_PATH)
        if not os.path.exists(FFMPEG_PATH):
            logger.warning("FFMPEG 路径不存在: %s", FFMPEG_PATH)
    except Exception:
        logger.exception("FFMPEG 配置失败")

    # 注册路由
    from routes import register_routes
    register_routes(app, socketio)

    # 延迟启动 bot（导入时不启动，由 run.py 显式调用）
    # 如果 BOT_TOKEN 已配置且非调试模式，自动启动
    if BOT_TOKEN:
        start_bot()

    return app
