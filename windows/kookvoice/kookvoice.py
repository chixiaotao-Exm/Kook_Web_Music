import asyncio
import os
import shlex
import threading
import time
import logging
from enum import Enum, unique
from typing import Dict, Union, List, Any, Optional, Coroutine as CoroutineType
from asyncio import AbstractEventLoop
try:
    from .requestor import VoiceRequestor
except ImportError:
    from requestor import VoiceRequestor

# 配置日志
logger = logging.getLogger(__name__)
log_enabled = False

def configure_logging(enabled: bool = True):
    global log_enabled
    log_enabled = enabled
    if enabled:
        logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')
    else:
        logging.disable(logging.CRITICAL)

ffmpeg_bin = os.environ.get('FFMPEG_BIN', 'ffmpeg')

original_loop = None  # 初始化为None，后面会赋值为AbstractEventLoop

def set_ffmpeg(path):
    global ffmpeg_bin
    ffmpeg_bin = path

@unique
class Status(Enum):
    STOP = 0
    WAIT = 1
    SKIP = 2
    END = 3
    START = 4
    PAUSE = 5
    PLAYING = 10
    EMPTY = 11

guild_status = {}
play_list: Dict[str, Dict[str, Any]] = {}
play_list_example = {'服务器id':
                              {'token': '机器人token',
                               'voice_channel': '语音频道id',
                               'text_channel': '最后一次执行指令的文字频道id',
                               'now_playing': {'file': '歌曲文件', 'ss': 0, 'start': 0,'extra':{}},
                               'play_list': [
                                   {'file': '路径', 'ss': 0}]}}

playlist_handle_status = {}

