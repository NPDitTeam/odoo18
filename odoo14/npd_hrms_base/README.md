# NPD HRMS บน Odoo 18 — ภาพรวมการพอร์ตจาก Odoo 14

พอร์ตระบบบุคคลจาก Odoo 14 (`npd_dev/employee_salary` + `hr_attendance_branch`)
มาที่ Odoo 18 พร้อมเปลี่ยนสถาปัตยกรรม 3 อย่างพร้อมกัน

---

## 1. ตัด PHP ออก — Odoo เป็นเจ้าของข้อมูลจริง

**เดิม**
```
แอป HR  →  PHP (npdhrms.com)  →  MySQL        ← แหล่งข้อมูลจริง
                                    ↑ ↓ cron
                                  Odoo 14      ← สำเนา
```
Odoo ดึงข้อมูลมาทีหลังด้วย cron แล้ว push กลับตอนแก้ไข → ข้อมูลสองชุด
ชนกันได้ Odoo เห็นช้า และกฎธุรกิจต้องเขียนซ้ำสองภาษา (PHP กับ Python) แล้วไม่ตรงกัน

**ตอนนี้**
```
แอป HR  →  Odoo 18 (REST /api/hrms/v1)  →  PostgreSQL   ← แหล่งข้อมูลจริงชุดเดียว
```
ไม่มี MySQL ไม่มี cron sync ไม่มีการ push กลับ
กฎธุรกิจอยู่ในโมเดลที่เดียว หน้าเว็บ Odoo กับแอปใช้กฎชุดเดียวกันเสมอ

## 2. หลายบริษัทใน DB เดียว (เดิมแยก DB ต่อบริษัท)

* `company` ที่เคยเป็น Selection ชื่อบริษัท 5 ค่า → `company_id` (`res.company`)
* มี `ir.rule` แยกข้อมูลรายบริษัททุกโมเดลหลัก
* **ค่าคอมมิชชั่นและค่าเที่ยวไม่ต้องยิง API ข้าม DB อีกแล้ว** — อ่านผ่าน ORM ตรง ๆ ได้เลย
  เพราะอยู่ DB เดียวกัน (ดูหัวข้อ "งานที่เหลือ")

## 3. รองรับการปล่อยเช่าระบบ (multi-tenant)

ค่าที่เคย hardcode เป็นของ NPD ย้ายมาเป็นข้อมูล/การตั้งค่าทั้งหมด:

| เดิม (ฝังในโค้ด) | ตอนนี้ |
|---|---|
| รหัสพนักงานเริ่มที่ 1352 | `res.company.hrms_employee_code_start` (+ prefix, padding) |
| ประกันสังคม 5% ช่วง 1,650–17,500 | `res.company.hrms_sso_*` |
| วันตัดรอบ 25 | `res.company.hrms_cutoff_start_day` |
| สิทธิ์วันลา 8 ประเภท เป็นคอลัมน์ตายตัว | `hrms.leave.type` + `hrms.leave.balance` (ข้อมูลหลัก) |
| สิทธิหยุดเสาร์ HQ 2 / สาขา 1 | `res.company.hrms_saturday_days_*` + ธง `res.branch.hr_is_head_office` |
| ประเภทการเพิ่มเวลา 10 ค่าตายตัว | `hrms.manual.time.reason` (ข้อมูลหลัก) |
| ลิสต์สาขา 27 ค่า / แผนก / ตำแหน่ง | `res.branch` / `hr.department.custom` / `hr.position.custom` |
| เวอร์ชันแอป + release notes ในไฟล์ PHP | `hrms.app.release` |
| URL API npdhrms.com | ไม่มีแล้ว |

---

## โมดูล

