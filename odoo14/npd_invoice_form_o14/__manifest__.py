{
    'name': 'NPD: หัวฟอร์มใบแจ้งหนี้แบบ Odoo 14',
    'version': '18.0.1.0.0',
    'summary': 'จัดฟิลด์หัวฟอร์มใบแจ้งหนี้ให้ครบและเรียงแบบ o14',
    'description': """
จัดหัวฟอร์มใบแจ้งหนี้ (account.move) ให้เหมือน Odoo 14

- ซ้าย: ลูกค้า, ที่อยู่จัดส่ง, การอ้างอิงการชำระเงิน, Sale Type, Objective
- ขวา: วันที่ใบแจ้งหนี้, วันกำหนดจ่าย, สมุดรายวัน, Branch, Source Document, การติดต่อของลูกค้า,
  Sales ที่ติดต่อ, การชำระเงิน, วันที่เริ่มต้น/สิ้นสุดการเช่า, Document Type, ประเภทสินค้า,
  ประเภทการรับชำระหนี้, สถานะวางบิล
- ซ่อนช่องซ้ำ (สาขาบนหัวเอกสาร, Sales ที่ติดต่อ ตัวเก่าของ pfb_npd_all_customs)

ฟิลด์ที่ o18 ยังไม่มี ยกมาจาก o14 แบบฟิลด์ธรรมดา:
start_date / end_date (pfb_npd_add_date_account_move), document_type (npd_print_select_account)
""",
    'author': 'NPD',
    'category': 'Accounting',
    'depends': [
        'account',
        'pfb_npd_all_customs',             # pfb_so_type, pfb_objective_id, contact_type, sales_contact, debt_payment_type
        'npd_commission_fields',           # sales_contact_id, reason_code_id
        'npd_invoice_billing_status',      # billing_status / channel / evidence
        'custom_invoice_date',             # is_from_reservation
        'multi_branch_management_aagam',   # branch_id
        'npd_head_office_branch',          # head_office_branch_id
        'account_payment_invoice',         # payment_id
    ],
    'data': [
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
