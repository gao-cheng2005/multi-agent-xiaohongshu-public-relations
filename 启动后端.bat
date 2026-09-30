@echo off
chcp 65001 >nul
cd /d %~dp0
echo 启动舆情后端：http://127.0.0.1:8000
C:\Users\HUAWEI\.conda\envs\agent_project_1\python.exe run.py
pause
