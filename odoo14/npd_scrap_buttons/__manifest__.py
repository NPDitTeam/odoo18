# -*- coding: utf-8 -*-
{
    'name': 'NPD Scrap Buttons',
    'version': '18.0.1.1.0',
    'summary': 'Reset / Cancel / Repair workflow for Scrap Orders',
    'description': """
        Adds to Scrap Orders:
        - Reset to Draft button
        - Cancel button
        - Repair workflow (แจ้งซ่อม / ซ่อมสำเร็จ) for reason codes flagged
          as is_damage_repair on scrap.reason.code
    """,
    'category': 'Inventory',
    'author': 'NPD',
    'website': '',
    'license': 'LGPL-3',
    'depends': ['stock', 'scrap_reason_code', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/scrap_reason_code_views.xml',
        'views/stock_scrap_views.xml',
        'wizard/scrap_repair_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
