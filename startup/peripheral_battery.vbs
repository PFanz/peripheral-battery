' peripheral-battery: silent startup launcher
'
' Copy this file into your Startup folder (Win+R -> shell:startup) to start
' the battery service on login with no visible window.
'
' EDIT the two paths below to match your machine:
'   PYTHONW: path to pythonw.exe in your Python installation
'   SCRIPT : path to peripheral_battery_service.py

PYTHONW = "C:\Python\pythonw.exe"
SCRIPT  = "C:\peripheral-battery\service\peripheral_battery_service.py"

Set sh = CreateObject("WScript.Shell")
sh.Run """" & PYTHONW & """ """ & SCRIPT & """", 0, False
