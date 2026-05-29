-- 🔍 ตรวจสอบค่าเบี้ยเลี้ยงในฐานข้อมูล

-- 1️⃣ ดูค่าเบี้ยเลี้ยงล่าสุด 20 รายการ
SELECT 
    id,
    name as "เลขที่จอง",
    state as "สถานะ",
    driver_name as "คนขับ",
    daily_allowance as "ค่าเบี้ยเลี้ยง",
    travel_expenses as "ค่าเที่ยว",
    shipping_cost as "ค่าขนส่ง",
    write_date as "อัปเดต"
FROM vehicle_booking
WHERE state = 'done'
ORDER BY id DESC
LIMIT 20;

-- 2️⃣ นับว่ามีค่าเบี้ยเลี้ยงกี่รายการ
SELECT 
    COUNT(*) as "ทั้งหมด",
    SUM(CASE WHEN daily_allowance > 0 THEN 1 ELSE 0 END) as "มีค่า",
    SUM(CASE WHEN daily_allowance IS NULL OR daily_allowance = 0 THEN 1 ELSE 0 END) as "ไม่มีค่า"
FROM vehicle_booking
WHERE state = 'done';

-- 3️⃣ ดูการจองที่ไม่มีค่าเบี้ยเลี้ยง
SELECT 
    id,
    name as "เลขที่จอง",
    driver_name as "คนขับ",
    daily_allowance as "ค่าเบี้ยเลี้ยง",
    travel_expenses as "ค่าเที่ยว",
    write_date
FROM vehicle_booking
WHERE state = 'done'
AND (daily_allowance IS NULL OR daily_allowance = 0)
LIMIT 20;

-- 4️⃣ เปรียบเทียบ vehicle_booking กับ delivery_history
SELECT 
    vb.name as "เลขที่จอง",
    vb.daily_allowance as "booking_daily_allowance",
    dh.daily_allowance as "history_daily_allowance",
    dh.id as "history_id"
FROM vehicle_booking vb
LEFT JOIN delivery_history dh ON dh.booking_id = vb.id
WHERE vb.state = 'done'
LIMIT 20;

-- 5️⃣ ดูค่าเบี้ยเลี้ยงจากตาราง transport_order
SELECT 
    to_id.id,
    to_id.name as "order_name",
    to_id.daily_allowance as "order_daily_allowance",
    vb.name as "booking_name",
    vb.daily_allowance as "booking_daily_allowance"
FROM transport_order to_id
LEFT JOIN vehicle_booking vb ON vb.transport_order_id = to_id.id
ORDER BY to_id.id DESC
LIMIT 20;
