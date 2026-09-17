{
    'name': 'ใบแจ้งหนี้ค่าเช่าพื้นที่สำนักงาน (Jasper)',
    'version': '18.0.1.0.0',
    'summary': 'Jasper office space rental invoice form printed from invoices',
    'description': """
แปลงจาก Odoo 14 QWeb (pfb_npd_office_rent_billing_sheet) เป็น Jasper พิมพ์จากหน้าใบแจ้งหนี้

หัวเอกสาร/ยอดเงิน/ภาษีหัก ณ ที่จ่าย/บัญชีรับเงิน + QR ใช้ร่วมกับ pfb_npd_account_billing_sheets_jasper
ตารางไล่รายการจากใบแจ้งหนี้ และแสดงชื่อผู้พิมพ์เหนือ "ผู้วางบิล" แบบ o14
""",
    'author': 'NPD',
    'category': 'Accounting',
    'depends': [
        'pfb_npd_account_billing_sheets_jasper',  # jasper_abs_* (หัวกระดาษ ยอด QR รายการสินค้า ราคาถอด VAT)
        'pfb_npd_all_customs',                    # pfb_date_of_rent / pfb_quantity บนบรรทัดใบแจ้งหนี้
    ],
    'data': [
        'data/report_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
