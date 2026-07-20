# -*- coding: utf-8 -*-
{
    "name": u"หนังสือมอบอำนาจ (Jasper)",
    "summary": u"พิมพ์หนังสือมอบอำนาจจากใบขายด้วย JasperReports",
    "description": """
        Power of Attorney report using JasperReports.
        Ported from Odoo 14 QWeb module (npd_power_of_attorney_qweb)
        to Odoo 18 with the report rebuilt in Jasper (.jrxml) format.

        ใช้ฟิลด์ jasper_rc_* ของโมดูลสัญญาเช่าซ้ำ (ชื่อผู้ให้เช่า / เลขที่สัญญา /
        วันที่แบบไทย) เหมือนที่ฝั่ง O14 depend npd_rental_equipment_contract_qweb
    """,
    "version": "18.0.1.0.0",
    "license": "LGPL-3",
    "author": "NPD Custom",
    "category": "Sales",
    "depends": [
        "base",
        "sale",
        "jasper_reports",
        "pfb_npd_rental_equipment_contract_jasper",
    ],
    "data": [
        "data/report_data.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
