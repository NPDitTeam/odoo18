# 🚚 Food Delivery Style Tracking - Setup Guide

## 🎯 Overview
ระบบติดตามรถแบบ **Food Delivery App** (Grab, LINE MAN) ที่สามารถดูตำแหน่งรถเรียลไทม์ได้

## ✨ Features

### 🎨 UI/UX แบบ Food Delivery
- ✅ **ไอคอนรถสวยๆ** พร้อมแอนิเมชั่น
- ✅ **จุดรับ (A)** และ **ปลายทาง (B)** แบบ Pin
- ✅ **เส้นทางสีม่วง** แสดงเส้นทางที่รถวิ่งผ่าน
- ✅ **Live Badge** แสดงสถานะการอัพเดท
- ✅ **Stats Bar** แสดงความเร็ว, ระยะทาง, เวลา
- ✅ **Info Card** แสดงข้อมูลการจอง
- ✅ **Responsive** รองรับทั้ง Desktop และ Mobile

### 🔧 Technical Features
- ✅ Auto-refresh ทุก 5 วินาที
- ✅ รองรับ **TransportUserSettings**
- ✅ แสดง **ความเร็วแบบเรียลไทม์**
- ✅ คำนวณ **เวลาโดยประมาณ**
- ✅ แสดง **เส้นทางประวัติ** (Last 100 points)

## 📋 Installation

### 1️⃣ Files Created
```
transport_booking/
├── views/
│   └── tracking_map_food_delivery.xml  ✨ New template
├── controllers/
│   └── tracking_controller.py          ✏️ Updated
├── simulate_vehicle_tracking.py        ✨ New script
├── restart_odoo_food_delivery.bat      ✨ New script
└── FOOD_DELIVERY_TRACKING_README.md    📚 This file
```

### 2️⃣ Update Module
1. เปิด Odoo → Apps
2. ค้นหา "Transport Booking"
3. คลิก **Upgrade**

### 3️⃣ Restart Odoo
Run as **Administrator**:
```cmd
restart_odoo_food_delivery.bat
```

## 🎮 Usage

### 📍 Option 1: View Existing Tracking
1. เปิดเว็บเบราว์เซอร์
2. ไปที่: `http://localhost:8069/tracking/map/[BOOKING_ID]`
3. แทน `[BOOKING_ID]` ด้วย ID ของการจองรถ

**ตัวอย่าง:**
```
http://localhost:8069/tracking/map/1
http://localhost:8069/tracking/map/42
```

### 🚗 Option 2: Simulate Vehicle Movement

ถ้ายังไม่มีข้อมูล GPS จริง ใช้สคริปต์จำลอง:

#### Step 1: แก้ไข Configuration
เปิดไฟล์ `simulate_vehicle_tracking.py` และแก้:

```python
# ⚙️ Configuration
DB_NAME = 'your_database_name'  # ⚠️ เปลี่ยนเป็นชื่อ DB ของคุณ
USERNAME = 'admin'              # ⚠️ เปลี่ยนเป็น username ของคุณ
PASSWORD = 'your_password'      # ⚠️ เปลี่ยนเป็น password ของคุณ
```

#### Step 2: Run Script
เปิด **Command Prompt** และรัน:

```cmd
cd "C:\Program Files\Odoo 18.0.20251009\server\custom-addons\transport_booking"
python simulate_vehicle_tracking.py
```

#### Step 3: เลือก Booking
สคริปต์จะแสดงรายการ Booking ที่มีสถานะ **confirmed** หรือ **in_progress**

#### Step 4: ดูผลลัพธ์
- เปิดเว็บเบราว์เซอร์
- ไปที่ `http://localhost:8069/tracking/map/[BOOKING_ID]`
- จะเห็นรถเคลื่อนที่จาก **Siam → Don Mueang Airport**

## 🎨 What You'll See

### 🖼️ Desktop View
```
┌─────────────────────────────────────────────────┐
│ Header: 🚚 Booking Name | 🟢 กำลังขนส่ง        │
├─────────────────────────────────────────────────┤
│ ┌─────────────┐              ┌──────────┐       │
│ │ Info Card   │              │ LIVE     │       │
│ │ 🎯 Pickup   │              │ 🔴       │       │
│ │ 📍 Dest     │    [ MAP ]   │ 5 วิ     │       │
│ │ 🚚 Vehicle  │              └──────────┘       │
│ │ 👤 Driver   │                                 │
│ └─────────────┘                                 │
├─────────────────────────────────────────────────┤
│ Stats: 60 km/h | 15.3 km | 15 นาที | 5.2 km    │
└─────────────────────────────────────────────────┘
```

