# Copyright 2019 Ecosoft Co., Ltd (https://ecosoft.co.th)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)

# แยกเฉพาะส่วนรายงานภาษีหัก ณ ที่จ่าย (ภ.ง.ด.1/1ก/2/3/53) ออกมาจาก OCA
# l10n_th_account_tax_report 18.0 เพราะโมดูลต้นทางประกาศ model tax.report.wizard
# ซ้ำกับ l10n_th_tax_report (รายงานภาษีซื้อ/ขายที่พอร์ตจาก o14) ติดตั้งคู่กันไม่ได้
{
    "name": "NPD - Thai Withholding Tax Reports (PND)",
    "version": "18.0.1.0.0",
    "author": "Ecosoft, Odoo Community Association (OCA), NPD",
    "website": "https://github.com/OCA/l10n-thailand",
    "license": "AGPL-3",
    "category": "Accounting",
    "depends": [
        "date_range",
        "report_xlsx_helper",
        "l10n_th_base_utils",
        "l10n_th_partner",
        "l10n_th_account_tax",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/paper_format.xml",
        "data/report_data.xml",
        "reports/templates/layout.xml",
        "reports/templates/wht_report.xml",
        "reports/templates/wht_report_rd_pnd1.xml",
        "reports/templates/wht_report_rd_pnd1a.xml",
        "reports/templates/wht_report_rd_pnd2.xml",
        "reports/templates/wht_report_rd_pnd3.xml",
        "reports/templates/wht_report_rd_pnd53.xml",
        "reports/templates/wht_report_rd.xml",
        "reports/templates/wht_report_text.xml",
        "wizard/withholding_tax_report_wizard_view.xml",
        "views/res_company_views.xml",
        "views/res_config_settings_views.xml",
        "views/account_menu.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "npd_l10n_th_wht_report/static/src/scss/style_report.scss",
        ],
        "web.report_assets_common": [
            "npd_l10n_th_wht_report/static/src/scss/style_report.scss",
        ],
    },
    "installable": True,
}
