#!/bin/bash
# ============================================
# LiveSTT 원클릭 실행 스크립트 (Mac/Linux)
#
# 터미널에서 실행: chmod +x start.sh && ./start.sh
#
# 이 파일을 실행하면:
# 1. Python, ffmpeg, Ollama 설치 여부 확인
# 2. 미설치 항목 자동 설치 (brew 사용)
# 3. Python 패키지 설치
# 4. Ollama 모델 다운로드
# 5. Ollama + Python 서버 실행
# 6. 준비 완료되면 브라우저 자동 오픈
# ============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKIP_OLLAMA=0

echo ""
echo "============================================"
echo "  LiveSTT - 실시간 자막 서버"
echo "  원클릭 실행 스크립트"
echo "============================================"
echo ""

# ------------------------------------------
# Homebrew 확인 (Mac만)
# ------------------------------------------
check_brew() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        if ! command -v brew &>/dev/null; then
            echo "  Homebrew가 설치되어 있지 않습니다."
            echo "  자동 설치를 시도합니다..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
            echo "  Homebrew 설치 완료!"
        fi
    fi
}

# ------------------------------------------
# 1단계: Python 확인
# ------------------------------------------
echo "[1/6] Python 확인 중..."
if ! command -v python3 &>/dev/null; then
    echo "  Python이 설치되어 있지 않습니다."
    echo "  자동 설치를 시도합니다..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        check_brew
        brew install python@3.12
    else
        sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv
    fi
    echo "  Python 설치 완료!"
fi
echo "  $(python3 --version) 확인됨 ✓"

# ------------------------------------------
# 2단계: ffmpeg 확인
# ------------------------------------------
echo "[2/6] ffmpeg 확인 중..."
if ! command -v ffmpeg &>/dev/null; then
    echo "  ffmpeg가 설치되어 있지 않습니다."
    echo "  자동 설치를 시도합니다..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        check_brew
        brew install ffmpeg
    else
        sudo apt-get update && sudo apt-get install -y ffmpeg
    fi
    echo "  ffmpeg 설치 완료!"
fi
echo "  ffmpeg 확인됨 ✓"

# ------------------------------------------
# 3단계: Ollama 확인
# ------------------------------------------
echo "[3/6] Ollama 확인 중..."
if ! command -v ollama &>/dev/null; then
    echo "  Ollama가 설치되어 있지 않습니다."
    echo "  자동 설치를 시도합니다..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        check_brew
        brew install ollama
    else
        curl -fsSL https://ollama.com/install.sh | sh
    fi

    if ! command -v ollama &>/dev/null; then
        echo "  [경고] Ollama 설치에 실패했습니다."
        echo "  https://ollama.com/download 에서 직접 설치해주세요."
        echo "  (Ollama 없이도 자막 기능은 사용 가능합니다)"
        SKIP_OLLAMA=1
    else
        echo "  Ollama 설치 완료!"
    fi
else
    echo "  Ollama 확인됨 ✓"
fi

# ------------------------------------------
# 4단계: Python 패키지 설치
# ------------------------------------------
echo "[4/6] Python 패키지 확인 중..."
if ! python3 -c "import aiohttp; import faster_whisper; import yt_dlp" &>/dev/null; then
    echo "  필요한 패키지를 설치합니다..."

    # 가상환경이 있으면 활성화, 없으면 생성
    if [ -d "$SCRIPT_DIR/venv" ]; then
        source "$SCRIPT_DIR/venv/bin/activate"
    fi

    pip3 install -r "$SCRIPT_DIR/requirements.txt"
    echo "  패키지 설치 완료!"
else
    echo "  Python 패키지 확인됨 ✓"
fi

# ------------------------------------------
# 5단계: Ollama 모델 확인 + 서비스 시작
# ------------------------------------------
if [ "$SKIP_OLLAMA" -eq 0 ]; then
    echo "[5/6] Ollama 모델 확인 중..."

    # Ollama 서비스가 실행 중인지 확인
    if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
        echo "  Ollama 서비스 시작 중..."
        ollama serve &>/dev/null &
        OLLAMA_PID=$!

        # 서비스 시작 대기 (최대 15초)
        for i in $(seq 1 15); do
            sleep 1
            if curl -s http://localhost:11434/api/tags &>/dev/null; then
                break
            fi
        done
    fi
    echo "  Ollama 서비스 실행 중 ✓"

    # gemma3:4b 모델 확인
    if ! ollama list 2>/dev/null | grep -qi "gemma3:4b"; then
        echo "  gemma3:4b 모델 다운로드 중... (약 3GB, 몇 분 소요)"
        ollama pull gemma3:4b
        echo "  모델 다운로드 완료!"
    else
        echo "  gemma3:4b 모델 확인됨 ✓"
    fi
else
    echo "[5/6] Ollama 건너뜀 (미설치)"
fi

# ------------------------------------------
# 6단계: 서버 실행 + 브라우저 오픈
# ------------------------------------------
echo "[6/6] LiveSTT 서버 시작 중..."
echo ""
echo "============================================"
echo "  잠시 후 브라우저가 자동으로 열립니다."
echo "  (Whisper 모델 로딩에 1~2분 소요)"
echo ""
echo "  입력:  http://localhost:8765"
echo "  뷰어:  http://localhost:8765/viewer.html"
echo ""
echo "  종료하려면 Ctrl+C를 누르세요."
echo "============================================"
echo ""

# 서버가 준비되면 브라우저를 여는 백그라운드 작업
(
    for i in $(seq 1 120); do
        sleep 2
        if curl -s http://localhost:8765/api/status &>/dev/null; then
            if [[ "$OSTYPE" == "darwin"* ]]; then
                open "http://localhost:8765"
            else
                xdg-open "http://localhost:8765" 2>/dev/null || true
            fi
            exit 0
        fi
    done
) &

# 서버 실행 (포그라운드)
python3 "$SCRIPT_DIR/server.py"