### 📱 Mobile View
- Info Card แสดงแบบ full-width
- Stats Bar แสดง 3 columns
- ปุ่ม zoom/fullscreen ตามมาตรฐาน Mobile

## 🔧 Configuration with TransportUserSettings

### Model: `transport.user.settings`

| Field | Type | Description |
|-------|------|-------------|
| `tracking_enabled` | Boolean | เปิด/ปิดการติดตาม |
| `tracking_refresh_interval` | Integer | เวลา Refresh (5-300 วินาที) |
| `auto_center_map` | Boolean | ปรับแผนที่อัตโนมัติ |
| `show_route_history` | Boolean | แสดงเส้นทางที่ผ่านมา |
| `show_speed_indicator` | Boolean | แสดงความเร็ว |
| `notification_enabled` | Boolean | เปิดการแจ้งเตือน |

### How to Use Settings (Future Update)
```javascript
// JavaScript code ใน template จะดึงค่าจาก settings
const settings = await getUserSettings();
const refreshInterval = settings.tracking_refresh_interval * 1000;
setInterval(updateTracking, refreshInterval);
```

## 🐛 Troubleshooting

### ❌ Problem: แผนที่โหลดไม่ขึ้น
**Solution:**
1. เช็ค Google Maps API Key
2. ตรวจสอบ Console (F12) หา error

### ❌ Problem: ไม่มีไอคอนรถ
**Solution:**
1. ตรวจสอบว่ามี `current_latitude`, `current_longitude` หรือไม่
2. Run `simulate_vehicle_tracking.py` เพื่อสร้างข้อมูล

### ❌ Problem: ไม่มีจุดรับ/ปลายทาง
**Solution:**
1. ตรวจสอบว่ามี `pickup_latitude`, `destination_latitude` หรือไม่
2. ใช้ Google Maps Widget ใน Booking Form เพื่อ geocode address

### ❌ Problem: Script simulate ไม่ทำงาน
**Solution:**
1. ตรวจสอบ DB_NAME, USERNAME, PASSWORD
2. เช็คว่า Odoo service ทำงานอยู่
3. Run as Administrator

## 📊 Data Flow

```
┌─────────────────┐
│  Mobile App     │ (จำลองด้วย simulate_vehicle_tracking.py)
│  (GPS Tracker)  │
└────────┬────────┘
         │
         ▼ POST /api/tracking/update_location
┌─────────────────┐
│ Odoo Backend    │
│ - vehicle.tracking (create)
│ - vehicle.booking (update current_lat/lng)
└────────┬────────┘
         │
         ▼ Auto refresh every 5s
┌─────────────────┐
│  Web Browser    │
│  tracking_map_food_delivery_style
│  - Fetch booking data
│  - Fetch tracking data
│  - Update markers
└─────────────────┘
```

## 🚀 Next Steps

### 🔜 Planned Features
- [ ] **Real-time updates** ด้วย WebSocket
- [ ] **Notifications** เมื่อรถใกล้ถึง
- [ ] **Route optimization** แสดงเส้นทางที่ดีที่สุด
- [ ] **Multiple vehicles** แสดงหลายรถพร้อมกัน
- [ ] **Dark mode** สำหรับกลางคืน
- [ ] **Offline support** บันทึกข้อมูลเมื่อไม่มีเน็ต

### 🎨 Customization
แก้ไขได้ที่:
- **Template**: `views/tracking_map_food_delivery.xml`
- **Controller**: `controllers/tracking_controller.py`
- **Colors**: แก้ใน `<style>` tag
- **Icons**: แก้ใน `ICONS` object
- **Refresh interval**: แก้ `CONFIG.updateInterval`

## 📞 Support

ถ้ามีปัญหาหรือต้องการความช่วยเหลือ:
1. เช็ค Odoo logs: `C:\Program Files\Odoo 18.0.20251009\server\odoo.log`
2. เช็ค Browser Console (F12)
3. ดู Documentation ใน code comments

## 🎉 Credits

Created with ❤️ by Claude AI Assistant
Inspired by: Grab, LINE MAN, Uber Eats

---

**Happy Tracking! 🚚💨**
