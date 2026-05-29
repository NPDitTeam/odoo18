# NPD Connection Settings - คู่มือการใช้งาน

## 📋 ภาพรวม
โมดูล **NPD Connection Settings** ให้คุณจัดการการเชื่อมต่อไปยังเซิร์ฟเวอร์ Odoo หลายเครื่องจากเมนูการตั้งค่า

## 🚀 ขั้นตอนการติดตั้ง

### 1. ติดตั้งโมดูลใน Odoo
```bash
# โมดูลอยู่ที่:
C:\Program Files\Odoo 18.0.20251009\server\custom-addons\npd_connection_settings
```

### 2. เปิดใช้งานโมดูล
1. ไปที่ **Apps** ใน Odoo
2. ค้นหา **NPD Connection Settings**
3. คลิก **Install**

### 3. เข้าหน้าการตั้งค่า
- ไปที่ **Settings** (การตั้งค่า)
- ไปที่ **Company** (บริษัท)
- จะเห็น **NPD Connection Settings** ในเมนู

## 📝 วิธีใช้งาน

### สร้างการตั้งค่าการเชื่อมต่อใหม่

1. ไปที่ **Settings > Company > NPD Connection Settings**
2. คลิก **Create** (สร้าง)
3. กรอกข้อมูลต่อไปนี้:

#### ข้อมูลการเชื่อมต่อเซิร์ฟเวอร์
- **Connection Name**: ชื่อของการเชื่อมต่อ (เช่น "NPD Main", "NPD Dev")
- **Server URL/IP**: URL หรือ IP ของเซิร์ฟเวอร์ (เช่น `https://npd-solution.com` หรือ `http://192.168.1.100:8070`)

#### ข้อมูลฐานข้อมูล
- **Database Name**: ชื่อฐานข้อมูล (เช่น `NPD_Logistics`)

#### ข้อมูลการยืนยันตัวตน
- **Username**: ชื่อผู้ใช้ Odoo (เช่น `Npd_admin`)
- **Password**: รหัสผ่าน Odoo

#### ข้อมูลเพิ่มเติม
- **Description**: หมายเหตุเพิ่มเติม (ไม่จำเป็น)
- **Active**: ตั้งเป็น True เพื่อใช้การเชื่อมต่อนี้

4. คลิก **Save** (บันทึก)

### เปลี่ยนการเชื่อมต่อที่ใช้งาน

1. เปิดการตั้งค่าการเชื่อมต่อที่ต้องการ
2. ตั้ง **Active** เป็น True
3. บันทึกการเปลี่ยนแปลง

### ตัวอย่างการตั้งค่า

#### NPD Main Server
```
Connection Name: NPD Main
Server URL/IP: https://npd-solution.com
Database Name: NPD_Logistics
Username: Npd_admin
Password: 1234
Active: True ✓
```

#### NPD Test Server
```
Connection Name: NPD Test
Server URL/IP: http://119.59.124.50:8070
Database Name: NPD_Logistics_Test
Username: Npd_admin
Password: 1234
Active: False
```

## 🔗 API Endpoints

Flutter App สามารถเรียกใช้ API เหล่านี้:

### ดึงการตั้งค่าที่ใช้งาน
```
GET /api/npd/connection/get_active
```

**Response:**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "name": "NPD Main",
    "server_url": "https://npd-solution.com",
    "database_name": "NPD_Logistics",
    "username": "Npd_admin",
    "password": "1234",
    "is_active": true
  }
}
```

### ดึงการตั้งค่าทั้งหมด
```
GET /api/npd/connection/get_all
```

### ตั้งการเชื่อมต่อให้เป็นแบบใช้งาน
```
POST /api/npd/connection/set_active/{connection_id}
```

## 📱 Flutter App Integration

### 1. ใช้ ConnectionManager
```dart
import 'package:npd_transport_app/services/connection_manager.dart';

// ดึงการตั้งค่าการเชื่อมต่อ
final config = await ConnectionManager.getActiveConnection();

// ใช้การตั้งค่า
final baseUrl = config?['server_url'];
final database = config?['database_name'];
final username = config?['username'];
final password = config?['password'];
```

### 2. เพิ่มเมนูการตั้งค่า
```dart
import 'package:npd_transport_app/screens/connection_settings_screen.dart';

// ในเมนูของ App
ListTile(
  title: const Text('Connection Settings'),
  onTap: () {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => const ConnectionSettingsScreen(),
      ),
    );
  },
),
```

## 🔄 Workflow

```
Flutter App
    ↓
  [ไม่มีการตั้งค่า?]
    ↓
  Odoo Connection Manager
    ↓
  Get Active Connection API
    ↓
  บันทึกใน SharedPreferences
    ↓
  ใช้ในการเชื่อมต่อกับ Odoo
```

## 🆘 Troubleshooting

### ปัญหา: ไม่พบการตั้งค่าการเชื่อมต่อ
**วิธีแก้:**
1. ตรวจสอบว่าติดตั้งและเปิดใช้งานโมดูล NPD Connection Settings แล้ว
2. สร้างการตั้งค่าการเชื่อมต่อใหม่
3. ตั้ง Active เป็น True

### ปัญหา: Flutter App ไม่สามารถเชื่อมต่อไปยังเซิร์ฟเวอร์
**วิธีแก้:**
1. ตรวจสอบ URL/IP ของเซิร์ฟเวอร์
2. ตรวจสอบรหัสผ่าน Username และ Password
3. ตรวจสอบชื่อฐานข้อมูล
4. ตรวจสอบการเชื่อมต่อเครือข่าย

## 📚 File Structure

```
npd_connection_settings/
├── __init__.py
├── __manifest__.py
├── models.py
├── controllers/
│   ├── __init__.py
│   └── connection_controller.py
├── security/
│   └── ir_model_access.xml
└── views/
    ├── connection_views.xml
    └── menu_items.xml
```

## 🔐 Security
- เฉพาะ System Admin เท่านั้นที่มองเห็นและแก้ไขได้
- รหัสผ่านเก็บเป็น Char field (หากต้องการ ให้เปลี่ยนเป็น Password field ใน Odoo)

## 📞 Support
สำหรับความช่วยเหลือ ติดต่อทีม NPD Solutions

---

**Last Updated:** 2025-01-09
**Version:** 1.0
