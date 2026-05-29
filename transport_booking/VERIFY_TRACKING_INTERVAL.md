# 🔍 ตรวจสอบ: แอปใช้ tracking_interval จาก Odoo จริงหรือไม่?

## ✅ สรุป: **ใช่! แอปใช้ค่าจาก tracking_interval ใน tracking.settings**

---

## 📊 Flow การทำงานทั้งหมด

### 1️⃣ Odoo Database (tracking.settings model)
```python
# File: models/vehicle_tracking.py (line 97)

class TrackingSettings(models.Model):
    _name = 'tracking.settings'
    
    tracking_interval = fields.Integer(
        'ช่วงเวลาการติดตาม (นาที)', 
        default=5,  # ✅ Default = 5 นาที
        help='ระยะเวลาในการส่งตำแหน่ง (นาที)'
    )
```

**ฐานข้อมูล:**
```sql
Table: tracking_settings
- user_id: 2
- tracking_interval: 5  (นาที)
- tracking_enabled: True
```

---

### 2️⃣ Odoo Model Method
```python
# File: models/vehicle_tracking.py (line 165)

@api.model
def get_user_settings(self, user_id):
    """ดึงการตั้งค่าของ user"""
    settings = self.get_or_create_settings(user_id)
    return {
        'tracking_enabled': settings.tracking_enabled,
        'tracking_interval': settings.tracking_interval,  # ✅ ส่งค่านี้
        'high_accuracy': settings.high_accuracy,
        # ... ฟิลด์อื่นๆ
    }
```

---

### 3️⃣ API Controller
```python
# File: controllers/tracking_controller.py (line 75)

@http.route('/api/settings/get', type='json', auth='user')
def get_user_settings_api(self, force_refresh=False, **kwargs):
    # ค้นหา settings ของ user
    settings_model = request.env['tracking.settings'].sudo()
    user_setting = settings_model.search([
        ('user_id', '=', request.env.user.id)
    ], limit=1)
    
    # Log ค่าที่ได้
    _logger.info(f'⏱️  tracking_interval from DB: {user_setting.tracking_interval} minutes')
    
    # เรียก method get_user_settings
    settings = settings_model.get_user_settings(request.env.user.id)
    
    return {
        'success': True,
        'data': settings  # ✅ ส่ง tracking_interval ไปให้แอป
    }
```

---

### 4️⃣ API Response
```json
{
  "result": {
    "success": true,
    "data": {
      "tracking_interval": 5,        // ✅ นาที (จาก DB)
      "tracking_enabled": true,
      "high_accuracy": true,
      "show_speed": true,
      "show_route": true,
      // ... ฟิลด์อื่นๆ
    }
  }
}
```

---

### 5️⃣ แอปมือถือ (OdooService)
```dart
// File: lib/services/odoo_service.dart (line 820)

Future<Map<String, dynamic>?> getTrackingSettings() async {
  final response = await http.post(
    Uri.parse('$baseUrl/api/settings/get'),  // ✅ เรียก API
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode({'jsonrpc': '2.0', 'params': {}}),
  );
  
  if (response.statusCode == 200) {
    final data = jsonDecode(response.body);
    if (data['result'] != null && data['result']['success'] == true) {
      return data['result']['data'];  // ✅ return tracking_interval
    }
  }
}
```

---

### 6️⃣ แอปมือถือ (TrackingSettings Model)
```dart
// File: lib/models/tracking_settings.dart (line 28)

factory TrackingSettings.fromJson(Map<String, dynamic> json) {
  final trackingMinutes = json['tracking_interval'] ?? 5;  // ✅ อ่านค่า (นาที)
  final trackingSeconds = trackingMinutes * 60;            // ✅ แปลงเป็นวินาที
  
  print('📋 [TrackingSettings] Loading from Odoo:');
  print('   🔑 Key: tracking_interval');
  print('   ⏱️  Value from Odoo: $trackingMinutes minutes');
  print('   ⏱️  Converted to: $trackingSeconds seconds');
  
  return TrackingSettings(
    trackingInterval: trackingSeconds,  // ✅ ใช้ค่านี้
    // ... ฟิลด์อื่นๆ
  );
}
```

---

### 7️⃣ แอปมือถือ (TrackingService)
```dart
// File: lib/services/tracking_service.dart (line 31)

Future<TrackingSettings?> loadSettings() async {
  final settingsData = await _odooService.getTrackingSettings();  // ✅ ดึงจาก API
  
  if (settingsData != null) {
    _settings = TrackingSettings.fromJson(settingsData);  // ✅ แปลงข้อมูล
    print('✅ [Tracking] Settings loaded');
    print('   - Interval: ${_settings!.trackingInterval}s');  // วินาที
    return _settings;
  }
}
```

