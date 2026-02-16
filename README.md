# LiveSTT - 실시간 음성 자막 + 미팅 요약

YouTube 라이브, Zoom, Google Meet 등의 음성을 실시간으로 텍스트로 변환하고, 별도 브라우저 탭에서 자막을 확인할 수 있는 웹앱입니다.

## ✨ 주요 기능

| 기능 | 설명 |
|------|------|
| 📺 YouTube 모드 | YouTube URL 입력 → 서버가 직접 오디오 추출 + Whisper AI 인식 |
| 🖥️ 탭 오디오 모드 | 브라우저 탭 오디오 + 마이크 스테레오 믹스 → Whisper AI 인식 |
| 📡 실시간 뷰어 | 별도 탭/기기에서 자막을 실시간으로 확인 |
| 🌐 자동 번역 | 비한국어 음성 → 한국어 자동 번역 (Ollama) |
| 📊 미팅 요약 | 주요 주제, 핵심 내용, 액션 아이템 형식으로 요약 (Ollama) |

## 📋 사전 준비

### 공통 (Windows / Mac)

1. **Python 3.10+**
2. **ffmpeg** — 오디오 변환에 필요
3. **Ollama** — 번역 + 미팅 요약에 필요 (선택, 없어도 자막은 동작)

### ffmpeg 설치

**Mac:**
```bash
brew install ffmpeg
```

**Windows:**
```bash
# winget (권장)
winget install ffmpeg

# 또는 https://ffmpeg.org/download.html 에서 다운로드 후 PATH에 추가
```

### Ollama 설치 (번역 + 요약 기능)

> Ollama가 없으면 자막 인식은 정상 동작하지만, 번역과 요약 기능은 사용할 수 없습니다.

**Mac:**
```bash
brew install ollama
```

**Windows:**
- https://ollama.com/download 에서 설치

**모델 다운로드 (공통):**
```bash
ollama pull gemma3:4b
```

## 🚀 설치 & 실행

### 1. 다운로드

👉 **[ZIP 다운로드](https://github.com/m2nh0926/livetts/archive/refs/heads/main.zip)**

다운로드 후 압축을 풀어주세요. (git을 아신다면 `git clone`도 가능합니다)

### 2. 실행

**Windows:** 압축 푼 폴더에서 `start.bat` 더블클릭
**Mac:** 터미널에서 압축 푼 폴더로 이동 후 `./start.sh`

> 스크립트가 Python, ffmpeg, Ollama 설치 여부를 자동 확인하고, 미설치 항목을 자동 설치합니다.
> Ollama 모델 다운로드, 서버 실행, 브라우저 오픈까지 전부 자동.

### 수동 실행

```bash
# 1. 저장소 클론
git clone https://github.com/m2nh0926/livetts.git
cd livetts

# 2. Python 가상환경 (권장)
python -m venv venv

# Mac/Linux
source venv/bin/activate

# Windows
venv\Scripts\activate

# 3. 의존성 설치
pip install -r requirements.txt

# 4. Ollama 실행 (번역/요약을 쓰려면 별도 터미널에서)
ollama serve

# 5. 서버 실행
python server.py
```

> ⚠️ **첫 실행 시 Whisper small 모델을 자동 다운로드합니다** (~500MB, 1~2분 소요).
> 이후 실행에서는 캐시된 모델을 사용합니다.

## 💻 사용법

서버 실행 후 브라우저에서:

| 페이지 | URL | 용도 |
|--------|-----|------|
| 입력/제어 | http://localhost:8765 | YouTube URL 입력 또는 탭 오디오 공유 시작 |
| 자막 뷰어 | http://localhost:8765/viewer.html | 실시간 자막 확인 (별도 탭/기기) |

### YouTube 모드
1. 📺 YouTube 탭 선택
2. YouTube 영상/라이브 URL 붙여넣기
3. ▶ 인식 시작 클릭

### 탭 오디오 모드 (Zoom, Google Meet 등)
1. 🖥️ 탭 오디오 공유 탭 선택
2. "탭 오디오 공유 시작" 클릭
3. 공유 팝업에서 Zoom/Meet이 열린 탭을 선택
4. ⚠️ **"탭 오디오도 공유" 체크 필수!**
5. 마이크 권한도 허용하면 내 음성도 함께 인식 (스테레오 믹스)

### 자막 뷰어
- 같은 네트워크의 다른 기기에서도 `http://{서버IP}:8765/viewer.html`로 접속 가능
- 글자 크기, 시간 표시, 자동 스크롤, 전체화면 설정 제공
- 📊 요약 버튼으로 미팅 요약 생성

## 🔧 기술 스택

- **서버**: Python + aiohttp (비동기 WebSocket)
- **음성 인식**: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (small 모델, CPU int8)
- **YouTube 오디오**: [yt-dlp](https://github.com/yt-dlp/yt-dlp) + ffmpeg
- **번역/요약**: [Ollama](https://ollama.com/) + gemma3:4b
- **프론트엔드**: Vanilla HTML/CSS/JS (프레임워크 없음)

## 📁 프로젝트 구조

```
livetts/
├── start.bat          # 원클릭 실행 (Windows)
├── start.sh           # 원클릭 실행 (Mac/Linux)
├── server.py          # 메인 서버 (Whisper AI, WebSocket, Ollama API)
├── index.html         # 입력/제어 UI (YouTube + 탭 오디오)
├── viewer.html        # 실시간 자막 뷰어
├── requirements.txt   # Python 의존성
└── README.md
```

## ❓ FAQ

**Q: Whisper 모델 로딩이 오래 걸려요**
A: 첫 실행 시 모델 다운로드 + 로딩에 1~2분 소요됩니다. 이후엔 ~30초 내 로딩됩니다.

**Q: 탭 오디오가 인식이 안 돼요**
A: 공유 팝업에서 "탭 오디오도 공유" 체크를 확인하세요. Chrome/Edge에서만 지원됩니다.

**Q: 번역/요약이 작동하지 않아요**
A: Ollama 서비스가 실행 중인지 확인하세요 (`ollama serve`). `gemma3:4b` 모델이 필요합니다.

**Q: 다른 기기에서 뷰어를 보고 싶어요**
A: 서버 PC의 IP 주소를 확인 후 `http://{IP}:8765/viewer.html`로 접속하세요.

## 📜 License

MIT
