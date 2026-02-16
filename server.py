"""
LiveSTT - YouTube 실시간 자막 서버

YouTube 라이브/일반 영상 → yt-dlp + ffmpeg → Whisper AI → WebSocket 자막

실행: pip install aiohttp yt-dlp faster-whisper && python server.py
"""

import asyncio
import json
import os
import sys
import struct
import subprocess
import tempfile
import time
from datetime import datetime

import aiohttp
from aiohttp import web

# Whisper 모델 (서버 시작 시 1회 로드)
whisper_model = None

# 뷰어 WebSocket 목록
viewers = set()

# 최근 자막 (뷰어 늦게 접속해도 이전 내용 표시)
recent_lines = []
MAX_RECENT = 500

# 현재 인식 작업
current_task = None
is_running = False


def load_whisper():
    """Whisper 모델 로드"""
    global whisper_model
    from faster_whisper import WhisperModel
    print('[Whisper] small 모델 로딩 중 (언어 감지 정확도 향상)...')
    whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
    print('[Whisper] 로딩 완료!')


def transcribe_chunk(audio_path):
    """오디오 파일 하나를 Whisper로 인식"""
    segments, info = whisper_model.transcribe(
        audio_path,
        language=None,       # 자동 언어 감지
        vad_filter=True,     # 침묵 구간 제거
        beam_size=5,
    )
    results = []
    for seg in segments:
        text = seg.text.strip()
        if text:
            lang = 'ko' if info.language == 'ko' else 'en'
            results.append((text, seg.start, seg.end, lang))
    return results


def get_stream_info(youtube_url):
    """yt-dlp로 YouTube 오디오 스트림 URL + 메타 정보 추출"""
    import yt_dlp
    with yt_dlp.YoutubeDL({'format': 'bestaudio/best', 'quiet': True, 'no_warnings': True}) as ydl:
        info = ydl.extract_info(youtube_url, download=False)

        audio_url = info.get('url')
        if not audio_url:
            for f in reversed(info.get('formats', [])):
                if f.get('acodec') != 'none':
                    audio_url = f['url']
                    break

        return {
            'url': audio_url,
            'title': info.get('title', 'Unknown'),
            'is_live': info.get('is_live', False),
            'duration': info.get('duration'),
        }


def start_ffmpeg(audio_url):
    """ffmpeg: 오디오 스트림 → 16kHz mono PCM WAV (stdout 파이프)"""
    cmd = [
        'ffmpeg', '-i', audio_url,
        '-f', 'wav', '-acodec', 'pcm_s16le',
        '-ar', '16000', '-ac', '1',
        '-loglevel', 'error',
        'pipe:1',
    ]
    kwargs = {}
    if sys.platform == 'win32':
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs['startupinfo'] = si

    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)


def write_wav(path, pcm, sr=16000):
    """raw PCM → WAV 파일 저장"""
    with open(path, 'wb') as f:
        f.write(b'RIFF')
        f.write(struct.pack('<I', 36 + len(pcm)))
        f.write(b'WAVEfmt ')
        f.write(struct.pack('<IHHIIHH', 16, 1, 1, sr, sr * 2, 2, 16))
        f.write(b'data')
        f.write(struct.pack('<I', len(pcm)))
        f.write(pcm)


def convert_audio_to_wav(input_path, output_path):
    """webm/opus 등 브라우저 오디오 → 16kHz mono WAV 변환 (탭 오디오용)"""
    cmd = [
        'ffmpeg', '-y', '-i', input_path,
        '-f', 'wav', '-acodec', 'pcm_s16le',
        '-ar', '16000', '-ac', '1',
        '-loglevel', 'error',
        output_path,
    ]
    kwargs = {}
    if sys.platform == 'win32':
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs['startupinfo'] = si
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30, **kwargs)
        return result.returncode == 0
    except Exception:
        return False


# ========================================
# WebSocket 브로드캐스트
# ========================================

