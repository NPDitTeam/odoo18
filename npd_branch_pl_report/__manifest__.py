# -*- coding: utf-8 -*-
{
    'name': 'งบรายรับ-รายจ่ายรายสาขา',
    'version': '18.0.1.1.0',
    'category': 'Accounting',
    'summary': 'งบรายรับ-รายจ่ายรายสาขา แยกตามรหัสบัญชี x รายเดือน (ดึงจาก GL)',
    'description': """
งบรายรับ-รายจ่ายรายสาขา (Branch P&L by month)
=============================================
- เลือก ปี + สาขา แล้วออกรายงานแยกตามรหัสบัญชี x 12 เดือน + รวม
- ดึงจากบัญชีแยกประเภท (account.move.line) ที่ posted ของสาขานั้น
- แถวรายได้ / แถวรายจ่าย (บัญชีค่าใช้จ่าย + บัญชีภาษีซื้อ) / รวมรายจ่าย / คงเหลือ
- ตั้งค่าได้รายสาขาว่าไม่ต้องเอาบัญชีไหนมาคิด (เมนู ตั้งค่าบัญชีที่ไม่แสดง)
  บัญชีที่ตัดออกจะไม่แสดงและไม่ถูกนับใน 'รวมรายจ่าย' กับ 'คงเหลือ'
  สาขาที่ไม่ได้ตั้งค่าไว้ รายงานออกเหมือนเดิมทุกประการ

พอร์ตมาจากฝั่ง Odoo 14 สิ่งที่ต่าง
- o18 ไม่มี internal_type แล้ว เปลี่ยนไปใช้ account_type
  ('asset_receivable' / 'liability_payable')
- สมุดรายวันชื่อเดียวกันมีหลายตัว (ตัวละบริษัท) จึงใช้ทุกตัวที่ชื่อตรง
  ไม่ใช่เอาแค่ตัวแรกเหมือน o14 ซึ่งจะทำให้ยอดหาย
- ส่วนเงินเดือนดึงจาก npd.salary.branch.report.line ซึ่งยังไม่ได้พอร์ตมา o18
  ถ้ายังไม่มีจะข้ามส่วนนี้ไปเงียบ ๆ ตัวเลขอื่นยังออกครบ
  พอพอร์ตรายงานเงินเดือนมาแล้วส่วนนี้จะทำงานเองโดยไม่ต้องแก้โค้ด
""",
    'author': 'NPD',
    'depends': [
        'account',
        'multi_branch_management_aagam',
        'pfb_npd_all_customs',
        'account_advance',
        'account_voucher_npd',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/branch_pl_report_views.xml',
        'views/branch_pl_exclusion_views.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
