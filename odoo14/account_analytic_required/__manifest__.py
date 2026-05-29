# Copyright Akretion - Alexis de Lattre
# Copyright Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)
{
    "name": "Account Analytic Required",
    "version": "18.0.1.0.0",
    "category": "Analytic Accounting",
    "license": "AGPL-3",
    "author": "Akretion, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/account-analytic",
    "depends": ["account", "analytic", "multi_branch_management_aagam"],
    "data": [
        "views/account_account_views.xml",
        "views/account_analytic_account_views.xml",
    ],
    "installable": True,
}