class Player:
    def __init__(self, guild_id, voice_channel_id=None, token=None):
        """
            :param str guild_id: 推流服务器id
            :param str voice_channel_id: 推流语音频道id
            :param str token: 推流机器人token
        """
        self.guild_id = str(guild_id)

        if self.guild_id in play_list:
            if token is None:
                token = play_list[self.guild_id]['token']
            else:
                if token != play_list[self.guild_id]['token']:
                    raise ValueError('播放歌曲过程中无法更换token')
            if voice_channel_id is None:
                voice_channel_id = play_list[self.guild_id]['voice_channel']
            else:
                if voice_channel_id != play_list[self.guild_id]['voice_channel']:
                    raise ValueError('播放歌曲过程中无法更换语音频道')
        self.token = str(token) if token else ""
        self.voice_channel_id = str(voice_channel_id) if voice_channel_id else ""

    def join(self):
        global guild_status
        if not self.voice_channel_id:
            raise ValueError('第一次启动推流时，你需要指定语音频道id')
        if not self.token:
            raise ValueError('第一次启动推流时，你需要指定机器人token')
        if self.guild_id not in play_list:
            play_list[self.guild_id] = {'token': self.token,
                                        'now_playing': None,
                                        'play_list': []}
        guild_status[self.guild_id] = Status.WAIT
        play_list[self.guild_id]['voice_channel'] = self.voice_channel_id
        if log_enabled:
            logger.info(f'加入语音频道: {self.voice_channel_id}，服务器: {self.guild_id}')
        PlayHandler(self.guild_id, self.token).start()

    def add_music(self, music: str, extra_data: dict = {}):
        """
        添加音乐到播放列表
            :param str music: 音乐文件路径或音乐链接
            :param dict extra_data: 可以在这里保存音乐信息
        """
        if not self.voice_channel_id:
            raise ValueError('第一次启动推流时，你需要指定语音频道id')
        if not self.token:
            raise ValueError('第一次启动推流时，你需要指定机器人token')
        need_start = False
        if self.guild_id not in play_list:
            need_start = True
            play_list[self.guild_id] = {'token': self.token,
                                        'now_playing': None,
                                        'play_list': []}
        # 检查是否是歌单歌曲标记，如果是则跳过文件存在检查
        if not music.startswith("PLAYLIST_SONG:"):
            if 'http' not in music:
                if not os.path.exists(music):
                    raise ValueError('文件不存在')

        play_list[self.guild_id]['voice_channel'] = self.voice_channel_id
        play_list[self.guild_id]['play_list'].append({'file': music, 'ss': 0, 'extra': extra_data})
        if log_enabled:
            logger.info(f'添加音乐到播放列表，服务器: {self.guild_id}，音乐: {music}')
        if self.guild_id in guild_status and guild_status[self.guild_id] == Status.WAIT:
            guild_status[self.guild_id] = Status.END
        if need_start:
            if play_list[self.guild_id]['play_list']:
                PlayHandler(self.guild_id, self.token).start()
            elif ((self.guild_id not in playlist_handle_status
                   or (not playlist_handle_status[self.guild_id]))
                  and play_list[self.guild_id]['play_list']):
                PlayHandler(self.guild_id, self.token).start()

    def stop(self):
        global guild_status, playlist_handle_status
        if self.guild_id not in play_list:
            raise ValueError('该服务器没有正在播放的歌曲')
        guild_status[self.guild_id] = Status.STOP
        if log_enabled:
            logger.info(f'停止播放，服务器: {self.guild_id}')

    def skip(self, skip_amount: int = 1):
        '''
        跳过指定数量的歌曲
            :param amount int: 要跳过的歌曲数量,默认为一首
        '''
        global guild_status
        if self.guild_id not in play_list:
            raise ValueError('该服务器没有正在播放的歌曲')
        for i in range(skip_amount - 1):
            try:
                if play_list[self.guild_id]['play_list']:
                    play_list[self.guild_id]['play_list'].pop(0)
            except:
                pass
        guild_status[self.guild_id] = Status.SKIP
        if log_enabled:
            logger.info(f'跳过了 {skip_amount} 首歌曲，服务器: {self.guild_id}')

    def pause(self):
        global guild_status
        if self.guild_id not in play_list:
            raise ValueError('该服务器没有正在播放的歌曲')
        guild_status[self.guild_id] = Status.PAUSE
        if log_enabled:
            logger.info(f'暂停播放，服务器: {self.guild_id}')

    def resume(self):
        global guild_status
        if self.guild_id not in play_list:
            raise ValueError('该服务器没有正在播放的歌曲')
        guild_status[self.guild_id] = Status.PLAYING
        if log_enabled:
            logger.info(f'继续播放，服务器: {self.guild_id}')

    def list(self, json=True):
        if self.guild_id not in play_list:
            raise ValueError('该服务器没有正在播放的歌曲')
        if json:
            result = []
            if play_list[self.guild_id]['now_playing']:
                result.append(play_list[self.guild_id]['now_playing'])
            result.extend(play_list[self.guild_id]['play_list'])
            return result
        else:
            # 懒得写
            return []

    def seek(self, music_seconds: int):
        '''
        跳转至歌曲指定位置
            :param music_seconds int: 所要跳转到歌曲的秒数
        '''
        global play_list
        if self.guild_id not in play_list:
            raise ValueError('该服务器没有正在播放的歌曲')
        if play_list[self.guild_id]['now_playing']:
            now_play = play_list[self.guild_id]['now_playing'].copy()
            now_play['ss'] = int(music_seconds)
            if 'start' in now_play:
                del now_play['start']
            play_list[self.guild_id]['play_list'].insert(0, now_play)
            guild_status[self.guild_id] = Status.SKIP
            if log_enabled:
                logger.info(f'跳转至 {music_seconds} 秒，服务器: {self.guild_id}')


# 事件处理部分

events = {}

class PlayInfo:
    def __init__(self, guild_id, voice_channel_id, file, bot_token, extra_data):
        self.file = file
        self.extra_data = extra_data
        self.guild_id = guild_id
        self.voice_channel_id = voice_channel_id
        self.token = bot_token

def on_event(event):
    global events
    def _on_event_wrapper(func):
        if event not in events:
            events[event] = []
        events[event].append(func)
        return func
    return _on_event_wrapper

async def trigger_event(event, *args, **kwargs):
    if event in events:
        for func in events[event]:
            await func(*args, **kwargs)

