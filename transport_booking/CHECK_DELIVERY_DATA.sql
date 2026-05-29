-- 🔍 ตรวจสอบข้อมูลการจัดส่งใน Odoo Database
-- ใช้กับ PostgreSQL (Odoo 18)

-- ===============================================
-- 1️⃣ ตรวจสอบการจองล่าสุด (vehicle.booking)
-- ===============================================
SELECT 
    id,
    name as "เลขที่จอง",
    state as "สถานะ",
    tracking_status as "สถานะติดตาม",
    planned_end_date_t as "วันเวลาส่งจริง(Planned)",
    actual_pickup_time as "เวลารับของจริง",
    actual_delivery_time as "เวลาส่งถึงจริง",
    delivery_timestamp as "Timestamp จากแอป(GPS)",
    travel_expenses as "ค่าเที่ยว",
    daily_allowance as "ค่าเบี้ยเลี้ยง",
    shipping_cost as "ค่าขนส่ง",
    delivery_photo is not null as "มีรูปส่งของ?",
    receiver_signature is not null as "มีลายเซ็น?",
    delivery_latitude,
    delivery_longitude
FROM vehicle_booking
ORDER BY id DESC
LIMIT 10;

-- ===============================================
-- 2️⃣ ตรวจสอบประวัติการจัดส่ง (delivery.history)
-- ===============================================
SELECT 
    id,
    name as "เลขที่จอง",
    state as "สถานะ",
    actual_pickup_time as "เวลารับของจริง",
    actual_delivery_time as "เวลาส่งถึงจริง",
    travel_expenses as "ค่าเที่ยว",
    daily_allowance as "ค่าเบี้ยเลี้ยง",
    shipping_cost as "ค่าขนส่ง",
    completion_date as "วันที่บันทึก",
    driver_name as "คนขับ",
    partner_name as "ลูกค้า"
FROM delivery_history
ORDER BY id DESC
LIMIT 10;

-- ===============================================
-- 3️⃣ ตรวจสอบการจองสมบูรณ์
-- ===============================================
SELECT 
    vb.id,
    vb.name,
    vb.state,
    vb.actual_delivery_time,
    dh.id as "history_id",
    dh.state as "history_state",
    dh.travel_expenses as "history_travel_expenses",
    dh.actual_delivery_time as "history_actual_delivery_time",
    dh.completion_date
FROM vehicle_booking vb
LEFT JOIN delivery_history dh ON dh.booking_id = vb.id
WHERE vb.state IN ('done', 'cancelled')
ORDER BY vb.id DESC
LIMIT 10;

-- ===============================================
-- 4️⃣ ตรวจสอบการจองที่ไม่มี actual_delivery_time
-- ===============================================
SELECT 
    id,
    name,
    state,
    actual_delivery_time,
    delivery_timestamp,
    created_date,
    write_date
FROM vehicle_booking
WHERE state = 'done'
AND actual_delivery_time IS NULL
ORDER BY id DESC;

-- ===============================================
-- 5️⃣ ตรวจสอบประวัติที่ไม่มี travel_expenses
-- ===============================================
SELECT 
    id,
    name,
    travel_expenses,
    daily_allowance,
    shipping_cost,
    state,
    completion_date
FROM delivery_history
WHERE (travel_expenses = 0 OR travel_expenses IS NULL)
AND state = 'completed'
ORDER BY id DESC
LIMIT 20;

-- ===============================================
-- 6️⃣ นับจำนวนรวม
-- ===============================================
SELECT 
    'vehicle.booking (ทั้งหมด)' as "ตาราง",
    COUNT(*) as "จำนวน"
FROM vehicle_booking
UNION ALL
SELECT 
    'vehicle.booking (เสร็จสิ้น)',
    COUNT(*)
FROM vehicle_booking
WHERE state = 'done'
UNION ALL
SELECT 
    'delivery.history (ทั้งหมด)',
    COUNT(*)
FROM delivery_history
UNION ALL
SELECT 
    'delivery.history (เสร็จสิ้น)',
    COUNT(*)
FROM delivery_history
WHERE state = 'completed';
