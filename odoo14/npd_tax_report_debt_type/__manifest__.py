{
    'name': 'NPD Thai Tax Report - Debt Type Columns',
    'version': '18.0.1.0.0',
    'summary': 'รายงานภาษี (Thai Tax Reports): เพิ่มคอลัมน์ประเภทหนี้ และประเภทหนี้ (บ้านเขียว)',
    'description': """
พอร์ตจาก o14 npd_tax_report_debt_type (pfb1)

ฝ่ายบัญชีขอให้รายงานภาษีบอกว่ารายการนี้เป็นหนี้ประเภทไหน

* ประเภทหนี้ = ช่อง "ประเภทสินค้า" (reason_code_id) ของใบแจ้งหนี้
* ประเภทหนี้ (บ้านเขียว) = bk_debt_type ของใบแจ้งหนี้ — o18 ยังไม่ได้พอร์ต
  baankheaw_debt_payment คอลัมน์นี้จึงว่างไปก่อน และจะมีค่าเองเมื่อติดตั้ง

เอกสารภาษีที่เกิดจากรายการรับชำระ อ่านค่าจากใบแจ้งหนี้ที่รายการนั้นตัดชำระ
    """,
    'category': 'Accounting',
    'author': 'NPD',
    'license': 'LGPL-3',
    'depends': ['l10n_th_tax_report', 'npd_commission_fields'],
    'data': [
        'reports/tax_report_templates.xml',
        'views/tax_report_view_list.xml',
    ],
    'installable': True,
    'auto_install': False,
}
