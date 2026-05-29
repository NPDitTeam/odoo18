@echo off
REM ======================================
REM 🚀 Restart Odoo - Food Delivery Style
REM ======================================

echo.
echo ╔══════════════════════════════════════╗
echo ║  🚚 Restart Odoo - Food Delivery UI ║
echo ╚══════════════════════════════════════╝
echo.

REM Stop Odoo service
echo 🛑 Stopping Odoo service...
net stop odoo-server-18.0
timeout /t 2 >nul

REM Start Odoo service
echo 🚀 Starting Odoo service...
net start odoo-server-18.0

echo.
echo ✅ Odoo restarted successfully!
echo 📍 You can now access the Food Delivery style tracking at:
echo    http://localhost:8069/tracking/map/[BOOKING_ID]
echo.
echo 💡 Don't forget to:
echo    1. Update your module (Apps → Transport Booking → Upgrade)
echo    2. Use simulate_vehicle_tracking.py to generate GPS data
echo.

pause
