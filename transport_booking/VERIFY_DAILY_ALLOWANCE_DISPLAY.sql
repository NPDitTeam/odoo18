-- ตรวจสอบค่าเบี้ยเลี้ยงในตาราง delivery_history
SELECT 
    id,
    name,
    partner_name,
    driver_name,
    vehicle_name,
    shipping_cost,
    travel_expenses,
    daily_allowance,
    state,
    completion_date
FROM delivery_history
WHERE daily_allowance > 0 OR daily_allowance IS NOT NULL
ORDER BY completion_date DESC
LIMIT 20;

-- นับจำนวนบันทึกที่มีค่าเบี้ยเลี้ยง
SELECT 
    'ทั้งหมด' as รายการ,
    COUNT(*) as จำนวน,
    SUM(daily_allowance) as รวมค่าเบี้ยเลี้ยง
FROM delivery_history
UNION ALL
SELECT 
    'มีค่าเบี้ยเลี้ยง > 0',
    COUNT(*),
    SUM(daily_allowance)
FROM delivery_history
WHERE daily_allowance > 0
UNION ALL
SELECT 
    'ค่าเบี้ยเลี้ยง IS NULL',
    COUNT(*),
    SUM(daily_allowance)
FROM delivery_history
WHERE daily_allowance IS NULL;

-- ตรวจสอบค่าเบี้ยเลี้ยงของการจอง BOOK-20251121-0018
SELECT 
    dh.id,
    dh.name,
    dh.daily_allowance,
    dh.travel_expenses,
    dh.shipping_cost,
    vb.daily_allowance as 'booking_daily_allowance',
    vb.travel_expenses as 'booking_travel_expenses'
FROM delivery_history dh
LEFT JOIN vehicle_booking vb ON dh.booking_id = vb.id
WHERE dh.name = 'BOOK-20251121-0018';
