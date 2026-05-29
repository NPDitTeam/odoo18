@echo off
echo ========================================
echo Force Clear Odoo Cache and Update Module
echo ========================================

echo.
echo Step 1: Stopping Odoo service...
net stop "odoo-server-18.0"

echo.
echo Step 2: Deleting Python cache files...
cd "C:\Program Files\Odoo 18.0.20251009\server\custom-addons\transport_booking"
del /s /q __pycache__\*.* 2>nul
for /d /r %%i in (__pycache__) do @rmdir "%%i" 2>nul

echo.
echo Step 3: Starting Odoo...
net start "odoo-server-18.0"

echo.
echo Step 4: Waiting for Odoo to be ready...
timeout /t 10 /nobreak

echo.
echo Step 5: Updating module with cache clear...
cd "C:\Program Files\Odoo 18.0.20251009\server"
python odoo-bin -u transport_booking -d Npd_Transport --stop-after-init

echo.
echo Step 6: Final restart...
net stop "odoo-server-18.0"
timeout /t 3 /nobreak
net start "odoo-server-18.0"

echo.
echo ========================================
echo IMPORTANT: Clear Browser Cache!
echo ========================================
echo.
echo 1. Close ALL browser tabs and windows
echo 2. Press Ctrl+Shift+Delete (Clear browsing data)
echo 3. Select: "Cached images and files"
echo 4. Time range: "All time"
echo 5. Click "Clear data"
echo.
echo OR use Incognito/Private browsing mode
echo ========================================
pause
