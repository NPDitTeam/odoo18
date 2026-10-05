# -*- coding: utf-8 -*-
{
    'name': 'ใบลา NPD/HR.03 (Jasper)',
    'version': '18.0.1.0.0',
    'summary': 'พิมพ์ใบลาจากหน้าจอการลา และให้แอปดาวน์โหลดใบลาเป็น PDF',
    'description': """
ใบลา NPD/HR.03 (Jasper)
=======================
แบบฟอร์มใบลาเดียวกับฝั่ง Odoo 14 (hr_attendance_branch) ตามที่ฝ่ายบุคคลกำหนด

* ตัดช่องหมายเหตุ / เอกสารประกอบใบลา / ช่องเจ้าหน้าที่บันทึก / ลายเซ็นกรรมการผู้จัดการ
* ช่องพิจารณามี รออนุมัติ / สมควร / ไม่สมควร ติ๊กตามสถานะจริง
* ตารางประเภทการลาใช้ประเภทการลาของบริษัทพนักงาน (hrms.leave.type) ไม่ใช่ 4 ช่องในกระดาษ
* แอปดาวน์โหลดผ่าน GET /api/hrms/v1/leave/requests/<id>/pdf (เจ้าของใบหรือผู้อนุมัติ)

ไม่เก็บไฟล์ไว้บนเรคคอร์ด — ออกจากข้อมูลล่าสุดทุกครั้ง ใบที่ซิงก์ทับจาก o14
หรือเปลี่ยนสถานะภายหลังจึงไม่มีไฟล์ค้างรุ่นเก่า
    """,
    'category': 'Human Resources',
    'author': 'NPD Group',
    'license': 'LGPL-3',
    'depends': [
        'jasper_reports',
        'npd_hrms_attendance',
        'npd_hrms_api',
    ],
    'data': [
        'data/report_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
