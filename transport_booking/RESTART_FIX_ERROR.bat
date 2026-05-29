@echo off
echo ========================================
echo   🔧 Restarting Odoo - Fix Error Message
echo ========================================
echo.

echo [1/3] Stopping Odoo service...
net stop odoo-server-18.0
if %errorlevel% neq 0 (
    echo ❌ Failed to stop Odoo service!
    echo Please run as Administrator
    pause
    exit /b 1
)
echo ✅ Odoo stopped

echo.
echo [2/3] Waiting 3 seconds...
timeout /t 3 /nobreak >nul

echo.
echo [3/3] Starting Odoo service...
net start odoo-server-18.0
if %errorlevel% neq 0 (
    echo ❌ Failed to start Odoo service!
    pause
    exit /b 1
)
echo ✅ Odoo started

echo.
echo ========================================
echo   ✅ Restart Complete!
echo ========================================
echo.
echo Next steps:
echo 1. Clear browser cache (Ctrl + Shift + Delete)
echo 2. Refresh tracking map (Ctrl + F5)
echo 3. Check console (F12) for any remaining errors
echo.
pause