class PlayHandler(threading.Thread):
    channel_id: str = None

    def __init__(self, guild_id: str, token: str):
        threading.Thread.__init__(self)
        self.token = token
        self.guild = guild_id
        self.requestor = VoiceRequestor(token)

    def run(self):
        if log_enabled:
            logger.info(f'开始处理，服务器: {self.guild}')
        loop_t = asyncio.new_event_loop()
        asyncio.set_event_loop(loop_t)
        loop_t.run_until_complete(self.main())
        if log_enabled:
            logger.info(f'处理完成，服务器: {self.guild}')

    async def main(self):
        start_event = asyncio.Event()
        task1 = asyncio.create_task(self.push())
        task2 = asyncio.create_task(self.keepalive())
        task3 = asyncio.create_task(self.stop(start_event))

        done, pending = await asyncio.wait(
            [task1, task2],
            return_when=asyncio.FIRST_COMPLETED
        )

        # 可选地取消未完成的任务
        for task in pending:
            task.cancel()

        # 触发 task3 开始
        start_event.set()
        await task3

    async def stop(self, start_event):
        await start_event.wait()
        global playlist_handle_status
        if self.guild in play_list:
            del play_list[self.guild]
        if self.guild in playlist_handle_status and playlist_handle_status[self.guild]:
            playlist_handle_status[self.guild] = False
        try:
            await self.requestor.leave(self.channel_id)
        except:
            pass
        if log_enabled:
            logger.info(f'停止并清理，服务器: {self.guild}')

    async def push(self):
        global playlist_handle_status
        playlist_handle_status[self.guild] = True
        try:
            await asyncio.sleep(1)
            if self.guild in play_list and 'voice_channel' in play_list[self.guild]:
                new_channel = play_list[self.guild]['voice_channel']
                self.channel_id = new_channel

                try:
                    await self.requestor.leave(self.channel_id)
                except:
                    pass
                try:
                    res = await self.requestor.join(self.channel_id)
                except Exception as e:
                    if log_enabled:
                        logger.error(f'加入频道失败: {e}')
                    raise RuntimeError(f'加入频道失败 {e}')

                rtp_url = f"rtp://{res['ip']}:{res['port']}?rtcpport={res['rtcp_port']}"
                if log_enabled:
                    try:
                        logger.info(f"RTP配置: {res}")
                    except Exception:
                        pass

                audio_ssrc = res.get('audio_ssrc', 1111)
                audio_pt = res.get('audio_pt', 111)

                bitrate = int(res['bitrate'] / 1000)
                bitrate *= 0.9 if bitrate > 100 else 1

                while self.guild in guild_status and guild_status[self.guild] == Status.WAIT:
                    await asyncio.sleep(2)

                rtp_url = c[self.rtp_url_index] if self.rtp_url_index < len(c) else c[0]
                enc_args = [
                    ffmpeg_bin, "-re", "-loglevel", "level+info", "-nostats",
                    "-f", "wav", "-i", "-",
                    "-map", "0:a:0",
                    "-acodec", "libopus", "-ab", f"{bitrate}k",
                    "-ac", "2", "-ar", "48000",
                    "-filter:a", "volume=1.0",
                    "-f", "tee",
                    f"[select=a:f=rtp:ssrc={audio_ssrc}:payload_type={audio_pt}]{rtp_url}",
                ]
                if log_enabled:
                    logger.info(f'运行 ffmpeg 命令: {" ".join(enc_args)}')
                p = await asyncio.create_subprocess_exec(
                    *enc_args,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE
                )

                while True:
                    await asyncio.sleep(0.5)
                    if self.guild in play_list:
                        if play_list[self.guild]['now_playing'] and not play_list[self.guild]['play_list']:
                            music_info = play_list[self.guild]['now_playing']
                        else:
                            if play_list[self.guild]['play_list']:
                                music_info = play_list[self.guild]['play_list'].pop(0)
                                music_info['start'] = time.time()
                                play_list[self.guild]['now_playing'] = music_info
                            else:
                                break
                        
                        if isinstance(music_info, dict) and 'file' in music_info:
                            file = music_info['file']

                            # 检查是否是歌单歌曲标记，如果是则实时获取URL
                            if file.startswith("PLAYLIST_SONG:"):
                                try:
                                    # 解析歌单歌曲标记 — 使用 maxsplit=3 防止歌名含冒号导致解析错误
                                    parts = file.split(":", 3)
                                    if len(parts) >= 4:
                                        song_id = parts[1]
                                        song_name = parts[2]
                                        artist_name = parts[3]
                                        
                                        if log_enabled:
                                            logger.info(f'🎵 实时获取歌单歌曲URL: {song_name} - {artist_name}')
                                        
                                        # 实时获取歌曲URL
                                        import requests
                                        # 尝试加载主程序的构建请求头（含Cookie）
                                        try:
                                            from ..utils import build_headers as _kv_build_headers
                                        except Exception:
                                            def _kv_build_headers(extra: dict | None = None):
                                                headers = {
                                                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127 Safari/537.36",
                                                }
                                                try:
                                                    import os
                                                    cookie_path = os.path.join(os.path.dirname(__file__), "..", "Cookie", "cookie.txt")
                                                    cookie_path = os.path.abspath(cookie_path)
                                                    if os.path.exists(cookie_path):
                                                        with open(cookie_path, "r", encoding="utf-8") as f:
                                                            cookie_str = f.read().strip()
                                                            if cookie_str:
                                                                headers["Cookie"] = cookie_str
                                                except Exception:
                                                    pass
                                                if extra:
                                                    headers.update(extra)
                                                return headers
                                        try:
                                            from ..config import MUSIC_API_BASE
                                        except ImportError:
                                            from config import MUSIC_API_BASE
                                        
                                        url_api = f"{MUSIC_API_BASE}/song/url?id={song_id}"
                                        url_res = requests.get(url_api, timeout=15, headers=_kv_build_headers())
                                        
                                        if url_res.status_code == 200:
                                            url_data = url_res.json()
                                            if url_data.get('data') and url_data['data'][0].get('url'):
                                                file = url_data['data'][0]['url']
                                                if log_enabled:
                                                    logger.info(f'✅ 实时获取到URL: {song_name} - {artist_name}')
                                            else:
                                                if log_enabled:
                                                    logger.warning(f'❌ 无法获取播放链接: {song_name} - {artist_name}')
                                                continue  # 跳过这首歌
                                        else:
                                            if log_enabled:
                                                logger.error(f'❌ 获取URL失败: {song_name} - {artist_name}')
                                            continue  # 跳过这首歌
                                except Exception as e:
                                    if log_enabled:
                                        logger.error(f'❌ 实时获取URL异常: {e}')
                                    continue  # 跳过这首歌

                            extra_command = ''
                            if 'extra' in music_info and music_info['extra']:
                                extra_data = music_info['extra']

                                def pack_command_safe(full_command: str, name: str, value: str | None) -> str:
                                    """安全地拼接 ffmpeg 参数，防止 Shell 注入"""
                                    if value and isinstance(value, str) and value.strip():
                                        return f'{full_command} -{name} {shlex.quote(value)}'
                                    return full_command

                                if isinstance(extra_data, dict):
                                    extra_command = pack_command_safe(extra_command, 'headers', extra_data.get('header'))
                                    extra_command = pack_command_safe(extra_command, 'cookies', extra_data.get('cookies'))
                                    extra_command = pack_command_safe(extra_command, 'user_agent', extra_data.get('user_agent'))
                                    extra_command = pack_command_safe(extra_command, 'referer', extra_data.get('referer'))

                            ss_value = music_info.get('ss', 0)
                            
                            # 获取音频时长
                            if log_enabled:
                                logger.info(f'获取音频时长: {file}')
                            
                            audio_duration = 0
                            try:
                                # 使用ffprobe获取音频时长 — 安全参数传递
                                try:
                                    from ..config import FFPROBE_PATH
                                except ImportError:
                                    from config import FFPROBE_PATH
                                duration_args = [
                                    FFPROBE_PATH, "-v", "quiet",
                                    "-show_entries", "format=duration",
                                    "-of", "csv=p=0", file,
                                ]
                                
                                if log_enabled:
                                    logger.info(f'执行时长获取命令: {" ".join(duration_args)}')
                                
                                duration_process = await asyncio.create_subprocess_exec(
                                    *duration_args,
                                    stdout=asyncio.subprocess.PIPE,
                                    stderr=asyncio.subprocess.PIPE
                                )
                                stdout, stderr = await duration_process.communicate()
                                
                                if stdout:
                                    duration_text = stdout.decode('utf-8', errors='ignore').strip()
                                    if duration_text and duration_text != 'N/A':
                                        try:
                                            audio_duration = float(duration_text)
                                            if log_enabled:
                                                logger.info(f'音频时长: {audio_duration:.2f} 秒')
                                        except ValueError:
                                            if log_enabled:
                                                logger.warning(f'无法解析音频时长: {duration_text}')
                                    else:
                                        if log_enabled:
                                            logger.warning(f'ffprobe返回空时长: {duration_text}')
                                else:
                                    if log_enabled:
                                        logger.warning(f'ffprobe无输出，尝试备用方法')
                                    
                                    # 备用方法：使用 ffmpeg 获取时长（安全 exec 方式）
                                    backup_args = [
                                        ffmpeg_bin, "-i", file,
                                        "-f", "null", "-",
                                    ]
                                    backup_process = await asyncio.create_subprocess_exec(
                                        *backup_args,
                                        stdout=asyncio.subprocess.PIPE,
                                        stderr=asyncio.subprocess.PIPE
                                    )
                                    _, stderr = await backup_process.communicate()
                                    stderr_text = stderr.decode('utf-8', errors='ignore')
                                    
                                    # 解析音频时长
                                    import re
                                    duration_match = re.search(r'Duration: (\d{2}):(\d{2}):(\d{2})\.(\d{2})', stderr_text)
                                    if duration_match:
                                        hours = int(duration_match.group(1))
                                        minutes = int(duration_match.group(2))
                                        seconds = int(duration_match.group(3))
                                        centiseconds = int(duration_match.group(4))
                                        audio_duration = hours * 3600 + minutes * 60 + seconds + centiseconds / 100
                                        if log_enabled:
                                            logger.info(f'备用方法获取音频时长: {audio_duration:.2f} 秒')
                                    else:
                                        if log_enabled:
                                            logger.warning(f'备用方法也无法获取音频时长')
                                            
                            except Exception as e:
                                if log_enabled:
                                    logger.error(f'获取音频时长失败: {e}')
                                audio_duration = 0
                            
                            expected_duration = audio_duration
                            
                            # 如果无法获取音频时长，设置默认时长（3分钟）
                            if expected_duration <= 0:
                                expected_duration = 180.0  # 3分钟
                                if log_enabled:
                                    logger.info(f'使用默认音频时长: {expected_duration:.2f} 秒')
                            
                            # 将预期时长写入当前播放信息，供前端显示总时长
                            try:
                                if self.guild in play_list and play_list[self.guild]['now_playing']:
                                    play_list[self.guild]['now_playing']['duration'] = float(expected_duration)
                            except Exception:
                                pass

                            if log_enabled:
                                logger.info(f'正在播放文件: {file}')
                            # 解析 extra_command 为安全参数列表
                            extra_args = shlex.split(extra_command) if extra_command else []
                            decode_args = [
                                ffmpeg_bin,
                                "-nostats",
                                "-reconnect", "1",
                                "-reconnect_streamed", "1",
                                "-reconnect_delay_max", "2",
                                "-timeout", "30000000",
                                "-ss", str(ss_value),
                                "-i", file,
                                *extra_args,
                                "-filter:a", "volume=0.4",
                                "-acodec", "pcm_s16le",
                                "-ac", "2",
                                "-ar", "48000",
                                "-f", "wav",
                                "-y", "-",
                            ]
                            p2 = await asyncio.create_subprocess_exec(
                                *decode_args,
                                stdin=asyncio.subprocess.DEVNULL,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE
                            )

                            # 音频播放逻辑 - 解码到编码管道
                            if log_enabled:
                                logger.info(f'开始播放音频，预期时长: {expected_duration:.2f} 秒')

                            # 记录播放开始时间
                            first_music_start_time = time.time()

                            # 设置播放状态
                            if self.guild not in guild_status:
                                guild_status[self.guild] = Status.END

                            if guild_status[self.guild] == Status.END:
                                if original_loop:
                                    asyncio.run_coroutine_threadsafe(
                                        trigger_event(
                                            Status.START,
                                            PlayInfo(self.guild, self.channel_id, file, self.token, music_info.get('extra'))
                                        ),
                                        original_loop
                                    )
                                if log_enabled:
                                    logger.info(f'开始播放: {file}，服务器: {self.guild}')
                                guild_status[self.guild] = Status.PLAYING

                            chunk_size = 96000
                            total_audio = b''
                            last_write_time = 0.0
                            consecutive_empty_reads = 0
                            max_empty_reads = 10  # 最大连续空读取次数

                            try:
                                skip_song = False
                                while True:
                                    if p2 and p2.stdout:
                                        try:
                                            # 使用超时读取，避免无限阻塞
                                            new_audio = await asyncio.wait_for(
                                                p2.stdout.read(chunk_size), 
                                                timeout=2.0
                                            )
                                        except asyncio.TimeoutError:
                                            # 读取超时，检查进程状态
                                            if p2.poll() is not None:
                                                # 进程已退出
                                                if log_enabled:
                                                    logger.warning(f'解码进程已退出: {file}')
                                                break
                                            # 进程仍在运行，继续尝试读取
                                            consecutive_empty_reads += 1
                                            if consecutive_empty_reads >= max_empty_reads:
                                                if log_enabled:
                                                    logger.warning(f'连续{max_empty_reads}次读取超时，可能网络问题: {file}')
                                                break
                                            continue

                                        if not new_audio:
                                            consecutive_empty_reads += 1
                                            if consecutive_empty_reads >= max_empty_reads:
                                                # 打印解码器stderr，帮助定位
                                                if p2.stderr:
                                                    try:
                                                        err_text = (await p2.stderr.read()).decode('utf-8', errors='ignore').strip()
                                                        if err_text and log_enabled:
                                                            logger.warning(f'解码进程stderr: {err_text[:500]}')
                                                    except Exception:
                                                        pass

                                                # 写入剩余缓存
                                                if total_audio and p and p.stdin:
                                                    try:
                                                        p.stdin.write(total_audio)
                                                        await p.stdin.drain()
                                                        if log_enabled:
                                                            logger.info(f'写入剩余音频数据: {len(total_audio)} 字节')
                                                    except Exception as e:
                                                        if log_enabled:
                                                            logger.error(f'写入剩余音频数据异常: {e}')

                                                # 若播放时长不足，继续等待凑够最小时长
                                                actual_duration = max(0.0, time.time() - first_music_start_time)
                                                min_play_time = 30.0
                                                target_duration = max(expected_duration, min_play_time)
                                                if actual_duration < target_duration:
                                                    wait_sec = target_duration - actual_duration
                                                    if log_enabled:
                                                        logger.info(f'等待剩余时间: {wait_sec:.2f} 秒 (目标时长: {target_duration:.2f} 秒)')
                                                    await asyncio.sleep(wait_sec)

                                                if log_enabled:
                                                    logger.info(f'音频播放完成: {file}')
                                                break
                                        else:
                                            # 重置连续空读取计数
                                            consecutive_empty_reads = 0

                                        total_audio += new_audio

                                        # 成块写入编码器stdin
                                        while len(total_audio) >= chunk_size:
                                            audio_slice = total_audio[:chunk_size]
                                            total_audio = total_audio[chunk_size:]
                                            if p and p.stdin:
                                                try:
                                                    now = time.time()
                                                    if last_write_time > 0:
                                                        elapsed = now - last_write_time
                                                        if elapsed < 0.02:
                                                            await asyncio.sleep(0.02 - elapsed)
                                                    # 暂停控制：当状态为 PAUSE 时，阻塞写入，直到恢复
                                                    if self.guild in guild_status and guild_status[self.guild] == Status.PAUSE:
                                                        while self.guild in guild_status and guild_status[self.guild] == Status.PAUSE:
                                                            await asyncio.sleep(0.1)
                                                    p.stdin.write(audio_slice)
                                                    await p.stdin.drain()
                                                    last_write_time = time.time()

                                                    # 更新前端显示进度
                                                    if self.guild in play_list and play_list[self.guild]['now_playing']:
                                                        play_list[self.guild]['now_playing']['ss'] = last_write_time - first_music_start_time

                                                    # 中断控制
                                                    if self.guild in guild_status:
                                                        state = guild_status[self.guild]
                                                        if state == Status.SKIP:
                                                            if log_enabled:
                                                                logger.info(f'跳过当前歌曲: {file}')
                                                            # 重置状态并标记跳过当前歌曲，不退出整个推流
                                                            try:
                                                                guild_status[self.guild] = Status.END
                                                            except Exception:
                                                                pass
                                                            skip_song = True
                                                            try:
                                                                if p2:
                                                                    p2.kill()
                                                            except Exception:
                                                                pass
                                                            break
                                                        if state == Status.STOP:
                                                            if log_enabled:
                                                                logger.info(f'停止播放: {file}')
                                                            if self.guild in play_list:
                                                                play_list[self.guild]['play_list'] = []
                                                            return
                                                except Exception as e:
                                                    if log_enabled:
                                                        logger.error(f'音频写入异常: {e}')
                                                    break
                                        # 若标记跳过，结束本曲读循环
                                        if skip_song:
                                            break
                                    else:
                                        if log_enabled:
                                            logger.error(f'音频进程异常: {file}')
                                        break
                            except Exception as e:
                                if log_enabled:
                                    logger.error(f'音频播放异常: {e}')
                            
                            # 播放完成后清理
                            if log_enabled:
                                logger.info(f'歌曲播放完成: {file}')
                            
                            # 清理当前播放状态
                            if self.guild in play_list and play_list[self.guild]['now_playing']:
                                play_list[self.guild]['now_playing'] = None
                            
                            # 检查是否还有更多歌曲
                            if self.guild in play_list and len(play_list[self.guild]['play_list']) == 0:
                                try:
                                    if p:
                                        p.kill()
                                    if p2:
                                        p2.kill()
                                except Exception as e:
                                    if log_enabled:
                                        logger.error(f'关闭FFMPEG进程异常: {e}')
                                if self.guild in playlist_handle_status:
                                    playlist_handle_status[self.guild] = False
                                if log_enabled:
                                    logger.info(f'播放列表结束，服务器: {self.guild}')
                            else:
                                # 还有更多歌曲，继续播放下一首
                                if log_enabled:
                                    logger.info(f'准备播放下一首歌曲，服务器: {self.guild}')
                    else:
                        break
        except Exception as e:
            if log_enabled:
                logger.error(f'推流过程中出现错误: {str(e)}', exc_info=True)

    async def keepalive(self):
        while True:
            await asyncio.sleep(45)
            if self.channel_id:
                await self.requestor.keep_alive(self.channel_id)
                if log_enabled:
                    logger.info(f'发送保活请求，频道: {self.channel_id}')

async def start():
    global original_loop
    original_loop = asyncio.get_event_loop()
    while True:
        await asyncio.sleep(1000)

from typing import Coroutine, TypeVar, Any
T = TypeVar('T')

async def run_async(task: CoroutineType[Any, Any, T], timeout=10) -> T:
    if original_loop:
        return asyncio.run_coroutine_threadsafe(task, original_loop).result(timeout=timeout)
    return None

def run():
    asyncio.run(start())