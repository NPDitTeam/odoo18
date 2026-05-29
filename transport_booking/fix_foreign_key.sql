-- ==========================================================
-- 🔧 Fix Foreign Key Violation in vehicle_tracking
-- ==========================================================
-- ลบ records ที่ driver_id ไม่มีจริง
-- ==========================================================

-- ขั้นตอนที่ 1: ดูจำนวน records ที่ invalid
SELECT COUNT(*) as invalid_count
FROM vehicle_tracking vt
WHERE NOT EXISTS (
    SELECT 1 FROM vehicle_driver vd
    WHERE vd.id = vt.driver_id
)
AND vt.driver_id IS NOT NULL;

-- ขั้นตอนที่ 2: ลบ records ที่ driver_id ไม่มีจริง
DELETE FROM vehicle_tracking
WHERE driver_id IS NOT NULL
AND driver_id NOT IN (
    SELECT id FROM vehicle_driver
);

-- ขั้นตอนที่ 3: ตรวจสอบว่าเสร็จแล้ว
SELECT COUNT(*) as remaining_invalid
FROM vehicle_tracking vt
WHERE NOT EXISTS (
    SELECT 1 FROM vehicle_driver vd
    WHERE vd.id = vt.driver_id
)
AND vt.driver_id IS NOT NULL;

-- ขั้นตอนที่ 4: ดูจำนวน records ทั้งหมดที่เหลือ
SELECT COUNT(*) as total_tracking_records
FROM vehicle_tracking;