async def broadcast(data):
    """모든 뷰어에게 JSON 전송"""
    msg = json.dumps(data, ensure_ascii=False)
    if data.get('type') == 'final':
        recent_lines.append(msg)
        if len(recent_lines) > MAX_RECENT:
            recent_lines.pop(0)

    for v in list(viewers):
        try:
            await v.send_str(msg)
        except Exception:
            viewers.discard(v)


async def send_status(text):
    await broadcast({
        'type': 'final', 'text': text,
        'time': datetime.now().strftime('%H:%M:%S'), 'lang': 'ko',
    })


async def translate_to_korean(text):
    """비한국어 텍스트 → 한국어 번역 (Ollama)"""
    payload = {
        'model': 'gemma3:4b',
        'prompt': f'다음 텍스트를 한국어로 번역하세요. 번역문만 출력하세요.\n\n{text}',
        'stream': False,
    }
    timeout = aiohttp.ClientTimeout(total=15)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post('http://localhost:11434/api/generate', json=payload) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return str(data.get('response', '')).strip() or None
    except Exception:
        return None


# ========================================
# 핵심: 인식 루프
# ========================================

async def recognition_loop(youtube_url):
    """
    YouTube → ffmpeg(실시간 PCM) → 10초 chunk → Whisper → 뷰어 전송

    라이브/VOD 모두 동일 흐름.
    """
    global is_running
    is_running = True
    proc = None
    chunk_path = os.path.join(tempfile.gettempdir(), 'livesst_chunk.wav')

    try:
        await send_status('🔍 YouTube 정보 가져오는 중...')
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, get_stream_info, youtube_url)

        if not info['url']:
            await send_status('❌ 오디오 스트림을 찾을 수 없습니다')
            return

        mode = '🔴 라이브' if info['is_live'] else '🎬 영상'
        await send_status(f'{mode}: {info["title"]}')
        await send_status('🎤 음성 인식 시작...')

        # ffmpeg 시작
        proc = await loop.run_in_executor(None, start_ffmpeg, info['url'])

        # WAV 헤더 스킵 (44바이트)
        header = await loop.run_in_executor(None, proc.stdout.read, 44)
        if len(header) < 44:
            await send_status('❌ 오디오 스트림 읽기 실패')
            return

        # 10초 단위 chunk 크기 (16kHz, 16bit, mono)
        chunk_bytes = 16000 * 2 * 10
        elapsed = 0.0

        while is_running:
            raw = await loop.run_in_executor(None, proc.stdout.read, chunk_bytes)
            if not raw or len(raw) < 3200:
                break

            write_wav(chunk_path, raw)
            results = await loop.run_in_executor(None, transcribe_chunk, chunk_path)

            for text, start, end, lang in results:
                t = elapsed + start
                time_str = f'{int(t // 60):02d}:{int(t % 60):02d}'
                msg = {
                    'type': 'final', 'text': text,
                    'time': time_str, 'lang': lang,
                    'ts': int(time.time() * 1000),
                }
                if lang != 'ko':
                    translated = await translate_to_korean(text)
                    if translated:
                        msg['translated'] = translated
                await broadcast(msg)

            elapsed += len(raw) / (16000 * 2)

        if is_running:
            await send_status('✅ 인식 완료!')

    except asyncio.CancelledError:
        await send_status('⏹ 인식 중단됨')
    except Exception as e:
        await send_status(f'❌ 오류: {e}')
        print(f'[오류] {e}', flush=True)
    finally:
        is_running = False
        if proc:
            try:
                proc.kill()
                proc.wait(timeout=3)
            except Exception:
                pass
        if os.path.exists(chunk_path):
            try:
                os.remove(chunk_path)
            except Exception:
                pass


# ========================================
# HTTP / WebSocket 핸들러
# ========================================

async def api_start(request):
    """YouTube URL 받아서 인식 시작"""
    global current_task, is_running
    data = await request.json()
    url = data.get('url', '').strip()
    if not url:
        return web.json_response({'error': 'URL 필요'}, status=400)

    if current_task and not current_task.done():
        is_running = False
        current_task.cancel()
        try:
            await current_task
        except Exception:
            pass

    current_task = asyncio.create_task(recognition_loop(url))
    return web.json_response({'status': 'started'})


