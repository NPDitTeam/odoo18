# -*- coding: utf-8 -*-
{
    'name': 'NPD Loan Management - ระบบสินเชื่อ',
    'version': '18.0.1.6.0',
    'category': 'Accounting/Loans',
    'summary': 'ระบบจัดการสินเชื่อ พร้อมดอกเบี้ยล่าช้าและหลักฐานหลายไฟล์',
    'description': """
        ระบบจัดการสินเชื่อครบวงจร
        ===========================
        - จัดการข้อมูลสินเชื่อ
        - ประเภทสินเชื่อเพิ่มได้เอง (พร้อมตั้งค่าอัตราดอกเบี้ยล่าช้า)
        - รันเลขอัตโนมัติ
        - จัดการงวดชำระรายเดือน
        - **ดอกเบี้ยล่าช้า** - ตั้งค่าที่ประเภทสินเชื่อ คำนวณอัตโนมัติเมื่อเกินกำหนด
        - **หลักฐานการโอนหลายไฟล์** - แนบได้มากกว่า 1 ไฟล์ต่องวด
        - แนบเอกสารการกู้
        - ติดตามสถานะสินเชื่อ
        - จัดการค่าคอมมิชชั่น
        - ติดตามทรัพย์สิน
    """,
    'author': 'NPD Development',
    'website': '',
    'depends': ['base', 'mail', 'contacts'],
    'data': [
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/assets.xml',
        'wizard/loan_payment_wizard_views.xml',
        'wizard/loan_call_wizard_views.xml',
        'wizard/commission_payout_wizard_views.xml',
        'views/res_partner_views.xml',
        'views/npd_loan_type_views.xml',
        'views/npd_sale_commission_template_views.xml',
        'views/npd_loan_installment_views.xml',
        'views/npd_loan_views.xml',
        'views/menu.xml',
    ],
    'post_init_hook': 'recalculate_carried_interest',
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