| โมดูล | เนื้อหา |
|---|---|
| `npd_hrms_base` | นโยบายบริษัท, สาขา (ต่อยอด `res.branch`), แผนก, ตำแหน่ง, **พนักงาน (`employee.salary`)**, ใบเตือน, ตารางงาน, วันหยุดประจำปี, สิทธิหยุดวันเสาร์, ค่าเบี้ยเลี้ยง, สายอนุมัติ, เวอร์ชันแอป |
| `npd_hrms_attendance` | ประเภท/สิทธิ์การลา, ลงเวลาเข้า-ออก, ใบลา, ขอเพิ่มเวลา |
| `npd_hrms_api` | REST API ให้แอปคุยกับ Odoo โดยตรง + token + กันเดา PIN |

ติดตั้ง: `-i npd_hrms_api` (ลากตัวอื่นมาให้เอง)

---

## การตัดสินใจที่ควรรู้

**คงชื่อโมเดลเดิมไว้** — `employee.salary`, `hr.attendance.branch`,
`hr.attendance.branch.leave`, `hr.manual.time.log`, `hr.work.schedule`,
`saturday.leave.config`, `allowance.management`, `employee.warning`,
`payroll.holiday` เพราะเอนจิน payroll (3,300 บรรทัด) และแอปอ้างชื่อพวกนี้อยู่

**สาขาใช้ `res.branch`** (จาก `multi_branch_management_aagam`) แทน `hr.branch.custom`
→ สาขาฝั่ง HR กับฝั่งขาย/บัญชี/สต๊อกเป็นตัวเดียวกัน คิดค่าคอมสาขาได้โดยไม่ต้อง map ชื่อ
ตาราง `hr.checkin.distance` เดิมยุบมาเป็นฟิลด์บน `res.branch` (พิกัด + รัศมี)

**`employee.salary` ยังแยกจาก `hr.employee`** แต่มี `hr_employee_id` ผูกไว้
→ ใช้ Attendance/Expense/Fleet มาตรฐานของ Odoo ร่วมได้ โดยข้อมูลเงินเดือนยังอยู่ที่เดียว

---

## บั๊ก/ช่องโหว่ของเดิมที่แก้ไปด้วย

1. **PIN ซ้ำกันได้** — แอปล็อกอินด้วย PIN อย่างเดียว ฝั่ง PHP ใช้
   `ORDER BY id DESC LIMIT 1` แปลว่าถ้า PIN ซ้ำ คนที่สร้างทีหลังแย่งบัญชีคนก่อนได้
   → เพิ่ม constraint ห้าม PIN ซ้ำ
2. **ไม่มีการจำกัดการเดา PIN** — PIN 6 หลักมีแค่ 1 ล้านแบบ ยิงไม่จำกัด = เดาเจอในไม่กี่ชั่วโมง
   → บล็อก 15 นาที เมื่อผิด 5 ครั้งจากต้นทางเดียวกัน
3. **ยิง `?user_id=123` อ่านข้อมูลคนอื่นได้** → token บอกตัวตน ดูของคนอื่นได้เฉพาะที่ตัวเองเป็นผู้อนุมัติ
4. **การบังคับกรอกจำนวนเงินไม่เคยทำงาน** — PHP เทียบสตริง `'ค่าเบี๊ยเลี้ยงออกนอกสถานที่'`
   ซึ่งสะกดไม่ตรงกับค่าจริง `'ค่าเบี้ยเลี้ยงออกนอกสถานที่'`
   → เปลี่ยนเป็นธง `requires_amount` บนเรคคอร์ด ไม่เทียบข้อความอีก
5. **ฝั่งเซิร์ฟเวอร์ไม่เคยตรวจรัศมีเช็คอิน** — ส่งค่ารัศมีให้แอปไปตรวจเอง
   → เซิร์ฟเวอร์คำนวณระยะและบันทึก `is_offsite` ไว้ให้ฝ่ายบุคคลตรวจย้อนหลัง
6. **`age` กรอกมือแล้วค้าง** → คำนวณจากวันเกิด
7. **ไฟล์แนบเปิดได้โดยไม่ต้องล็อกอิน** (`/uploads/…`) → ผ่าน endpoint ที่ตรวจสิทธิ์ก่อน

---

## โมดูลเงินเดือนและส่วนต่อขยาย

