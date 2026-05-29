@echo off
echo ========================================
echo   🔧 Fix Auto-Refresh Error Message
echo   Version: 4.3
echo ========================================
echo.

echo ✅ Changes made:
echo    - Changed console.error to console.warn
echo    - Removed debug information dump
echo    - System still works with default settings
echo.

echo [1/4] Stopping Odoo service...
net stop odoo-server-18.0
if %errorlevel% neq 0 (
    echo ❌ Failed to stop Odoo! Please run as Administrator
    pause
    exit /b 1
)
echo ✅ Odoo stopped

echo.
echo [2/4] Waiting 3 seconds...
timeout /t 3 /nobreak >nul

echo.
echo [3/4] Starting Odoo service...
net start odoo-server-18.0
if %errorlevel% neq 0 (
    echo ❌ Failed to start Odoo!
    pause
    exit /b 1
)
echo ✅ Odoo started

echo.
echo [4/4] Waiting for Odoo to fully start (10 seconds)...
timeout /t 10 /nobreak >nul

echo.
echo ========================================
echo   ✅ Restart Complete!
echo ========================================
echo.
echo IMPORTANT: You must clear browser cache!
echo.
echo Chrome/Edge:
echo   1. Press Ctrl + Shift + Delete
echo   2. Select "Cached images and files"
echo   3. Click "Clear data"
echo   4. Refresh page with Ctrl + F5
echo.
echo Firefox:
echo   1. Press Ctrl + Shift + Delete
echo   2. Select "Cache"
echo   3. Click "Clear Now"
echo   4. Refresh page with Ctrl + F5
echo.
echo Expected result:
echo   - Console shows: ⚠️ [Auto-Refresh] Cannot detect user ID
echo   - NO red error message
echo   - Auto-refresh works normally (30 min default)
echo.
pause
