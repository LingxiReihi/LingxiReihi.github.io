@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ROOT=%~dp0"
set "BACKEND_DIR=%ROOT%backend"
set "FRONTEND_DIR=%ROOT%frontend"

set "BACKEND_PORT_EXPLICIT="
if defined BACKEND_PORT set "BACKEND_PORT_EXPLICIT=1"
if not defined BACKEND_PORT set "BACKEND_PORT=8000"
set "FRONTEND_PORT_EXPLICIT="
if defined FRONTEND_PORT set "FRONTEND_PORT_EXPLICIT=1"
if not defined FRONTEND_PORT set "FRONTEND_PORT=5173"
if not defined BACKEND_RELOAD set "BACKEND_RELOAD=0"

if not exist "%BACKEND_DIR%\.venv\Scripts\python.exe" (
  echo [dev] ERROR: backend venv not found.
  echo        cd backend ^&^& python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
  exit /b 1
)
set "PY=%BACKEND_DIR%\.venv\Scripts\python.exe"

where node >nul 2>&1
if errorlevel 1 (
  echo [dev] ERROR: node not found. Install Node.js first.
  exit /b 1
)
where curl >nul 2>&1
if errorlevel 1 (
  echo [dev] ERROR: curl not found. Windows 10/11 should include it.
  exit /b 1
)
if not exist "%FRONTEND_DIR%\node_modules\vite\bin\vite.js" (
  echo [dev] ERROR: frontend dependencies not installed.
  echo        cd frontend ^&^& npm install
  exit /b 1
)

call :port_busy %BACKEND_PORT%
if errorlevel 1 goto backend_port_ok
if defined BACKEND_PORT_EXPLICIT goto backend_port_conflict
set /a ALT=%BACKEND_PORT%+1
:pick_backend
call :port_busy %ALT%
if errorlevel 1 goto backend_picked
set /a ALT+=1
if %ALT% gtr 8020 goto no_backend_port
goto pick_backend
:backend_picked
echo [dev] Backend port %BACKEND_PORT% is busy, using %ALT%.
set "BACKEND_PORT=%ALT%"
goto backend_port_ok
:backend_port_conflict
echo [dev] ERROR: backend port %BACKEND_PORT% is already in use.
echo        Use another port: set BACKEND_PORT=8001 ^&^& dev.bat
exit /b 1
:no_backend_port
echo [dev] ERROR: no free backend port near %BACKEND_PORT%.
exit /b 1

:backend_port_ok
call :port_busy %FRONTEND_PORT%
if errorlevel 1 goto frontend_port_ok
if defined FRONTEND_PORT_EXPLICIT goto frontend_port_conflict
set /a ALT=%FRONTEND_PORT%+1
:pick_frontend
call :port_busy %ALT%
if errorlevel 1 goto frontend_picked
set /a ALT+=1
if %ALT% gtr 5190 goto no_frontend_port
goto pick_frontend
:frontend_picked
echo [dev] Frontend port %FRONTEND_PORT% is busy, using %ALT%.
set "FRONTEND_PORT=%ALT%"
goto frontend_port_ok
:frontend_port_conflict
echo [dev] ERROR: frontend port %FRONTEND_PORT% is already in use.
echo        Use another port: set FRONTEND_PORT=5174 ^&^& dev.bat
exit /b 1
:no_frontend_port
echo [dev] ERROR: no free frontend port near %FRONTEND_PORT%.
exit /b 1

:frontend_port_ok
set "RELOAD_PS="
if "%BACKEND_RELOAD%"=="1" set "RELOAD_PS=,'--reload'"

echo [dev] Backend :%BACKEND_PORT%  Frontend :%FRONTEND_PORT%
set "PIDFILE=%TEMP%\personal-web-backend-%RANDOM%.pid"
powershell -NoProfile -Command "$p = Start-Process -FilePath '%PY%' -ArgumentList '-m','uvicorn','app.main:app','--port','%BACKEND_PORT%'%RELOAD_PS% -WorkingDirectory '%BACKEND_DIR%' -NoNewWindow -PassThru; Set-Content -Path '%PIDFILE%' -Value $p.Id"
set "BACKEND_PID="
if exist "%PIDFILE%" set /p BACKEND_PID=<"%PIDFILE%"
del "%PIDFILE%" >nul 2>&1
if not defined BACKEND_PID goto backend_failed

set /a WAIT=0
:wait_backend
curl -fsS -o nul "http://127.0.0.1:%BACKEND_PORT%/api/v1/site-config" >nul 2>&1
if not errorlevel 1 goto backend_ready
set /a WAIT+=1
if %WAIT% geq 40 goto backend_failed
ping -n 2 127.0.0.1 >nul
goto wait_backend

:backend_failed
echo [dev] ERROR: backend did not become ready in 20s. Check .env, database and dependencies.
call :stop_backend
exit /b 1

:backend_ready
echo [dev] Backend ready.
echo.
echo   Frontend   http://127.0.0.1:%FRONTEND_PORT%
echo   Admin      http://127.0.0.1:%FRONTEND_PORT%/admin
echo   API        http://127.0.0.1:%BACKEND_PORT%/api/v1
echo.
echo   Press Ctrl+C to stop both.
echo.

pushd "%FRONTEND_DIR%"
set "DEV_PROXY_TARGET=http://127.0.0.1:%BACKEND_PORT%"
set "VITE_STATIC=false"
node "%FRONTEND_DIR%\node_modules\vite\bin\vite.js" --host 127.0.0.1 --port %FRONTEND_PORT% --strictPort
set "FE_EXIT=%errorlevel%"
popd

echo [dev] Frontend exited, stopping backend...
call :stop_backend
exit /b %FE_EXIT%

:port_busy
node -e "const s=require('net').connect(%1,'127.0.0.1');const d=b=>{s.destroy();process.exit(b?0:1)};s.on('connect',()=>d(1));s.on('error',()=>d(0));s.setTimeout(600,()=>d(0));" >nul 2>&1
exit /b %errorlevel%

:stop_backend
if defined BACKEND_PID taskkill /PID %BACKEND_PID% /T /F >nul 2>&1
exit /b 0