async def api_stop(request):
    """인식 중단"""
    global is_running, current_task
    is_running = False
    if current_task and not current_task.done():
        current_task.cancel()
        try:
            await current_task
        except Exception:
            pass
    return web.json_response({'status': 'stopped'})


async def api_status(request):
    return web.json_response({
        'running': is_running,
        'viewers': len(viewers),
        'lines': len(recent_lines),
    })


async def generate_summary_with_ollama(lines):
    text = '\n'.join(str(line).strip() for line in lines if str(line).strip())
    if not text:
        raise ValueError('요약할 텍스트가 없습니다')

    prompt = (
        '다음은 실시간으로 인식된 음성 자막입니다. 이 내용을 미팅 요약 형식으로 정리해주세요.\n\n'
        '요약 형식:\n'
        '## 주요 주제\n'
        '- 논의된 핵심 주제들\n\n'
        '## 핵심 내용\n'
        '- 중요한 발언이나 결정 사항들\n\n'
        '## 액션 아이템\n'
        '- 해야 할 일이나 후속 조치\n\n'
        f'자막 내용:\n{text}'
    )

    payload = {
        'model': 'gemma3:4b',
        'prompt': prompt,
        'stream': False,
    }

    timeout = aiohttp.ClientTimeout(total=90)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            async with session.post('http://localhost:11434/api/generate', json=payload) as resp:
                if resp.status != 200:
                    detail = await resp.text()
                    raise RuntimeError(f'Ollama 호출 실패 ({resp.status}): {detail}')

                data = await resp.json()
                summary = str(data.get('response', '')).strip()
                if not summary:
                    raise RuntimeError('Ollama 응답에 summary가 비어 있습니다')
                return summary
        except aiohttp.ClientConnectionError as e:
            raise RuntimeError('Ollama 서버에 연결할 수 없습니다. Ollama 실행 상태를 확인해주세요') from e
        except asyncio.TimeoutError as e:
            raise RuntimeError('Ollama 응답 시간이 초과되었습니다') from e
        except aiohttp.ContentTypeError as e:
            raise RuntimeError('Ollama 응답 형식이 올바르지 않습니다') from e


