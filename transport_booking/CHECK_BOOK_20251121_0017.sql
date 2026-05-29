-- 🔍 ตรวจสอบการจอง BOOK-20251121-0017

-- 1️⃣ ดูข้อมูลการจองทั้งหมด
SELECT 
    id,
    name as "เลขที่จอง",
    state as "สถานะ",
    tracking_status as "สถานะติดตาม",
    driver_id,
    driver_name as "ชื่อคนขับ",
    vehicle_id,
    vehicle_name as "ทะเบียนรถ",
    partner_name as "ลูกค่า",
    pickup_location as "ต้นทาง",
    destination as "ปลายทาง",
    distance_km as "ระยะทาง",
    actual_pickup_time as "เวลารับของ",
    actual_delivery_time as "เวลาส่งถึง",
    delivery_timestamp as "GPS Timestamp",
    delivery_latitude as "Delivery Lat",
    delivery_longitude as "Delivery Lng",
    travel_expenses as "ค่าเที่ยว",
    daily_allowance as "ค่าเบี้ยเลี้ยง",
    shipping_cost as "ค่าขนส่ง",
    delivery_photo is not null as "มีรูป?",
    receiver_name as "ผู้รับ",
    receiver_signature is not null as "มีลายเซ็น?",
    created_date as "สร้างเมื่อ",
    write_date as "อัปเดตเมื่อ"
FROM vehicle_booking
WHERE name = 'BOOK-20251121-0017';

-- 2️⃣ ดูประวัติการจัดส่ง (delivery_history)
SELECT 
    id,
    name as "เลขที่จอง",
    state as "สถานะ",
    driver_name as "คนขับ",
    vehicle_name as "รถ",
    partner_name as "ลูกค้า",
    pickup_location as "ต้นทาง",
    destination as "ปลายทาง",
    distance_km as "ระยะทาง",
    actual_pickup_time as "เวลารับของ",
    actual_delivery_time as "เวลาส่งถึง",
    travel_expenses as "ค่าเที่ยว",
    daily_allowance as "ค่าเบี้ยเลี้ยง",
    shipping_cost as "ค่าขนส่ง",
    receiver_name as "ผู้รับ",
    completion_date as "วันที่เสร็จสิ้น"
FROM delivery_history
WHERE name = 'BOOK-20251121-0017';

-- 3️⃣ ดูการติดตาม GPS (vehicle_tracking)
SELECT 
    id,
    booking_id,
    latitude as "Lat",
    longitude as "Lng",
    speed as "ความเร็ว",
    accuracy as "ความแม่นยำ",
    status as "สถานะ",
    created_at as "เวลา"
FROM vehicle_tracking
WHERE booking_id = (SELECT id FROM vehicle_booking WHERE name = 'BOOK-20251121-0017')
ORDER BY created_at DESC;

-- 4️⃣ ดูข้อมูล transport_order ที่เกี่ยวข้อง
SELECT 
    vb.name as "booking_name",
    to_id.id as "order_id",
    to_id.name as "order_name",
    to_id.trip_allowance as "trip_allowance",
    to_id.daily_allowance as "order_daily_allowance",
    vb.travel_expenses as "booking_travel_expenses",
    vb.daily_allowance as "booking_daily_allowance"
FROM vehicle_booking vb
LEFT JOIN transport_order to_id ON to_id.id = vb.transport_order_id
WHERE vb.name = 'BOOK-20251121-0017';

-- 5️⃣ ดูเปรียบเทียบ booking กับ history
SELECT 
    'booking' as "ตาราง",
    vb.name,
    vb.daily_allowance as "daily_allowance",
    vb.travel_expenses as "travel_expenses",
    vb.actual_delivery_time as "actual_delivery_time",
    vb.delivery_timestamp as "delivery_timestamp",
    vb.state as "state"
FROM vehicle_booking vb
WHERE vb.name = 'BOOK-20251121-0017'

UNION ALL

SELECT 
    'history',
    dh.name,
    dh.daily_allowance,
    dh.travel_expenses,
    dh.actual_delivery_time,
    NULL as "delivery_timestamp",
    dh.state
FROM delivery_history dh
WHERE dh.name = 'BOOK-20251121-0017';

-- 6️⃣ สรุปข้อมูลทั้งหมด
SELECT 
    'vehicle_booking' as "ตาราง",
    COUNT(*) as "มี record?"
FROM vehicle_booking
WHERE name = 'BOOK-20251121-0017'

UNION ALL

SELECT 
    'delivery_history',
    COUNT(*)
FROM delivery_history
WHERE name = 'BOOK-20251121-0017'

UNION ALL

SELECT 
    'vehicle_tracking',
    COUNT(*)
FROM vehicle_tracking
WHERE booking_id = (SELECT id FROM vehicle_booking WHERE name = 'BOOK-20251121-0017');
