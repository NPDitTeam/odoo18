@echo off
echo Installing Vehicle Tracking Module...
echo.

cd /d "C:\Program Files\Odoo 18.0.20251009\server"

python odoo-bin -c odoo.conf -d YOUR_DATABASE_NAME -i vehicle_tracking --stop-after-init

echo.
echo Installation completed!
echo Please restart Odoo server.
pause
