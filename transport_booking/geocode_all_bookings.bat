@echo off
echo ========================================
echo Geocoding All Bookings
echo ========================================
echo.
echo This will add GPS coordinates to all bookings
echo that don't have them yet.
echo.
echo Press Ctrl+C to cancel, or
pause

cd "C:\Program Files\Odoo 18.0.20251009\server"

echo.
echo Running geocoding script...
echo.

python odoo-bin shell -d Npd_Transport -c odoo.conf --addons-path=addons,custom-addons --no-http -c "exec(open('custom-addons/transport_booking/geocode_bookings.py').read())"

echo.
echo ========================================
echo Done! Press any key to exit...
pause
