@echo off
echo ========================================
echo   Geocode Existing Bookings
echo ========================================
echo.
echo This will geocode all bookings that don't have coordinates yet.
echo.
pause

cd /d "C:\Program Files\Odoo 18.0.20251009\server\custom-addons\transport_booking"

python geocode_existing_bookings.py

echo.
echo ========================================
echo   Done!
echo ========================================
pause
