@echo off
echo ========================================
echo Setting Google Maps API Key in Odoo
echo ========================================
echo.

cd "C:\Program Files\Odoo 18.0.20251009\server"

echo Running Odoo shell to set API key...
python odoo-bin shell -d Npd_Transport -c odoo.conf --addons-path=addons,custom-addons -c "exec(open('custom-addons/transport_booking/set_google_api_key.py').read())"

echo.
echo ========================================
echo Done! Press any key to exit...
pause
