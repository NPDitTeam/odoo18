# -*- coding: utf-8 -*-
{
    'name': 'ฟิลด์ต้นทางของรายงานค่าคอมมิชชั่น',
    'version': '18.0.1.0.0',
    'summary': 'เซลล์ผู้ติดต่อบนใบแจ้งหนี้/ใบสำคัญจ่าย และฟิลด์อื่นที่รายงานค่าคอมต้องใช้',
    'description': """
ฟิลด์ต้นทางของรายงานค่าคอมมิชชั่น
=================================
รายงานค่าคอม Sales ต้องรู้ว่ายอดแต่ละใบเป็นของเซลล์คนไหน ซึ่งใน Odoo 14
มาจากโมดูล ``npd_contact_type``, ``account_advance_sales_contact`` และ
``npd_print_select_account`` ที่ยังไม่ได้พอร์ตมา

โมดูลนี้รวมเฉพาะ "ฟิลด์ที่จำเป็นต่อการคิดค่าคอม" ไว้ที่เดียว
ไม่ได้ยกทั้งสามโมดูลมา เพราะส่วนที่เหลือเป็นเรื่องอื่น (วิซาร์ดพิมพ์เอกสาร ฯลฯ)

ฟิลด์ที่เพิ่ม
-------------
* ``account.move.sales_contact_id``   เซลล์ผู้ติดต่อ — คัดลอกจากใบสั่งขายอัตโนมัติ
* ``account.move.reason_code_id``     ประเภทสินค้า (ใช้แยกใบค่าปรับหาย/ชำรุด)
* ``account.voucher.branch_id``       สาขาของใบสำคัญจ่าย
* ``account.voucher.line.sales_contact_id``  เซลล์ที่รับผิดชอบค่าขนส่ง
* ``account.voucher.line.payment_date``      วันที่กำหนดจ่าย
* ``res.users.employee_code``         รหัสพนักงาน (อ่านจากทะเบียนพนักงาน)
    """,
    'category': 'Accounting',
    'author': 'NPD Group',
    'license': 'LGPL-3',
    'depends': [
        'account', 'sale',
        'account_voucher_npd',
        'scrap_reason_code',
        'multi_branch_management_aagam',
        'npd_hrms_base',
    ],
    'data': [
        'views/account_move_views.xml',
        'views/account_voucher_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
