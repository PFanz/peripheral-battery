@echo off
setlocal
rem peripheral-battery uninstaller (per-user)

echo Stopping service...
taskkill /im peripheral_battery_service.exe /f >nul 2>&1

echo Removing autostart entry...
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v peripheral-battery /f >nul 2>&1

echo Removing LiteMonitor plugin (if found)...
for %%D in ("C:\" "D:\" "E:\") do (
    for /d %%P in ("%%~DLiteMonitor*") do (
        if exist "%%~fP\resources\plugins\MouseBattery.json" del /q "%%~fP\resources\plugins\MouseBattery.json"
    )
)

echo Removing install directory...
rd /s /q "%LOCALAPPDATA%\peripheral-battery" 2>nul

echo Done. Remove the plugin from LiteMonitor if it is still listed.
pause
