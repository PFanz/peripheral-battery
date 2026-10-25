peripheral-battery portable package
====================================

Contents:
  peripheral_battery_service.exe  -- the battery bridge service (standalone, no Python needed)
  MouseBattery.json               -- LiteMonitor plugin
  install.bat                     -- one-click install (per-user, no admin)
  uninstall.bat                   -- one-click uninstall

Quick start:
  1. Double-click install.bat
     - installs the service to %LOCALAPPDATA%\peripheral-battery
     - registers autostart (HKCU Run)
     - starts the service now
     - auto-detects LiteMonitor and deploys the plugin if found
  2. Open LiteMonitor -> plugin settings -> enable "MouseBattery"
  3. Verify: open http://127.0.0.1:8712/battery in a browser

Requirements:
  - Inphic official driver (Inphic.exe) must be installed and running
    (it normally auto-starts with Windows).

Uninstall: double-click uninstall.bat