async def api_summary(request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({'error': '잘못된 JSON 요청입니다'}, status=400)

    lines = data.get('lines')
    if not isinstance(lines, list):
        return web.json_response({'error': 'lines 배열이 필요합니다'}, status=400)

    try:
        summary = await generate_summary_with_ollama(lines)
        return web.json_response({'summary': summary})
    except ValueError as e:
        return web.json_response({'error': str(e)}, status=400)
    except RuntimeError as e:
        return web.json_response({'error': str(e)}, status=503)
    except Exception as e:
        return web.json_response({'error': f'요약 생성 중 알 수 없는 오류: {e}'}, status=500)


async def ws_handler(request):
    role = request.query.get('role', 'viewer').strip().lower()
    if role not in {'viewer', 'sender', 'audio_sender'}:
        return web.json_response({'error': 'role must be viewer, sender, or audio_sender'}, status=400)

    ws_resp = web.WebSocketResponse(max_msg_size=10 * 1024 * 1024)
    await ws_resp.prepare(request)

    if role == 'viewer':
        viewers.add(ws_resp)
        print(f'[뷰어 +] {len(viewers)}명', flush=True)
        for line in recent_lines:
            try:
                await ws_resp.send_str(line)
            except Exception:
                break

    elif role == 'audio_sender':
        print('[오디오 발신자 +] 탭 오디오 + 마이크 스테레오 믹스', flush=True)
        ws_id = id(ws_resp)
        webm_path = os.path.join(tempfile.gettempdir(), f'livesst_audio_{ws_id}.webm')
        wav_path = os.path.join(tempfile.gettempdir(), f'livesst_audio_{ws_id}.wav')

        try:
            async for msg in ws_resp:
                if msg.type == web.WSMsgType.BINARY:
                    with open(webm_path, 'wb') as f:
                        f.write(msg.data)

                    loop = asyncio.get_event_loop()
                    ok = await loop.run_in_executor(None, convert_audio_to_wav, webm_path, wav_path)
                    if not ok:
                        print('[오디오] ffmpeg 변환 실패, 건너뜀', flush=True)
                        continue

                    results = await loop.run_in_executor(None, transcribe_chunk, wav_path)
                    for text, start, end, lang in results:
                        msg = {
                            'type': 'final',
                            'text': text,
                            'time': datetime.now().strftime('%H:%M:%S'),
                            'lang': lang,
                            'ts': int(time.time() * 1000),
                        }
                        if lang != 'ko':
                            translated = await translate_to_korean(text)
                            if translated:
                                msg['translated'] = translated
                        await broadcast(msg)
                elif msg.type in (web.WSMsgType.ERROR, web.WSMsgType.CLOSE):
                    break
        finally:
            for p in (webm_path, wav_path):
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass
            print('[오디오 발신자 -] 연결 종료', flush=True)
        return ws_resp

    else:
        print('[발신자 +] 연결됨', flush=True)

    try:
        async for msg in ws_resp:
            if msg.type == web.WSMsgType.TEXT and role == 'sender':
                try:
                    data = json.loads(msg.data)
                except json.JSONDecodeError:
                    await ws_resp.send_json({'error': 'invalid json'})
                    continue

                msg_type = data.get('type')
                text = str(data.get('text', '')).strip()
                time_text = str(data.get('time', '')).strip()
                lang = str(data.get('lang', 'ko')).strip().lower()

                if msg_type not in {'final', 'interim'}:
                    await ws_resp.send_json({'error': 'type must be final or interim'})
                    continue
                if not text:
                    continue
                if not time_text:
                    time_text = datetime.now().strftime('%H:%M:%S')
                if lang not in {'ko', 'en'}:
                    lang = 'ko'

                bc_msg = {
                    'type': msg_type,
                    'text': text,
                    'time': time_text,
                    'lang': lang,
                    'ts': int(time.time() * 1000),
                }
                if lang != 'ko' and msg_type == 'final':
                    translated = await translate_to_korean(text)
                    if translated:
                        bc_msg['translated'] = translated
                await broadcast(bc_msg)
            elif msg.type in (web.WSMsgType.ERROR, web.WSMsgType.CLOSE):
                break
    finally:
        if role == 'viewer':
            viewers.discard(ws_resp)
            print(f'[뷰어 -] {len(viewers)}명', flush=True)
        else:
            print('[발신자 -] 연결 종료', flush=True)
    return ws_resp


async def static_handler(request):
    base = os.path.dirname(os.path.abspath(__file__))
    path = request.match_info.get('path', '') or 'index.html'
    fp = os.path.join(base, path)
    if os.path.isfile(fp):
        return web.FileResponse(fp)
    return web.Response(status=404, text='Not Found')


def create_app():
    app = web.Application()
    app.router.add_post('/api/start', api_start)
    app.router.add_post('/api/stop', api_stop)
    app.router.add_get('/api/status', api_status)
    app.router.add_post('/api/summary', api_summary)
    app.router.add_get('/ws', ws_handler)
    app.router.add_get('/', static_handler)
    app.router.add_get('/{path:.*}', static_handler)
    return app


if __name__ == '__main__':
    PORT = 8765
    print('=' * 60)
    print('  LiveSTT - YouTube 실시간 자막 서버')
    print('=' * 60)
    print(f'  입력:  http://localhost:{PORT}')
    print(f'  뷰어:  http://localhost:{PORT}/viewer.html')
    print('=' * 60)
    print()

    load_whisper()

    print()
    print(f'✅ 준비 완료! http://localhost:{PORT}')
    print()

    app = create_app()
    web.run_app(app, host='0.0.0.0', port=PORT, print=None)
