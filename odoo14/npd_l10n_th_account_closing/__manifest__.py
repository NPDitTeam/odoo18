{
    "name": "NPD - Thai Accounting Closing Setup",
    "summary": "รวมโมดูลปิดงบแบบไทย (งบการเงิน/สินทรัพย์/ภ.ง.ด.) + ตั้งค่าเริ่มต้นตาม o14",
    "description": """
ติดตั้งโมดูลเดียวได้ครบชุดที่ใช้ปิดงบบน Odoo 18:
- งบทดลอง / แยกประเภท / ลูกหนี้-เจ้าหนี้คงค้าง (account_financial_report)
- งบแสดงฐานะการเงิน / งบกำไรขาดทุนแบบไทย (mis_builder + l10n_th_mis_report)
- ทะเบียนสินทรัพย์และค่าเสื่อม (account_asset_management + l10n_th_account_asset_management)
- รายงาน ภ.ง.ด.1/1ก/2/3/53 + ไฟล์ยื่นกรมสรรพากร (npd_l10n_th_wht_report)

ตอนติดตั้งจะตั้งค่าให้ทุกบริษัท (รันซ้ำได้ ไม่สร้างซ้ำ):
- สมุดรายวันภาษีเกณฑ์เงินสด = CABA (สมุดรายวันกลับรายการภาษี) แบบ o14
- ภาษีหัก ณ ที่จ่าย ภ.ง.ด.3/53 และภาษีถูกหัก ณ ที่จ่าย อัตรา 1/2/3/5%
- ช่วงวันที่ ปีบัญชี/รายเดือน (สร้างล่วงหน้าอัตโนมัติทุกวัน)
- กลุ่มสินทรัพย์ตาม o14 (จับคู่บัญชีด้วยรหัส)
- รายงาน MIS งบแสดงฐานะการเงิน/งบกำไรขาดทุน ต่อบริษัท
""",
    "version": "18.0.1.0.0",
    "author": "NPD",
    "license": "AGPL-3",
    "category": "Accounting",
    "depends": [
        "account_payment_invoice",
        "l10n_th_account_tax",
        "l10n_th_account_wht_cert_form",
        "npd_l10n_th_wht_report",
        "date_range",
        "account_financial_report",
        "mis_builder",
        "l10n_th_mis_report",
        "account_asset_management",
        "l10n_th_account_asset_management",
    ],
    "data": [],
    "post_init_hook": "post_init_hook",
    "installable": True,
}
