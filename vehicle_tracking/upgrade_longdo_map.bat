@echo off
echo ========================================
echo  Upgrade Vehicle Tracking Module
echo  (Longdo Map with Pulsing Dot)
echo ========================================
echo.

cd /d "C:\Program Files\Odoo 18.0.20251009\server"

echo Upgrading module...
python odoo-bin -c odoo.conf -d odoo18 -u vehicle_tracking --stop-after-init

echo.
echo ========================================
echo  Upgrade Complete!
echo ========================================
echo.
echo Please restart Odoo service and refresh
echo your browser to see the new Longdo Map
echo with Pulsing Dot effect.
echo.
pause
