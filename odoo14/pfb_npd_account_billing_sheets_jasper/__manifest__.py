{
    'name': 'ใบแจ้งหนี้ ค่าปรับหาย/ค่าปรับชำรุด/ค่าเช่าส่วนต่าง (Jasper)',
    'version': '18.0.1.0.0',
    'summary': 'Jasper billing sheet forms printed from invoices (lost / damaged penalty, rental difference)',
    'description': """
แปลงจาก Odoo 14 QWeb (pfb_npd_account_billing_sheets) เป็น Jasper พิมพ์จากหน้าใบแจ้งหนี้

- ใบแจ้งหนี้ค่าปรับหาย: ไล่รายการสินค้า ไม่มีภาษีหัก ณ ที่จ่าย
- ใบแจ้งหนี้ค่าปรับชำรุด: ไล่รายการสินค้า ไม่มีภาษีหัก ณ ที่จ่าย
- ใบแจ้งหนี้ค่าเช่าส่วนต่าง: บรรทัดสรุปเดียว มีภาษีหัก ณ ที่จ่าย 5% เฉพาะลูกค้านิติบุคคล

รูปแบบเดียวกับใบแจ้งหนี้/ใบวางบิล Jasper (ข้อมูลบัญชีรับเงิน + QR พร้อมเพย์ใช้ร่วมกัน)
    """,
    'author': 'NPD',
    'category': 'Accounting',
    'depends': [
        'account',
        'jasper_reports',
        # pfb_date_of_rent บนใบแจ้งหนี้/บรรทัด
        'pfb_npd_all_customs',
        # จำนวนเงินเป็นตัวอักษรไทย (เครื่อง o18 ไม่มีไลบรารี bahttext)
        'l10n_th_amount_to_text',
        # ข้อมูลบัญชีรับเงินต่อบริษัท, เลขพร้อมเพย์ (res.company.promptpay_id), รูป QR สำรอง
        'pfb_npd_sale_form_Billing_sheet_jasper',
    ],
    'data': [
        'data/report_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
