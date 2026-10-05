# -*- coding: utf-8 -*-
{
    'name': 'NPD HRMS - ลงบัญชีเงินเดือน',
    'version': '18.0.1.0.0',
    'summary': 'ลงบัญชีเงินเดือนจากรอบเงินเดือนเข้าบัญชีแยกประเภท แยกรายการบัญชีตามบริษัทของสลิป',
    'description': """
NPD HRMS - ลงบัญชีเงินเดือน
===========================
เดิมโมดูลเงินเดือนไม่สร้างรายการบัญชีเลย ฝ่ายบัญชีต้องทำ JV มือทุกเดือน

- ตั้งผังบัญชีเงินเดือนแยกรายบริษัท (เมนู การกำหนดค่า > การบัญชี > ผังบัญชีเงินเดือน)
  ปุ่ม "สร้างค่าเริ่มต้นจากผังบัญชี" จับคู่บัญชีจาก **ชื่อบัญชี** ไม่ใช่รหัส
  เพราะฝ่ายบัญชีเปลี่ยนรหัสได้ตลอด และรหัสของแต่ละผังไม่ตรงกัน
- รอบเงินเดือนที่อนุมัติ/จ่ายแล้ว กด "ลงบัญชีเงินเดือน" ดูตัวอย่างก่อน
  แล้วสร้างรายการบัญชี 1 ใบต่อ (รอบ, บริษัทของสลิป)
- ใช้ยอดจากบรรทัดสลิปเป็นหลัก ปัดเศษรายบรรทัด เศษต่ำกว่า 1 บาทเข้าเงินเดือนค้างจ่าย
- กันลงซ้ำ กลับรายการได้ แล้วลงใหม่ได้
    """,
    'category': 'Accounting',
    'author': 'NPD Group',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'npd_hrms_payroll',
    ],
    'data': [
        'security/payroll_account_security.xml',
        'security/ir.model.access.csv',
        'views/payroll_account_config_views.xml',
        'views/payroll_account_move_views.xml',
        'views/payroll_period_views.xml',
        'wizard/payroll_account_post_wizard_views.xml',
        'wizard/payroll_account_reverse_wizard_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
