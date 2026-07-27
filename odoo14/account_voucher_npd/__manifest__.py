# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Sale & Purchase Vouchers NPD',
    'version': '18.0.1.1.0',
    'summary': 'Manage your debts and credits thanks to simple sale/purchase receipts',
    'description': """
    Module Sale & Purchase Voucher for create sale receipt and purchase receipt derect from customer and supplier
This module manages:

* Voucher Entry
* Voucher Receipt [Sales & Purchase]
* Voucher Payment [Customer & Vendors]
    """,
    'category': 'Accounting',
    'sequence': 20,
    'depends': [
        'account',
        'payment_method',
        'account_cheque',
        'l10n_th_tax_invoice',
        'account_journal_sequences',
        'withholding_tax_cert_amount',
        # ใช้เมนูตั้งค่าสมุดรายวัน (npd.invoice.journal.config)
        'pfb_npd_all_customs',
    ],
    'demo': [],
    'data': [
        'security/account_voucher_security.xml',
        'security/ir.model.access.csv',
        'views/account_voucher_views.xml',
        'views/account_cheque_view.xml',
        'data/account_voucher_data.xml',
    ],
    'auto_install': False,
    'installable': True,
    'license': 'LGPL-3',
}
