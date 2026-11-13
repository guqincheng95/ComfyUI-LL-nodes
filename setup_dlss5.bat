@echo off
setlocal
set PYTHONUTF8=1
set "LL_SETUP_PYTHON="
if defined LL_COMFY_PYTHON if exist "%LL_COMFY_PYTHON%" set "LL_SETUP_PYTHON=%LL_COMFY_PYTHON%"
if not defined LL_SETUP_PYTHON if exist "%~dp0..\..\..\python_embeded\python.exe" set "LL_SETUP_PYTHON=%~dp0..\..\..\python_embeded\python.exe"
if not defined LL_SETUP_PYTHON if exist "%~dp0..\..\..\python\python.exe" set "LL_SETUP_PYTHON=%~dp0..\..\..\python\python.exe"
if not defined LL_SETUP_PYTHON if exist "%~dp0..\..\.venv\Scripts\python.exe" set "LL_SETUP_PYTHON=%~dp0..\..\.venv\Scripts\python.exe"
if not defined LL_SETUP_PYTHON if exist "%~dp0..\..\venv\Scripts\python.exe" set "LL_SETUP_PYTHON=%~dp0..\..\venv\Scripts\python.exe"
if not defined LL_SETUP_PYTHON (
  echo ComfyUI Python not found. Set LL_COMFY_PYTHON to its full python.exe path.
  pause
  exit /b 2
)
"%LL_SETUP_PYTHON%" "%~dp0setup_dlss5.py" %*
set "LL_SETUP_RESULT=%ERRORLEVEL%"
pause
exit /b %LL_SETUP_RESULT%
