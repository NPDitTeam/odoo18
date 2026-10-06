{
    'name': 'NPD Partner Tax Branch Check',
    'version': '18.0.1.0.0',
    'summary': 'บังคับกรอกรหัสสาขา (Tax Branch) ของลูกค้านิติบุคคล',
    'description': """
พอร์ตจาก o14 npd_partner_tax_branch (pfb1)

ฝ่ายบัญชีแจ้งว่าใบกำกับภาษีของลูกค้านิติบุคคลต้องมีรหัสสาขา (สำนักงานใหญ่ = 00000)

* หน้าผู้ติดต่อ: Tax Branch เป็นช่องบังคับกรอกเมื่อเป็นบริษัท
* ใบสั่งขาย: เลือกลูกค้าที่เป็นบริษัทแต่ยังไม่มีรหัสสาขา ระบบเด้งหน้าต่างให้กรอก
  รหัสสาขา 5 หลักทันที แล้วบันทึกกลับไปที่ลูกค้า ถ้าปิดหน้าต่างโดยไม่กรอก
  ระบบจะล้างช่องลูกค้าในใบสั่งขายออก
    """,
    'category': 'Sales',
    'author': 'NPD',
    'license': 'LGPL-3',
    'depends': ['sale', 'l10n_th_partner'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_partner_views.xml',
        'wizard/tax_branch_wizard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'npd_partner_tax_branch/static/src/js/sale_order_tax_branch.js',
        ],
    },
    'installable': True,
    'auto_install': False,
}
