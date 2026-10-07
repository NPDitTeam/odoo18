{
    "name": "NPD Tax Invoice Number by Payment Journal",
    "version": "18.0.1.0.0",
    "license": "LGPL-3",
    "category": "Accounting",
    "summary": "เลขใบกำกับภาษี (Tax Invoice Number) ของใบรับชำระ แยกเลขรันตามสมุดรายวันรับชำระ",
    # account_payment_sequence = แท็บเลขใบรับ/จ่ายชำระ (ใช้วิธีสร้างเลขรันแบบเดียวกัน)
    # l10n_th_account_tax = ตัวออก Tax Invoice Number (_get_tax_invoice_number)
    "depends": ["account_payment_sequence", "l10n_th_account_tax"],
    "data": [
        "views/account_journal_views.xml",
    ],
    "installable": True,
}
