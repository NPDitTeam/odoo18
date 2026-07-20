-- =====================================================================
-- ทดสอบค่าเดินทาง (travel_expenses) ของพนักงาน รหัส 0357 (ณัฐพนธ์ หงษ์ทอง)
-- DB: NPD_Logistics (Odoo 18) | vehicle_booking JOIN vehicle_driver
-- รอบตัดเดือน 6/2026 = 25/05/2026 ถึง 24/06/2026
-- ⚠️ ฟิลด์วันที่ทุกตัวเก็บเป็น UTC ใน Postgres
-- =====================================================================

-- ---------------------------------------------------------------------
-- ★ ตัวชี้ขาด: รวมค่าเที่ยวในรอบตัด โดยลองทุกฟิลด์วันที่
--   payroll ใช้ planned_start_date_t (ควรได้ 3000)
--   ดูว่าฟิลด์ไหน = 3600 → นั่นคือคอลัมน์ที่คุณกรองในระบบ
-- ---------------------------------------------------------------------
SELECT 'planned_start_date_t (payroll ใช้)' AS date_field,
       COUNT(*) FILTER (WHERE vb.planned_start_date_t >= '2026-05-25' AND vb.planned_start_date_t < '2026-06-25') AS jobs,
       COALESCE(SUM(vb.travel_expenses) FILTER (WHERE vb.planned_start_date_t >= '2026-05-25' AND vb.planned_start_date_t < '2026-06-25'),0) AS total_travel
FROM vehicle_booking vb JOIN vehicle_driver vd ON vd.id = vb.driver_id
WHERE vb.state='done' AND vd.employee_code='0357'
UNION ALL
SELECT 'booking_date (วันที่จอง)',
       COUNT(*) FILTER (WHERE vb.booking_date >= '2026-05-25' AND vb.booking_date < '2026-06-25'),
       COALESCE(SUM(vb.travel_expenses) FILTER (WHERE vb.booking_date >= '2026-05-25' AND vb.booking_date < '2026-06-25'),0)
FROM vehicle_booking vb JOIN vehicle_driver vd ON vd.id = vb.driver_id
WHERE vb.state='done' AND vd.employee_code='0357'
UNION ALL
SELECT 'planned_start_date (วันที่วางแผนออก)',
       COUNT(*) FILTER (WHERE vb.planned_start_date >= '2026-05-25' AND vb.planned_start_date < '2026-06-25'),
       COALESCE(SUM(vb.travel_expenses) FILTER (WHERE vb.planned_start_date >= '2026-05-25' AND vb.planned_start_date < '2026-06-25'),0)
FROM vehicle_booking vb JOIN vehicle_driver vd ON vd.id = vb.driver_id
WHERE vb.state='done' AND vd.employee_code='0357'
UNION ALL
SELECT 'planned_end_date_t (วันเวลาส่งจริง)',
       COUNT(*) FILTER (WHERE vb.planned_end_date_t >= '2026-05-25' AND vb.planned_end_date_t < '2026-06-25'),
       COALESCE(SUM(vb.travel_expenses) FILTER (WHERE vb.planned_end_date_t >= '2026-05-25' AND vb.planned_end_date_t < '2026-06-25'),0)
FROM vehicle_booking vb JOIN vehicle_driver vd ON vd.id = vb.driver_id
WHERE vb.state='done' AND vd.employee_code='0357'
UNION ALL
SELECT 'actual_delivery_time (เวลาส่งถึงจริง)',
       COUNT(*) FILTER (WHERE vb.actual_delivery_time >= '2026-05-25' AND vb.actual_delivery_time < '2026-06-25'),
       COALESCE(SUM(vb.travel_expenses) FILTER (WHERE vb.actual_delivery_time >= '2026-05-25' AND vb.actual_delivery_time < '2026-06-25'),0)
FROM vehicle_booking vb JOIN vehicle_driver vd ON vd.id = vb.driver_id
WHERE vb.state='done' AND vd.employee_code='0357';


-- ---------------------------------------------------------------------
-- (เสริม) เผื่อ 3600 มาจากการรวม "ทุก state" ไม่ใช่ done อย่างเดียว
-- ---------------------------------------------------------------------
SELECT vb.state, COUNT(*) AS jobs, COALESCE(SUM(vb.travel_expenses),0) AS total_travel
FROM vehicle_booking vb JOIN vehicle_driver vd ON vd.id = vb.driver_id
WHERE vd.employee_code='0357'
  AND vb.planned_start_date_t >= '2026-05-25' AND vb.planned_start_date_t < '2026-06-25'
GROUP BY vb.state ORDER BY vb.state;
