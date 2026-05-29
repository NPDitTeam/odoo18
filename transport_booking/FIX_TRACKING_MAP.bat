@echo off
cls
echo ============================================================
echo   ODOO TRACKING MAP FIX - MASTER SCRIPT
echo ============================================================
echo.
echo This script will:
echo   1. Stop Odoo service
echo   2. Clear Python cache
echo   3. Start Odoo temporarily
echo   4. Run Odoo shell to clear view cache
echo   5. Update module
echo   6. Restart Odoo
echo.
echo Press any key to continue or Ctrl+C to cancel...
pause >nul

echo.
echo [1/7] Stopping Odoo service...
net stop "odoo-server-18.0"
if %errorlevel% neq 0 (
    echo Warning: Failed to stop Odoo service
)

echo.
echo [2/7] Clearing Python cache...
cd "C:\Program Files\Odoo 18.0.20251009\server\custom-addons\transport_booking"
for /d /r %%i in (__pycache__) do @rmdir /s /q "%%i" 2>nul
echo Done.

echo.
echo [3/7] Starting Odoo service temporarily...
net start "odoo-server-18.0"
if %errorlevel% neq 0 (
    echo Error: Failed to start Odoo service
    pause
    exit /b 1
)

echo.
echo [4/7] Waiting for Odoo to be ready...
timeout /t 15 /nobreak

echo.
echo [5/7] Running Odoo shell to clear view cache...
cd "C:\Program Files\Odoo 18.0.20251009\server"
python odoo-bin shell -d Npd_Transport --stop-after-init < custom-addons\transport_booking\force_clear_views.py

echo.
echo [6/7] Updating transport_booking module...
python odoo-bin -u transport_booking -d Npd_Transport --stop-after-init

echo.
echo [7/7] Final restart...
net stop "odoo-server-18.0"
timeout /t 3 /nobreak
net start "odoo-server-18.0"

echo.
echo ============================================================
echo   COMPLETED SUCCESSFULLY!
echo ============================================================
echo.
echo IMPORTANT: Follow these steps NOW:
echo.
echo   1. CLOSE ALL BROWSER WINDOWS (very important!)
echo.
echo   2. Open NEW INCOGNITO/PRIVATE window:
echo      - Chrome: Ctrl + Shift + N
echo      - Edge: Ctrl + Shift + P
echo.
echo   3. Go to: http://127.0.0.1:8069
echo.
echo   4. Login and check:
echo      Bookings -^> BOOK-20251026-0013 -^> Tab "ติดตามการขนส่ง"
echo.
echo   5. Press F12 -^> Network tab
echo      Look for: js?key=AIzaSyAorvWR... (NOT js?key=^&)
echo.
echo ============================================================
pause
