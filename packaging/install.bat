@echo off
setlocal
rem peripheral-battery portable installer (per-user, no admin required)

set "INSTALL_DIR=%LOCALAPPDATA%\peripheral-battery"
set "EXE_SRC=%~dp0peripheral_battery_service.exe"
set "PLUGIN_SRC=%~dp0MouseBattery.json"

echo ============================================
echo  peripheral-battery portable install
echo ============================================

if not exist "%EXE_SRC%" (
    echo [ERROR] peripheral_battery_service.exe not found next to this script.
    pause & exit /b 1
)

rem -- 1. copy service exe --
mkdir "%INSTALL_DIR%" 2>nul
copy /y "%EXE_SRC%" "%INSTALL_DIR%\" >nul || (echo [ERROR] copy failed & pause & exit /b 1)
echo [OK] service installed to %INSTALL_DIR%

rem -- 2. auto-start at logon (HKCU Run, no admin needed) --
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v peripheral-battery /t REG_SZ /d "\"%INSTALL_DIR%\peripheral_battery_service.exe\"" /f >nul
echo [OK] autostart registered (HKCU Run)

rem -- 3. start it now --
tasklist /fi "imagename eq peripheral_battery_service.exe" | find /i "peripheral_battery_service.exe" >nul
if errorlevel 1 start "" "%INSTALL_DIR%\peripheral_battery_service.exe"
echo [OK] service started

rem -- 4. deploy LiteMonitor plugin (search common locations) --
set "LM_PLUGIN="
for %%D in ("%~d0\" "C:\" "D:\" "E:\") do (
    if not defined LM_PLUGIN (
        for /d %%P in ("%%~DLiteMonitor*") do (
            if exist "%%~fP\resources\plugins" set "LM_PLUGIN=%%~fP\resources\plugins"
        )
    )
)
if defined LM_PLUGIN (
    copy /y "%PLUGIN_SRC%" "%LM_PLUGIN%\" >nul 2>&1 && (
        echo [OK] LiteMonitor plugin deployed to %LM_PLUGIN%
        echo      Open LiteMonitor settings and enable the "MouseBattery" plugin.
    ) || echo [WARN] could not copy plugin to %LM_PLUGIN%
) else (
    echo [INFO] LiteMonitor not found automatically.
    echo        Copy MouseBattery.json manually to ^<LiteMonitor^>\resources\plugins\
)

echo.
echo Done. Check http://127.0.0.1:8712/battery in a browser to verify.
pause
