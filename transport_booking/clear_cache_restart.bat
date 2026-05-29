@echo off
chcp 65001 > nul
echo ===============================================
echo   Clear Cache และ Restart Odoo
echo ===============================================
echo.

echo หยุด Odoo Service...
net stop odoo-server-18.0

echo รอ 3 วินาที...
timeout /t 3 /nobreak > nul

echo ลบ Cache...
del /F /Q "C:\Users\%USERNAME%\AppData\Local\Temp\oe-*" 2>nul
echo Cache ถูกลบแล้ว

echo รอ 2 วินาที...
timeout /t 2 /nobreak > nul

echo เริ่ม Odoo Service ใหม่...
net start odoo-server-18.0

echo.
echo ===============================================
echo   เสร็จสิ้น! ลอง Hard Refresh Browser (Ctrl+F5)
echo ===============================================
echo.
pause
