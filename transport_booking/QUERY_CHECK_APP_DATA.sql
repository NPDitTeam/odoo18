-- 🔍 ตรวจสอบข้อมูลที่ส่งมาจากแอป
-- ตรวจสอบบันทึกการติดตาม GPS และค่าเบี้ยเลี้ยง

-- ========================================
-- 1️⃣ ดูการบันทึกการติดตาม (tracking history)
-- ========================================
SELECT 
    id,
    booking_id,
    created_at as "เวลาบันทึก",
    latitude as "Lat",
    longitude as "Lng",
    speed as "ความเร็ว",
    status as "สถานะ",
    accuracy as "ความแม่นยำ GPS"
FROM vehicle_tracking
ORDER BY id DESC
LIMIT 20;

-- ========================================
-- 2️⃣ ดูข้อมูลการจัดส่งที่เสร็จสิ้น
-- ========================================
SELECT 
    id,
    name as "เลขที่จอง",
    state as "สถานะ",
    driver_id,
    driver_name as "ชื่อคนขับ",
    actual_pickup_time as "เวลารับของ",
    actual_delivery_time as "เวลาส่งถึง",
    delivery_timestamp as "GPS Timestamp",
    delivery_latitude as "Delivery Lat",
    delivery_longitude as "Delivery Lng",
    travel_expenses as "ค่าเที่ยว",
    daily_allowance as "ค่าเบี้ยเลี้ยง",
    shipping_cost as "ค่าขนส่ง",
    delivery_photo is not null as "มีรูปถ่าย?",
    receiver_name as "ผู้รับ",
    write_date as "อัปเดตล่าสุด"
FROM vehicle_booking
WHERE state IN ('done', 'cancelled')
ORDER BY id DESC
LIMIT 15;

-- ========================================
-- 3️⃣ ตรวจสอบค่าเบี้ยเลี้ยงที่ว่าง
-- ========================================
SELECT 
    id,
    name as "เลขที่จอง",
    state,
    driver_id,
    travel_expenses as "ค่าเที่ยว",
    daily_allowance as "ค่าเบี้ยเลี้ยง",
    shipping_cost,
    write_date
FROM vehicle_booking
WHERE state = 'done'
AND (daily_allowance IS NULL OR daily_allowance = 0)
ORDER BY id DESC
LIMIT 20;

-- ========================================
-- 4️⃣ เปรียบเทียบ booking กับ history
-- ========================================
SELECT 
    vb.id,
    vb.name as "เลขที่จอง",
    vb.state,
    vb.actual_delivery_time as "booking_actual_delivery_time",
    vb.daily_allowance as "booking_daily_allowance",
    vb.travel_expenses as "booking_travel_expenses",
    dh.id as "history_id",
    dh.actual_delivery_time as "history_actual_delivery_time",
    dh.daily_allowance as "history_daily_allowance",
    dh.travel_expenses as "history_travel_expenses",
    dh.completion_date
FROM vehicle_booking vb
LEFT JOIN delivery_history dh ON dh.booking_id = vb.id
WHERE vb.state = 'done'
ORDER BY vb.id DESC
LIMIT 15;

-- ========================================
-- 5️⃣ ดูค่า daily_allowance จาก transport_order
-- ========================================
SELECT 
    vb.id as "booking_id",
    vb.name as "booking_name",
    to_id.id as "order_id",
    to_id.name as "order_name",
    to_id.daily_allowance as "order_daily_allowance",
    vb.daily_allowance as "booking_daily_allowance",
    vb.state
FROM vehicle_booking vb
LEFT JOIN transport_order to_id ON to_id.id = vb.transport_order_id
WHERE vb.state = 'done'
ORDER BY vb.id DESC
LIMIT 15;

-- ========================================
-- 6️⃣ นับสถิติค่าเบี้ยเลี้ยง
-- ========================================
SELECT 
    COUNT(*) as "จำนวนการจองทั้งหมด",
    SUM(CASE WHEN daily_allowance > 0 THEN 1 ELSE 0 END) as "มีค่าเบี้ยเลี้ยง",
    SUM(CASE WHEN daily_allowance IS NULL OR daily_allowance = 0 THEN 1 ELSE 0 END) as "ไม่มีค่าเบี้ยเลี้ยง",
    ROUND(AVG(CASE WHEN daily_allowance > 0 THEN daily_allowance ELSE NULL END), 2) as "ค่าเบี้ยเลี้ยงเฉลี่ย",
    MIN(daily_allowance) as "ต่ำสุด",
    MAX(daily_allowance) as "สูงสุด"
FROM vehicle_booking
WHERE state = 'done';

-- ========================================
-- 7️⃣ ดูการจองล่าสุดพร้อมค่าใช้จ่าย
-- ========================================
SELECT 
    id,
    name,
    created_date as "สร้างเมื่อ",
    write_date as "อัปเดตเมื่อ",
    state,
    driver_name,
    CONCAT(
        'ค่าเที่ยว: ', travel_expenses,
        ' | ค่าเบี้ยเลี้ยง: ', daily_allowance,
        ' | ค่าขนส่ง: ', shipping_cost
    ) as "ค่าใช้จ่าย",
    actual_delivery_time
FROM vehicle_booking
ORDER BY created_date DESC
LIMIT 20;

-- ========================================
-- 8️⃣ ตรวจสอบการส่งรูปถ่าย
-- ========================================
SELECT 
    id,
    name,
    state,
    delivery_photo is not null as "มีรูปส่ง?",
    delivery_timestamp as "Timestamp รูป",
    delivery_latitude as "Lat",
    delivery_longitude as "Lng",
    receiver_signature is not null as "มีลายเซ็น?",
    receiver_name as "ชื่อผู้รับ",
    write_date
FROM vehicle_booking
WHERE state IN ('done', 'cancelled')
AND delivery_photo IS NOT NULL
ORDER BY id DESC
LIMIT 15;

-- ========================================
-- 9️⃣ ตรวจสอบ vehicle.tracking (GPS points)
-- ========================================
SELECT 
    id,
    booking_id,
    latitude,
    longitude,
    speed,
    status,
    created_at,
    accuracy
FROM vehicle_tracking
WHERE booking_id IS NOT NULL
ORDER BY id DESC
LIMIT 30;

-- ========================================
-- 🔟 สรุปข้อมูลรวม
-- ========================================
SELECT 
    'vehicle.booking' as "ตาราง",
    COUNT(*) as "ทั้งหมด",
    SUM(CASE WHEN state = 'done' THEN 1 ELSE 0 END) as "เสร็จ",
    SUM(CASE WHEN state = 'draft' THEN 1 ELSE 0 END) as "ร่าง",
    SUM(CASE WHEN state = 'in_progress' THEN 1 ELSE 0 END) as "กำลังจัดส่ง"
FROM vehicle_booking
UNION ALL
SELECT 
    'delivery.history',
    COUNT(*),
    SUM(CASE WHEN state = 'completed' THEN 1 ELSE 0 END),
    0,
    0
FROM delivery_history
UNION ALL
SELECT 
    'vehicle.tracking',
    COUNT(*),
    0,
    0,
    0
FROM vehicle_tracking;
