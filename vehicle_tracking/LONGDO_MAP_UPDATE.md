# Longdo Map Integration with Pulsing Dot Effect

## การเปลี่ยนแปลง

เปลี่ยนจาก Leaflet Map มาใช้ **Longdo Map API** พร้อม **Pulsing Dot Effect**

## คุณสมบัติใหม่

### 1. Pulsing Dot Animation
- จุดกะพริบแบบ pulse แสดงตำแหน่งรถ
- **สีเขียว** = เครื่องยนต์ทำงาน
- **สีแดง** = เครื่องยนต์ดับ

### 2. Direction Arrow
- ลูกศรแสดงทิศทางการเคลื่อนที่ของรถ
- หมุนตามค่า course ของรถ

### 3. Longdo Map Features
- แผนที่ประเทศไทยที่ละเอียด
- รองรับภาษาไทย
- API Key: `7b14be3925326c8779d890e55ac4bb0d`

## วิธีการอัพเดต

1. **หยุด Odoo Service** (ถ้ารันอยู่)
   ```
   1_stop_odoo.bat
   ```

2. **รัน Upgrade Script**
   ```
   upgrade_longdo_map.bat
   ```

3. **เริ่ม Odoo Service**
   ```
   3_start_odoo.bat
   ```

4. **รีเฟรชเบราว์เซอร์** และทดสอบดูแผนที่

## โครงสร้างโค้ด

```javascript
// Pulsing Dot Object
pulsingDot = {
    width: 150,
    height: 150,
    engineOn: true/false,  // กำหนดสี
    onAdd(),               // สร้าง canvas
    render()               // วาด animation
}

// Longdo Map Initialization
map = new longdo.Map({
    placeholder: document.getElementById('map'),
    zoom: 15
});

// เพิ่ม Pulsing Dot Layer
map.Renderer.addImage('pulsing-dot', pulsingDot);
map.Renderer.addSource('vehicle-point', geojsonData);
map.Renderer.addLayer({ id: 'vehicle-layer', ... });
```

## การทำงาน

1. โหลด Longdo Map API
2. สร้าง pulsingDot object พร้อม canvas animation
3. เมื่อแผนที่พร้อม ใส่ pulsing dot layer
4. อัพเดตตำแหน่งทุก 60 วินาที
5. เปลี่ยนสีตามสถานะเครื่องยนต์

## หมายเหตุ

- ใช้ Longdo Map API v3
- Animation ทำงานต่อเนื่องด้วย `map.Renderer.triggerRepaint()`
- รองรับการอัพเดตตำแหน่งแบบ real-time
