# -*- coding: utf-8 -*-
{
    'name': 'NPD Head Office Branch Mapping',
    'version': '18.0.1.0.0',
    'summary': 'กำหนดสาขาที่ให้ออกเอกสารในนาม "สำนักงานใหญ่" (บิลผู้ขาย / Avance Clear / การรับ)',
    'description': """
NPD Head Office Branch Mapping
==============================
เพิ่มเมนู "กำหนดค่าสาขา (สำนักงานใหญ่)" ไว้ที่ การกำหนดค่า ของแอปการออกใบแจ้งหนี้
กดแล้วจะเด้ง popup ให้กำหนดค่าแยกตามเมนู 3 เมนู

    * บิลผู้ขาย        (account.move ประเภท in_invoice / in_refund)
    * Avance Clear    (account.advance.clear)
    * การรับ           (account.voucher เฉพาะ check_type_show_selection = False)

วิธีทำงาน
---------
ในแต่ละเมนูจะกำหนด "รายชื่อสาขาที่ระบุ" ไว้ เช่น อยุธยา / ชะอำ / ภูเก็ต
เมื่อเอกสารในเมนูนั้นเลือก Branch เป็นสาขาใดสาขาหนึ่งในรายการ
ระบบจะเติมฟิลด์ใหม่ "สาขาสำนักงานใหญ่" ให้อัตโนมัติเป็นสาขาสำนักงานใหญ่ที่กำหนดไว้
ถ้าไม่ตรงรายการ จะใช้สาขาของเอกสารเอง (ปิดได้ที่ตัวเลือกในหน้ากำหนดค่า)

เคสย้อนหลัง
-----------
ปุ่ม "บันทึก + ปรับใช้ย้อนหลัง" จะไล่คำนวณเอกสารเก่าทั้งหมดใหม่
พร้อมเก็บประวัติทุกครั้งที่ปรับใช้ (ใครทำ เมื่อไหร่ ตั้งค่าอะไรไว้)
และเก็บรายการเอกสารที่ถูกเปลี่ยนค่า (ค่าเดิม -> ค่าใหม่) ไว้ตรวจสอบย้อนหลังได้
""",
    'category': 'Accounting',
    'author': 'NPD Dev',
    'license': 'AGPL-3',
    'depends': [
        'account',
        # res.branch + account.move.branch_id
        'multi_branch_management_aagam',
        # account.voucher (เมนู การรับ)
        'account_voucher_npd',
        # account.voucher.branch_id + ช่อง Branch บนฟอร์มการรับ
        'npd_commission_fields',
        'account_advance',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/head_office_branch_security.xml',
        'views/head_office_branch_config_views.xml',
        'views/head_office_branch_apply_log_views.xml',
        'views/account_move_views.xml',
        'views/account_advance_clear_views.xml',
        'views/account_voucher_views.xml',
        'views/res_users_views.xml',
        'views/head_office_branch_menus.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
