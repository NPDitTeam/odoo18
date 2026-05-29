@echo off
REM ==========================================
REM Fix Odoo Multi-Branch Module & Restart
REM ==========================================

setlocal enabledelayedexpansion

echo.
echo 🔧 Odoo Multi-Branch Module Fix
echo ==========================================
echo.

echo [1/4] Backing up original file...
set BACKUP_FILE="C:\Program Files\Odoo 18.0.20251009\server\custom-addons\multi_branch_management_aagam\models\ir_http.py.backup_!date:~6,4!!date:~3,2!!date:~0,2!"
copy "C:\Program Files\Odoo 18.0.20251009\server\custom-addons\multi_branch_management_aagam\models\ir_http.py" !BACKUP_FILE! > nul
echo ✅ Backup created: !BACKUP_FILE!

echo.
echo [2/4] File already patched!
echo ✅ ir_http.py fixed with:
echo    - Null check for user object
echo    - Safe branch access
echo    - Try-catch error handling

echo.
echo [3/4] Stopping Odoo service...
net stop "Odoo 18.0" > nul 2>&1
if errorlevel 1 (
    echo ⚠️  Odoo may already be stopped
) else (
    echo ✅ Odoo stopped
)

echo Waiting 5 seconds...
timeout /t 5 /nobreak

echo.
echo [4/4] Starting Odoo service...
net start "Odoo 18.0" > nul 2>&1
if errorlevel 1 (
    echo ❌ Error starting Odoo!
    echo Try starting manually: Services → Odoo 18.0
    pause
    exit /b 1
) else (
    echo ✅ Odoo started
)

echo.
echo Waiting for Odoo to fully start (30 seconds)...
timeout /t 30 /nobreak

echo.
echo ==========================================
echo ✅ Fix Complete!
echo ==========================================
echo.
echo 🧪 To test:
echo   1. Open browser: http://119.59.124.50:8070
echo   2. Try to login
echo   3. Should NOT see AttributeError
echo.
echo 📱 To test in app:
echo   1. Run: flutter run
echo   2. Try PIN: 888888
echo   3. Should get past connection check
echo.
pause