@echo off
REM ========================================
REM 🚀 Update Odoo - Food Delivery Tracking
REM ========================================

echo.
echo ╔════════════════════════════════════════════╗
echo ║  🚀 Update Odoo - Tracking Improvements   ║
echo ╚════════════════════════════════════════════╝
echo.

REM Check Administrator
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ❌ Error: Requires Administrator privileges
    echo Please right-click and select "Run as Administrator"
    pause
    exit /b 1
)

echo ✅ Running with Administrator privileges
echo.

REM ==========================================
REM Stop Odoo Service
REM ==========================================
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo 🛑 Stopping Odoo service...
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

net stop odoo-server-18.0
if %errorLevel% equ 0 (
    echo ✅ Odoo service stopped
) else (
    echo ⚠️  Could not stop Odoo service
)

timeout /t 2 >nul
echo.

REM ==========================================
REM Start Odoo Service
REM ==========================================
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo 🚀 Starting Odoo service...
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

net start odoo-server-18.0
if %errorLevel% equ 0 (
    echo ✅ Odoo service started successfully!
) else (
    echo ❌ Failed to start Odoo service
    echo Please start it manually from Services
)

timeout /t 3 >nul
echo.

REM ==========================================
REM Summary
REM ==========================================
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo 📋 What's New:
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo ✨ Updated Features:
echo   1. 🎨 Food Delivery Style Tracking Map
echo   2. ⚙️  Settings Integration (tracking.settings)
echo   3. 📊 Modern Tracking Views
echo   4. 🗺️  Smart Button for Tracking Map
echo   5. 📡 Real-time GPS Updates
echo.
echo 🎯 Next Steps:
echo   1. Login to Odoo → Apps
echo   2. Search "Transport Booking"
echo   3. Click "Upgrade" button
echo   4. Go to Bookings and click "🗺️ แผนที่ติดตาม"
echo.
echo 📱 For Mobile App:
echo   - App already sends GPS data to Odoo
echo   - View tracking at: http://localhost:8069/tracking/map/[ID]
echo.
echo 📚 Documentation:
echo   - FOOD_DELIVERY_TRACKING_README.md
echo   - QUICK_START_FOOD_DELIVERY.md
echo   - ODOO_TRACKING_IMPROVEMENTS.md (NEW!)
echo.

pause