| โมดูล | เนื้อหา |
|---|---|
| `npd_hrms_payroll` | รอบทำเงินเดือน, สลิป, เอนจินคิดสาย/ขาด/ลา/OT, ภาษี, ประกันสังคม, เงินได้อื่นๆ, เงินประกันการทำงาน, **`payroll.policy`** ที่รวมสูตรทุกตัว |
| `npd_hrms_commission` | ตั้งค่าคอมมิชชั่นสาขา/Sales + ต่อเข้าสลิป |
| `npd_hrms_rental` | ผูกพนักงานกับคนขับ, ค่าเที่ยว/เบี้ยเลี้ยงจากงานขนส่ง-เช่า |

**สูตรทุกตัวตั้งค่าได้** ที่ `payroll.policy` — ตัวหารวัน/ชั่วโมง, อัตรา OT 3 แบบ,
เพดานลดหย่อนภาษีทุกช่อง, ขั้นบันไดภาษี, วิธีปัดเศษสาย/ออกก่อน, ช่วงพักเที่ยง
ค่าเริ่มต้นตรงกับระบบเดิมของ NPD และมี `effective_from` ให้สร้างฉบับใหม่เมื่อกฎหมายเปลี่ยน
โดยไม่กระทบสลิปย้อนหลัง (สลิปเก็บ `policy_id` + สำเนาขั้นภาษีไว้ในตัว)

**บุคคลพิเศษ** ตั้งบนบัตรพนักงาน (ยกเว้นภาษี / ล็อกภาษีคงที่ / ยกเว้น ปกส. /
ไม่คิดสาย / ไม่คิด OT) — เดิม Odoo 14 ฝังรหัสผู้บริหารไว้ใน `EXECUTIVE_TAX_CONFIG`
ต้องแก้โค้ดและ deploy ใหม่ทุกครั้งที่เปลี่ยนคน

---

## งานที่เหลือ

| งาน | หมายเหตุ |
|---|---|
| พอร์ต `npd_commission_report` | **ค่าคอมยังเป็น 0 จนกว่าจะพอร์ตตัวนี้** — เป็นแหล่งยอดขาย/ยอดเช่า (`npd.commission.report`, `npd.commission.report.sales`) `npd_hrms_commission` เตรียม adapter รออยู่แล้ว ตรวจก่อนเสมอว่ามีโมเดลไหม ถ้าไม่มีคืน 0 ไม่ error |
| ยกข้อมูลเก่า | สคริปต์ย้ายจาก MySQL (`npdhr_dbbase_npd`) + Odoo 14 มา Odoo 18 |
| ฝั่งแอป | เปลี่ยน base URL + แนบ token — ดู `npd_hrms_api/README.md` |

---

## แก้บั๊กในโมดูลอื่นระหว่างทาง

`npd_hrms_rental` ต้อง depends `vehicle_registration` + `transport_booking`
ซึ่ง **ติดตั้งบน Odoo 18 ไม่ผ่านมาก่อน** (ไฟล์ถูกพอร์ตไว้แต่ไม่เคยรันจริง) แก้ไปแล้ว 4 จุด:

1. `vehicle_registration/views/vehicle_views.xml` — menuitem อ้าง `action_notification_history` ก่อนที่ action จะถูกประกาศ (Odoo อ่าน XML ตามลำดับ) → ย้ายเมนูไปไว้หลัง action
2. `vehicle_registration/__manifest__.py` — ใช้ `res.users.is_approver` แต่ไม่ depends `user_approver` ที่ประกาศฟิลด์นั้น
3. `vehicle_registration/hooks.py` + `transport_booking/post_init_hook.py` — ลายเซ็น `post_init_hook(cr, registry)` เป็นแบบ Odoo 14, Odoo 17+ ใช้ `(env)` และ `ir.cron` ไม่มี `numbercall`/`doall` แล้ว
4. `transport_booking/__init__.py` — ประกาศ `post_init_hook` ใน manifest แต่ไม่ได้ import เข้ามา Odoo จึงหา hook ไม่เจอ
