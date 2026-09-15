# -*- coding: utf-8 -*-
{
    'name': 'NPD Thai Tax Report - Branch Filter',
    'version': '18.0.1.0.0',
    'summary': 'รายงานภาษี (Thai Tax Reports) เลือกประเภทภาษีซื้อ/ขาย และกรองตามสาขาได้',
    'description': """
เพิ่มในหน้า Thai Tax Reports
============================
* ประเภทภาษี: ภาษีขาย / ภาษีซื้อ - เลือก Tax Group แล้วระบบเติมเฉพาะภาษีประเภทนั้น
  (ภาษีซื้อกับภาษีขายจึงเลือกรวมกันไม่ได้)
* สาขา: ติ๊ก "ทุกสาขา" หรือเลือกสาขาเดียว
    - ภาษีซื้อ -> กรองด้วย "สาขาสำนักงานใหญ่" (โมดูล npd_head_office_branch)
      ของเอกสารต้นทาง Avance Clear / การรับ / บิลผู้ขาย
    - ภาษีขาย  -> กรองด้วย Branch ของเอกสารต้นทาง (การรับชำระ / ใบแจ้งหนี้)
* หัวรายงาน View / PDF / Excel แสดงสาขาที่เลือก
""",
    'category': 'Accounting',
    'author': 'NPD Dev',
    'license': 'AGPL-3',
    'depends': [
        'l10n_th_tax_report',
        'npd_head_office_branch',
    ],
    'data': [
        'views/tax_report_wizard_views.xml',
        'reports/tax_report_templates.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
