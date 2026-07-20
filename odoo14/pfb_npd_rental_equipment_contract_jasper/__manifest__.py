# -*- coding: utf-8 -*-
{
    "name": u"สัญญาเช่าอุปกรณ์ก่อสร้าง (Jasper)",
    "summary": u"พิมพ์สัญญาเช่าอุปกรณ์ก่อสร้างจากใบขายด้วย JasperReports "
               u"เลขที่สัญญา prefix ตาม company + ir.sequence",
    "description": """
        Construction Equipment Rental Contract report using JasperReports.
        Ported from Odoo 14 QWeb module (npd_rental_equipment_contract_qweb)
        to Odoo 18 with the report rebuilt in Jasper (.jrxml) format.

        - เลขที่สัญญาเช่า = ตัวย่อบริษัท + เลขรัน (ir.sequence) + /จำนวนเอกสาร
        - odoo18 single-DB: map ตัวย่อบริษัทจาก company_registry (แทนชื่อ DB)
        - ปุ่ม header เปลี่ยนตัวย่อบริษัทผ่าน wizard
    """,
    "version": "18.0.1.0.1",
    "license": "LGPL-3",
    "author": "NPD Custom",
    "category": "Sales",
    "depends": [
        "base",
        "sale",
        "jasper_reports",
        "pfb_npd_all_customs",
        "pfb_npd_add_date_quatation_order",
        "multi_branch_management_aagam",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence.xml",
        "views/contract_prefix_wizard_view.xml",
        "views/sale_order_view.xml",
        "data/report_data.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
