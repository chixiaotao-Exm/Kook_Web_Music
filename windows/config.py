import os

# 基本配置
DEBUG = os.environ.get("DEBUG", "False").lower() in ("true", "1", "t")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "5000"))

# KOOK机器人配置
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# FFMPEG配置 — 使用相对路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
FFMPEG_PATH = os.environ.get(
    "FFMPEG_PATH",
    os.path.join(_current_dir, "ffmpeg", "bin", "ffmpeg.exe"),
)
FFPROBE_PATH = os.environ.get(
    "FFPROBE_PATH",
    os.path.join(_current_dir, "ffmpeg", "bin", "ffprobe.exe"),
)

# 音乐API配置
MUSIC_API_BASE = os.environ.get(
    "MUSIC_API_BASE",
    "https://1304404172-f3na0r58ws.ap-beijing.tencentscf.com",
)

# 备用API地址
BACKUP_MUSIC_API = os.environ.get(
    "BACKUP_MUSIC_API",
    "https://api.music.liuzhijin.cn",
)

# Web控制台配置
SECRET_KEY = os.environ.get("SECRET_KEY", os.urandom(24).hex())
