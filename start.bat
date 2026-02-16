@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
title LiveSTT - 실시간 자막 서버

:: ============================================
:: LiveSTT 원클릭 실행 스크립트 (Windows)
::
:: 이 파일을 더블클릭하면:
:: 1. Python, ffmpeg, Ollama 설치 여부 확인
:: 2. 미설치 항목 자동 설치 (winget 사용)
:: 3. Python 패키지 설치
:: 4. Ollama 모델 다운로드
:: 5. Ollama + Python 서버 실행
:: 6. 준비 완료되면 브라우저 자동 오픈
:: ============================================

echo.
echo ============================================
echo   LiveSTT - 실시간 자막 서버
echo   원클릭 실행 스크립트
echo ============================================
echo.

:: ------------------------------------------
:: 1단계: Python 확인
:: ------------------------------------------
echo [1/6] Python 확인 중...
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   Python이 설치되어 있지 않습니다.
    echo   자동 설치를 시도합니다...
    echo.
    winget install Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo   [오류] Python 자동 설치에 실패했습니다.
        echo   https://www.python.org/downloads/ 에서 직접 설치해주세요.
        echo   설치 시 "Add Python to PATH" 체크를 반드시 해주세요!
        echo.
        pause
        exit /b 1
    )
    echo   Python 설치 완료! 터미널을 재시작합니다...
    echo   이 파일을 다시 더블클릭해주세요.
    pause
    exit /b 0
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo   %%i 확인됨 ✓

:: ------------------------------------------
:: 2단계: ffmpeg 확인
:: ------------------------------------------
echo [2/6] ffmpeg 확인 중...
where ffmpeg >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   ffmpeg가 설치되어 있지 않습니다.
    echo   자동 설치를 시도합니다...
    echo.
    winget install Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo   [오류] ffmpeg 자동 설치에 실패했습니다.
        echo   https://ffmpeg.org/download.html 에서 직접 설치해주세요.
        echo.
        pause
        exit /b 1
    )
    echo   ffmpeg 설치 완료!
    echo   PATH 반영을 위해 이 파일을 다시 더블클릭해주세요.
    pause
    exit /b 0
)
echo   ffmpeg 확인됨 ✓

:: ------------------------------------------
:: 3단계: Ollama 확인
:: ------------------------------------------
echo [3/6] Ollama 확인 중...
where ollama >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   Ollama가 설치되어 있지 않습니다.
    echo   자동 설치를 시도합니다...
    echo.
    winget install Ollama.Ollama --accept-source-agreements --accept-package-agreements
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo   [오류] Ollama 자동 설치에 실패했습니다.
        echo   https://ollama.com/download 에서 직접 설치해주세요.
        echo   (Ollama 없이도 자막 기능은 사용 가능합니다. 번역/요약만 안 됩니다)
        echo.
        set SKIP_OLLAMA=1
    ) else (
        echo   Ollama 설치 완료!
        echo   PATH 반영을 위해 이 파일을 다시 더블클릭해주세요.
        pause
        exit /b 0
    )
) else (
    echo   Ollama 확인됨 ✓
)

:: ------------------------------------------
:: 4단계: Python 패키지 설치
:: ------------------------------------------
echo [4/6] Python 패키지 확인 중...
python -c "import aiohttp; import faster_whisper; import yt_dlp" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   필요한 패키지를 설치합니다...
    echo.
    pip install -r "%~dp0requirements.txt"
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo   [오류] 패키지 설치에 실패했습니다.
        echo   수동으로 실행해보세요: pip install -r requirements.txt
        pause
        exit /b 1
    )
    echo   패키지 설치 완료!
) else (
    echo   Python 패키지 확인됨 ✓
)

:: ------------------------------------------
:: 5단계: Ollama 모델 확인 + 서비스 시작
:: ------------------------------------------
if not defined SKIP_OLLAMA (
    echo [5/6] Ollama 모델 확인 중...

    :: Ollama 서비스가 실행 중인지 확인
    curl -s http://localhost:11434/api/tags >nul 2>&1
    if !ERRORLEVEL! NEQ 0 (
        echo   Ollama 서비스 시작 중...
        start /min "" ollama serve
        timeout /t 5 /nobreak >nul
    )
    echo   Ollama 서비스 실행 중 ✓

    :: gemma3:4b 모델 확인
    ollama list 2>nul | findstr /i "gemma3:4b" >nul 2>&1
    if %ERRORLEVEL% NEQ 0 (
        echo   gemma3:4b 모델 다운로드 중... (약 3GB, 몇 분 소요)
        echo.
        ollama pull gemma3:4b
        if %ERRORLEVEL% NEQ 0 (
            echo   [경고] 모델 다운로드 실패. 번역/요약 기능은 나중에 사용 가능합니다.
        ) else (
            echo   모델 다운로드 완료!
        )
    ) else (
        echo   gemma3:4b 모델 확인됨 ✓
    )
) else (
    echo [5/6] Ollama 건너뜀 (미설치)
)

:: ------------------------------------------
:: 6단계: 서버 실행 + 브라우저 오픈
:: ------------------------------------------
echo [6/6] LiveSTT 서버 시작 중...
echo.
echo ============================================
echo   잠시 후 브라우저가 자동으로 열립니다.
echo   (Whisper 모델 로딩에 1~2분 소요)
echo.
echo   입력:  http://localhost:8765
echo   뷰어:  http://localhost:8765/viewer.html
echo.
echo   종료하려면 이 창을 닫으세요.
echo ============================================
echo.

:: 서버가 준비되면 브라우저를 여는 백그라운드 작업
start /min "" cmd /c "for /L %%i in (1,1,120) do (timeout /t 2 /nobreak >nul & curl -s http://localhost:8765/api/status >nul 2>&1 && (start http://localhost:8765 & exit /b 0))"

:: 서버 실행 (포그라운드 — 이 창이 서버 로그를 보여줌)
python "%~dp0server.py"

:: 서버가 종료되면
echo.
echo 서버가 종료되었습니다.
pause
