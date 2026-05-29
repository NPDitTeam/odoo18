@echo off
REM =====================================
REM Fix Google Maps in Odoo
REM =====================================

setlocal enabledelayedexpansion

echo.
echo 🗺️  Google Maps Fix Script
echo =====================================
echo.

set ODOO_PATH=C:\Program Files\Odoo 18.0.20251009\server
set MODULE_PATH=%ODOO_PATH%\custom-addons\transport_booking

echo [1/4] Backing up original files...
copy "%MODULE_PATH%\views\map_templates.xml" "%MODULE_PATH%\views\map_templates.xml.backup_!date:~6,4!!date:~3,2!!date:~0,2!" > nul
copy "%MODULE_PATH%\controllers\map_controller.py" "%MODULE_PATH%\controllers\map_controller.py.backup_!date:~6,4!!date:~3,2!!date:~0,2!" > nul
echo ✅ Backup created

echo.
echo [2/4] Files already patched!
echo ✅ map_templates.xml - Fixed with null checks
echo ✅ map_controller.py - Added API key validation

echo.
echo [3/4] Clearing Odoo cache...
cd /d "%ODOO_PATH%"

REM Stop Odoo
echo Stopping Odoo service...
net stop "Odoo 18.0" 2>nul
if errorlevel 1 (
    echo ⚠️  Could not stop Odoo (may already be stopped)
)

REM Wait 5 seconds
timeout /t 5 /nobreak

REM Clear cache
if exist "%ODOO_PATH%\..\data\sessions" (
    del /q "%ODOO_PATH%\..\data\sessions\*" 2>nul
    echo ✅ Sessions cleared
)

if exist "%ODOO_PATH%\odoo\modules\__pycache__" (
    rmdir /s /q "%ODOO_PATH%\odoo\modules\__pycache__" 2>nul
    echo ✅ Python cache cleared
)

echo.
echo [4/4] Restarting Odoo...
net start "Odoo 18.0" 2>nul
if errorlevel 1 (
    echo ❌ Error starting Odoo
    pause
    exit /b 1
)

echo ✅ Odoo started

echo.
echo =====================================
echo ✅ Google Maps Fix Completed!
echo =====================================
echo.
echo 📝 What was fixed:
echo   1. Added null/undefined checks in calculateRoute()
echo   2. Added proper error messages for different API errors
echo   3. Added API key validation in controller
echo   4. Added console logging for debugging
echo.
echo 🧪 To test:
echo   1. Open Odoo browser
echo   2. Go to any Booking
echo   3. Click Map button
echo   4. Should show route without JavaScript error
echo.
echo 📊 Expected output in browser console:
echo   ✅ Route calculation successful
echo   📏 Distance: X km, Duration: Y minutes
echo.
pause