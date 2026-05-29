@echo off
chcp 65001 >nul

REM ถ้า Odoo ยังรันอยู่ ให้ปิดก่อน
echo ⏹️ Stopping Odoo...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq Odoo*" 2>nul
timeout /t 2 /nobreak

echo ✅ Fixed! Starting Odoo with Python reload...
cd /d "C:\Program Files\Odoo 18.0.20251009\server"
python odoo-bin.py -c odoo.conf --dev=all 2>&1

echo.
pause
