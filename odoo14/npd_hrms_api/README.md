# NPD HRMS — API สำหรับแอป HR (Odoo 18)

แทน PHP ทั้งชุดบน `npdhrms.com/api` ด้วย controller ของ Odoo
ทุก endpoint อยู่ใต้ **`/api/hrms/v1`**

---

## สิ่งที่เปลี่ยนจากเดิม

| หัวข้อ | เดิม (PHP + MySQL) | ตอนนี้ (Odoo 18) |
|---|---|---|
| แหล่งข้อมูลจริง | MySQL `npdhr_dbbase_npd` — Odoo ดึงตามทีหลังด้วย cron | Odoo (PostgreSQL) ชุดเดียว |
| การยืนยันตัวตน | ไม่มี (บาง endpoint ใช้ HTTP Basic ที่ฝัง user/pass ในโค้ดแอป) | Bearer token ผูกกับพนักงาน + อุปกรณ์ มีวันหมดอายุ |
| กันเดา PIN | ไม่มี | บล็อก 15 นาที เมื่อผิด 5 ครั้งจากต้นทางเดียวกัน |
| ดูข้อมูลคนอื่น | ยิง `?user_id=123` ก็เห็นของคนอื่นได้ | token บอกว่าเป็นใคร — ดูของคนอื่นได้เฉพาะที่ตัวเองเป็นผู้อนุมัติ |
| กฎธุรกิจ | เขียนซ้ำสองที่ (PHP กับ Odoo) แล้วไม่ตรงกัน | อยู่ในโมเดลที่เดียว หน้าเว็บกับแอปใช้ร่วมกัน |
| ไฟล์แนบ | วางไว้ใน `/uploads/` เข้าถึงได้โดยไม่ต้องล็อกอิน | ผ่าน endpoint ที่ตรวจสิทธิ์ก่อนเสมอ |

---

## รายการ Endpoint

### ไม่ต้องล็อกอิน

| Method | Path | แทนไฟล์เดิม |
|---|---|---|
| GET | `/version` | `get_latest_version_test.php` |
| POST | `/login` | `api_login_pin_test1.php` |

**POST `/login`**
```json
{ "pin": "123456", "device_id": "abc-123" }
```
ตอบกลับ — เพิ่ม `token` และ `expires_at` จากของเดิม ส่วน `user` คีย์เหมือนเดิมทุกตัว
```json
{
  "status": "success",
  "message": "ล็อกอินสำเร็จ",
  "token": "…",
  "expires_at": "2026-09-12T…",
  "user": { "id": 42, "employee_code": "1352", "username": "…",
            "firstname": "…", "lastname": "…", "department": "…",
            "position": "…", "branch": "…", "company": "…",
            "status": "active", "device_id": "abc-123" },
  "is_approver": false,
  "mode": "production"
}
```

### ต้องแนบ token

ทุก request ต่อจากนี้ต้องมี header:
```
Authorization: Bearer <token>
X-Device-Id: <device_id>
```

| Method | Path | แทนไฟล์เดิม |
|---|---|---|
| POST | `/logout` | — (ของใหม่) |
| GET | `/menu` | `menu_data_test.php` |
| GET | `/employee/profile` | `/api/employee_info` |
| GET | `/checkin/status` | `api_checkin_status1.php` |
| POST | `/checkin` | `api_checkin_save_test1.php` |
| GET | `/checkin/history?month&year` | `get_checkin_history.php` |
| GET | `/leave/allowance` | `get_leave_allowance.php` |
| GET | `/leave/allowance/check?leave_type` | `check_leave_allowance.php` |
| GET | `/leave/types` | — (ของใหม่ แทนลิสต์ที่ hardcode ในแอป) |
| GET | `/leave/requests?month&year&limit` | `leave_requests.php` (GET) |
| POST | `/leave/requests` | `submit_leave_request_test.php` |
| POST | `/leave/requests/cancel` | `cancel_leave_request_test.php` |
| GET | `/leave/approvals` | `approve_leave_screen_test.php` (GET) |
| POST | `/leave/approvals/action` | `approve_leave_screen_test.php` (POST) |
| GET | `/leave/attachment/<id>` | ไฟล์ใน `/uploads/` |
| GET | `/manual_time?month&year&limit` | `manual_time_logs_test.php` (GET) |
| POST | `/manual_time` | `manual_time_logs_test.php` (POST) |
| POST | `/manual_time/cancel` | `cancel_manual_time_log.php` |
| GET | `/manual_time/approvals` | `approve_add_time_screen_test.php` (GET) |
| POST | `/manual_time/approvals/action` | `approve_add_time_screen_test.php` (POST) |
| GET | `/manual_time/attachment/<id>` | ไฟล์ใน `/uploads/manual_time_logs/` |
| GET | `/allowance_types` | `api_medical_expense.php` / callKw เดิม |
| GET | `/work_schedule` | `/api/work_schedule` |
| GET | `/holidays?year` | callKw `payroll.holiday` เดิม |
| GET | `/saturday_quota` | callKw `saturday.leave.config` เดิม |
| GET | `/warnings` | callKw `employee.warning` เดิม |
| GET | `/approvers` | — (ของใหม่) |
| GET/POST | `/payslip?month&year` | `get_payslip_data.php` — **ต้องติดตั้ง `npd_hrms_payroll` ก่อน** |

---

## หมายเหตุสำหรับคนแก้ฝั่งแอป

1. **`user_id` เปลี่ยนความหมาย** — เดิมคือ `users.id` ของ MySQL ตอนนี้คือ
   `employee.salary.id` ของ Odoo ค่าที่ได้จาก `/login` (`user.id`) ใช้ต่อได้เหมือนเดิม
   แต่ที่จริงแอปไม่ต้องส่ง `user_id` แล้ว เพราะ token บอกว่าเป็นใครอยู่แล้ว
   (ยังส่งมาได้ ระบบจะไม่สนใจ)

2. **คีย์ที่สะกดผิดคงไว้ตามเดิม** — `leave_statr_time` ยังเป็น `leave_statr_time`
   เพื่อให้แอปเวอร์ชันที่ผู้ใช้ติดตั้งอยู่ parse ได้ (รับ `leave_start_time` ด้วย)

3. **`file_path` เป็น URL ของ Odoo แล้ว** — ต้องแนบ token ตอนโหลดไฟล์
   (เดิมเป็นลิงก์สาธารณะบน npdhrms.com ที่ใครก็เปิดได้)

4. **ประเภทการลา/ประเภทการเพิ่มเวลา ดึงจาก API ได้แล้ว** — เลิก hardcode ในแอปได้
   เรียก `/leave/types` และ (ประเภทเพิ่มเวลาอยู่ใน `/allowance_types` + master data)

5. **สถานะยังเป็นภาษาไทยเหมือนเดิม** — `รออนุมัติ` / `อนุมัติ` / `ไม่อนุมัติ` / `ยกเลิก`

---

## การจัดการจากฝั่ง Odoo

* **ระบบบุคคล → ตั้งค่า → Token แอป HR** — ดูว่าใครล็อกอินจากเครื่องไหน เพิกถอนได้ทันทีเมื่อเครื่องหาย
* **บัตรพนักงาน → แท็บ "การเข้าใช้แอป"** — ดู/สุ่ม PIN, รีเซ็ต Device ID, ปลดล็อกบัญชี
* **ระบบบุคคล → ตั้งค่า → เวอร์ชันแอป HR** — ประกาศเวอร์ชันใหม่และ release notes
  (เดิมต้องแก้ไฟล์ PHP บนเซิร์ฟเวอร์)
