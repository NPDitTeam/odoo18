@echo off
echo ======================================
echo  Fix GPS Integration Issues
echo  - Remove attrs (Odoo 18)
echo  - Silent mode for missing GPS
echo ======================================
echo.
echo Fixed Issues:
echo  [✓] Removed deprecated 'attrs' attribute
echo  [✓] No warning when GPS not found
echo  [✓] GPS info only shows when available
echo.

SET /P DB_NAME="Enter your database name: "

cd /d "C:\Program Files\Odoo 18.0.20251009\server"

echo.
echo Stopping Odoo Service...
net stop "odoo-server-18.0"

echo.
echo Upgrading module: transport_booking
echo Database: %DB_NAME%
echo.

python odoo-bin -c odoo.conf -d %DB_NAME% -u transport_booking --stop-after-init --log-level=info

echo.
echo Starting Odoo Service...
net start "odoo-server-18.0"

echo.
echo ======================================
echo Fix Completed Successfully!
echo ======================================
echo.
echo Changes:
echo  1. GPS button shows only when vehicle found
echo  2. GPS info section hidden when not available
echo  3. No warning logs for missing GPS data
echo  4. Compatible with Odoo 18 (no attrs)
echo.
echo Behavior:
echo  - If GPS found: Show GPS button + info
echo  - If GPS not found: Hide everything (silent)
echo.
echo Please refresh your browser (Ctrl+F5) and test!
pause
