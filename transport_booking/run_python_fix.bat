@echo off
REM =======================================================
REM 🔧 Force Delete Invalid Records via Python
REM =======================================================

echo.
echo =========================================================
echo   🔧 Running Python Script to Delete Invalid Records
echo =========================================================
echo.

REM เปลี่ยน path ไป folder ที่มี script
cd /d "C:\Program Files\Odoo 18.0.20251009\server\custom-addons\transport_booking"

REM รัน Python script
python force_delete_invalid.py

echo.
pause
