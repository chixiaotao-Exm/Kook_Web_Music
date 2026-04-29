# 🎵 KOOK音乐机器人 Web控制台

一个功能强大的KOOK音乐机器人Web控制台，支持网易云音乐播放、歌单管理、远程控制等功能。通过现代化的Web界面，让您轻松管理KOOK服务器的音乐播放。

> 本项目 fork 自 [VexMare/Kook_Web_Music](https://github.com/VexMare/Kook_Web_Music)，主要修复了 Windows 版本的安全漏洞与架构问题。

## ✨ 核心功能

- **🎵 音乐播放**: 支持网易云音乐搜索与播放，海量音乐资源
- **📋 歌单管理**: 一键导入网易云歌单，支持自定义播放列表
- **🌐 Web控制台**: 现代化响应式界面，支持多设备访问
- **🎮 远程控制**: 无需在KOOK中输入命令，通过Web界面即可控制
- **🔊 语音频道**: 自动加入用户所在语音频道，智能语音管理
- **⚡ 实时同步**: 实时状态更新，Socket.IO 推送

## 🛠️ 技术特色

- **跨平台支持**: 同时支持 Windows 和 Ubuntu 系统
- **模块化设计**: 清晰的代码结构，易于维护和扩展
- **异步处理**: 基于 asyncio 的高性能异步架构
- **RESTful API**: 完整的API接口，支持第三方集成
- **安全优先**: 无 Shell 注入漏洞，参数安全传递

## 🚀 快速开始

### 环境要求

- Python 3.8+
- FFmpeg（Windows 版本已内置）
- KOOK 机器人 Token

### 安装步骤

**1. 克隆项目**

```bash
git clone https://github.com/chixiaotao-Exm/Kook_Web_Music.git
cd Kook_Web_Music
```

**2. 选择系统版本**

```bash
# Windows 用户
cd windows

# Ubuntu 用户
cd Ubuntu
```

**3. 安装依赖**

```bash
pip install -r requirements.txt
```

**4. 配置环境**

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env 文件，填入你的配置
# BOT_TOKEN=你的机器人Token
# SECRET_KEY=随机字符串
```

**5. 启动应用**

```bash
python run.py
```

**6. 访问控制台**

打开浏览器访问: `http://localhost:5000`

### 配置说明

`.env` 文件支持的配置项：

| 变量 | 必填 | 默认值 | 说明 |
|------|:--:|--------|------|
| `BOT_TOKEN` | ✅ | — | KOOK 机器人 Token |
| `SECRET_KEY` | ✅ | — | Flask session 加密密钥 |
| `HOST` | ❌ | `0.0.0.0` | Web 服务监听地址 |
| `PORT` | ❌ | `5000` | Web 服务端口 |
| `DEBUG` | ❌ | `False` | Flask 调试模式 |
| `FFMPEG_PATH` | ❌ | `C:/ffmpeg/bin/ffmpeg.exe` | ffmpeg 可执行文件路径 |
| `FFPROBE_PATH` | ❌ | `C:/ffmpeg/bin/ffprobe.exe` | ffprobe 可执行文件路径 |
| `MUSIC_API_BASE` | ❌ | `http://localhost:3000` | 网易云音乐 API 地址 |

## 📖 使用指南

### 基础操作

1. **选择服务器**: 在左侧面板选择要管理的KOOK服务器
2. **加入语音频道**: 选择语音频道并点击"加入频道"
3. **搜索音乐**: 在搜索框输入歌曲名称或歌手
4. **播放控制**: 使用播放、暂停、跳过等控制按钮
5. **歌单导入**: 输入网易云歌单ID或链接，一键导入

### 机器人命令

除了Web控制台，机器人还支持以下KOOK命令：

| 命令 | 功能 | 示例 |
|------|------|------|
| `/ping` | 测试机器人连接 | `/ping` |
| `/加入` | 加入用户所在语音频道 | `/加入` |
| `/wy 歌曲名` | 播放网易云音乐 | `/wy 稻香` |
| `/wygd 歌单ID` | 播放网易云歌单 | `/wygd 123456789` |
| `/暂停` | 暂停播放 | `/暂停` |
| `/继续` | 继续播放 | `/继续` |
| `/跳过` | 跳过当前歌曲 | `/跳过` |
| `/停止` | 停止播放 | `/停止` |

## 🏗️ 项目结构

```
Kook_Web_Music/
├── windows/                  # Windows 版本
│   ├── app.py               # Flask 应用工厂
│   ├── routes.py            # API 路由
│   ├── config.py            # 环境变量配置
│   ├── run.py               # 启动入口
│   ├── utils.py             # 工具函数
│   ├── .env.example         # 配置模板
│   ├── kookvoice/           # 语音处理模块
│   ├── templates/           # HTML 模板
│   ├── static/              # 前端静态资源
│   │   ├── css/
│   │   └── js/
│   └── ffmpeg/              # FFmpeg 工具（Windows）
├── Ubuntu/                  # Ubuntu 版本
└── README.md
```

## 🔒 安全修复记录

本仓库相比原版修复了以下安全问题：

- 🔴 **Shell 注入**: `kookvoice.py` 中 3 处 `create_subprocess_shell` 改为 `create_subprocess_exec`，所有外部输入使用 `shlex.quote` 转义
- 🔴 **配置损坏**: `config.py` 硬编码全部改为 `os.environ.get()` 读取环境变量
- 🟠 **歌名崩溃**: 冒号 `split` 添加 `maxsplit=3` 防止歌名被拆碎
- 🟠 **缺失依赖**: `requirements.txt` 补充 `aiohttp`

## 🤝 贡献

欢迎提交 Issue 和 Pull Request。

## 📄 许可证

本项目采用 MIT 许可证。
