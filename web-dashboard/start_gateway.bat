@echo off
chcp 65001 >nul
echo ============================================
echo 智能设备预测性维护 - AI Gateway
echo Dashboard + DeepSeek AI Assistant
echo ============================================
echo.
echo API Key: loaded from .env
echo LLM: DeepSeek (deepseek-chat)
echo.
echo Starting at http://localhost:8765
echo   Dashboard:  http://localhost:8765
echo   Chatbot:    http://localhost:8765/chat
echo   Tech Docs:  http://localhost:8765/technical-overview
echo   API Docs:   http://localhost:8765/docs
echo.
python app.py
pause
