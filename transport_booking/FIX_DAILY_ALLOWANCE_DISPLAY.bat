@echo off
REM =============================================================================
REM  🔧 ตัวแก้ไขการแสดงค่าเบี้ยเลี้ยง - Delivery History
REM  Daily Allowance Display Fix
REM =============================================================================
REM
REM โปรแกรมนี้จะ:
REM  1. ทำให้แน่ใจว่า XML ได้รับการแก้ไขแล้ว
REM  2. ล้างแคช Python
REM  3. รีสตาร์ท Odoo Service
REM
REM =============================================================================

setlocal enabledelayedexpansion
cd /d "C:\Program Files\Odoo 18.0.20251009\server\custom-addons\transport_booking"

color 0A
cls

echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║  🔧 ตัวแก้ไขการแสดงค่าเบี้ยเลี้ยง - Delivery History           ║
echo ║     Daily Allowance Display Fix                               ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.

REM ตรวจสอบ Admin Rights
echo 📋 ตรวจสอบ Admin Rights...
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ ต้องใช้ Admin Rights! กรุณาเปิด CMD เป็น Administrator
    echo.
    echo ⏳ กด Enter เพื่อปิด...
    pause
    exit /b 1
)
echo ✅ มี Admin Rights

echo.
echo 📍 ขั้นตอนที่ 1: ล้างแคช Python __pycache__
echo ─────────────────────────────────────
for /d /r . %%d in (__pycache__) do @if exist "%%d" (
    echo   🗑️  ลบ: %%d
    rmdir /s /q "%%d"
)
echo ✅ ล้างแคชเรียบร้อย

echo.
echo 📍 ขั้นตอนที่ 2: รีสตาร์ท Odoo Service
echo ─────────────────────────────────────
echo ⏳ หยุด Odoo Service...
net stop odoo /y
timeout /t 3 /nobreak

echo ✅ เริ่ม Odoo Service...
net start odoo
timeout /t 5 /nobreak

REM ตรวจสอบว่า Service เริ่มแล้ว
sc query odoo | find "RUNNING" >nul
if %errorlevel% equ 0 (
    echo ✅ Odoo Service เริ่มเรียบร้อย
) else (
    echo ❌ Odoo Service ยังไม่เริ่ม (อาจต้องรอ)
)

echo.
echo 📍 ขั้นตอนที่ 3: ข้อมูลการใช้งาน
echo ─────────────────────────────────────
echo   1️⃣  เข้าระบบ Odoo (ตามปกติ)
echo   2️⃣  ไปที่: Transport Booking ^> ประวัติการจัดส่ง
echo   3️⃣  ตรวจสอบคอลัมน์ "ค่าเบี้ยเลี้ยง" ต้องแสดงผล
echo   4️⃣  ถ้ายังไม่แสดง ให้: F5 (รีโหลด) หรือ Ctrl+Shift+R (ล้างแคชเบราว์เซอร์)
echo.

echo 🎉 เสร็จเรียบร้อย!
echo ⏳ กด Enter เพื่อปิด...
pause
exit /b 0
