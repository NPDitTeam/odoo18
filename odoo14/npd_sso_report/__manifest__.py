# -*- coding: utf-8 -*-
{
    'name': 'NPD รายงานประกันสังคม + สรุปรายได้รายเดือน',
    'version': '18.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'ไฟล์ยื่นประกันสังคม (แยกชีตตามรหัสสาขา สปส.) และรายงานสรุปรายได้ต่อเดือนจากหน้าทำเงินเดือน (ตาม o14)',
    'description': """
พอร์ตจาก o14 (npd_sso_report) เมนูใต้ "เงินเดือน"
- กำหนดค่ารายงานประกันสังคม: เลขบัญชีนายจ้าง + จับคู่รหัสสาขา สปส. กับสาขา (รายบริษัท) — ดึงจาก o14 ผ่านตัวซิงก์ HR
- รายงานประกันสังคม: ไฟล์ .xlsx แยกชีตตามรหัสสาขา
- รายงานสรุปรายได้ต่อเดือน: รายได้ (รวมรายรับ) / ภงด.1 / ประกันสังคม (ฐานค่าจ้าง) / ยื่นประกันสังคม
""",
    'author': 'NPD',
    'depends': ['npd_hrms_payroll'],
    'data': [
        'security/ir.model.access.csv',
        'views/sso_config_views.xml',
        'wizard/sso_report_wizard_views.xml',
        'views/payroll_monthly_summary_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
}
