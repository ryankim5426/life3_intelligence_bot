@echo off
REM 생보 3사 인텔리전스 봇 - Windows 실행용
REM 이 파일이 있는 폴더에서 실행됩니다.
cd /d "%~dp0"

REM 최초 1회만: 필요한 라이브러리 설치
if not exist ".installed" (
    python -m pip install -r requirements.txt
    echo ok > .installed
)

python main.py >> bot.log 2>&1
