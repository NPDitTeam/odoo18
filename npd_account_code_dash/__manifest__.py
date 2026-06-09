# -*- coding: utf-8 -*-
{
    'name': 'NPD Account Code – Allow Dash',
    'version': '18.0.1.0.0',
    'summary': 'Allow the dash "-" character in account codes (Odoo 14 compatibility)',
    'description': """
Allow dash in account codes
===========================
Odoo 17/18 restricts account codes to alphanumeric characters and dots only
(regex ^[A-Za-z0-9.]+$). Charts of accounts migrated from Odoo 14 often use
dashes (e.g. 1111-00). This module relaxes the validation so codes may also
contain "-", without patching Odoo core.
    """,
    'category': 'Accounting',
    'author': 'NPD',
    'depends': ['account'],
    'data': [],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