---

### 8️⃣ แอปมือถือ (Timer)
```dart
// File: lib/services/tracking_service.dart (line 141)

Future<bool> startTracking(Booking booking) async {
  await loadSettings();  // โหลดการตั้งค่า
  
  // ตั้ง timer
  _trackingTimer = Timer.periodic(
    Duration(seconds: _settings!.trackingInterval),  // ✅ ใช้ค่านี้
    (_) {
      _sendCurrentLocation();  // ส่งตำแหน่งทุก X วินาที
    },
  );
  
  print('⏰ [Tracking] Timer started');
  print('   ⏱️  Update every ${_settings!.trackingInterval} seconds');
}
```

---

## ✅ สรุป Flow สมบูรณ์

```
1. Odoo DB
   tracking.settings.tracking_interval = 5 (นาที)
   
2. Model Method
   get_user_settings() → return {'tracking_interval': 5}
   
3. API Controller
   /api/settings/get → return tracking_interval
   
4. API Response
   {"result": {"data": {"tracking_interval": 5}}}
   
5. แอป OdooService
   getTrackingSettings() → return {'tracking_interval': 5}
   
6. แอป TrackingSettings
   fromJson() → trackingSeconds = 5 * 60 = 300
   
7. แอป TrackingService
   loadSettings() → _settings.trackingInterval = 300
   
8. แอป Timer
   Timer.periodic(Duration(seconds: 300)) → ส่งทุก 5 นาที
```

---

## 🧪 วิธีทดสอบว่าใช้ค่าจริง

### 1. เปลี่ยนค่าใน Odoo
```sql
-- ใน Odoo shell
UPDATE tracking_settings 
SET tracking_interval = 10 
WHERE user_id = 2;

-- ตรวจสอบ
SELECT user_id, tracking_interval FROM tracking_settings;
```

### 2. Restart Odoo
```batch
net stop odoo-server-18.0
net start odoo-server-18.0
```

### 3. ดู Log ใน Odoo
```
⚙️ [Settings API] GET request received
   👤 User: Admin (ID: 2)
   ✅ Found settings record ID: 1
   ⏱️  tracking_interval from DB: 10 minutes
```

### 4. ดู Log ในแอป
```
📋 [TrackingSettings] Loading from Odoo:
   🔑 Key: tracking_interval
   ⏱️  Value from Odoo: 10 minutes
   ⏱️  Converted to: 600 seconds

⏰ [Tracking] Setting up location update timer
   ⏱️  Update every 600 seconds
```

### 5. ตรวจสอบผลลัพธ์
```
แอปควรส่งตำแหน่งทุก 10 นาที แทน 5 นาที
```

---

## 📝 ตัวอย่างค่าต่างๆ

| Odoo (นาที) | API Response | แอป (วินาที) | ความถี่ |
|-------------|--------------|--------------|---------|
| 1           | 1            | 60           | ทุก 1 นาที |
| 5 (default) | 5            | 300          | ทุก 5 นาที |
| 10          | 10           | 600          | ทุก 10 นาที |
| 30          | 30           | 1800         | ทุก 30 นาที |

---

## ✅ คำตอบ

**ใช่! แอปใช้ค่าจากฟิลด์ `tracking_interval` ในตาราง `tracking.settings` ของ Odoo 100%**

### หลักฐาน:
1. ✅ Model มีฟิลด์ tracking_interval (default=5)
2. ✅ Method get_user_settings() return ค่านี้
3. ✅ API Controller เรียก method นี้
4. ✅ แอปเรียก API และใช้ค่าที่ได้
5. ✅ มี log ทุกขั้นตอนเพื่อยืนยัน

### การทำงาน:
- เปลี่ยนค่าใน Odoo (เช่น 30 นาที)
- แอปจะส่งตำแหน่งทุก 30 นาที
- ไม่ต้อง rebuild แอป

---

## 🔧 สคริปต์ตรวจสอบ

ใช้สคริปต์นี้เพื่อทดสอบ:
```bash
# ดูค่าปัจจุบันใน Odoo
python check_tracking_interval.py
```

ไฟล์นี้จะแสดง:
- ค่า tracking_interval ของแต่ละ user
- API response
- การแปลงหน่วย (นาที → วินาที)
