# -*- coding: utf-8 -*-
{
    'name': 'ใบแจ้งหนี้/ใบวางบิล',
    'version': '18.0.1.0.0',
    'summary': 'Order Rent — พิมพ์ใบแจ้งหนี้/ใบวางบิล จากใบสั่งเช่า (พอร์ตจาก Odoo 14)',
    'description': """
พอร์ตรายงาน pfb_npd_sale_form_Billing_sheet จาก Odoo 14 (สูตรตาม o14 commit a30b9d59)

ต่างจาก o14 ตรงที่ o18 รวมทุกบริษัทไว้ฐานเดียว:
- บัญชีธนาคาร / รูป QR สำรอง / การซ่อนเลขผู้เสียภาษี เลือกตาม "บริษัทของเอกสาร" แทนชื่อฐานข้อมูล
- ที่อยู่หัวเอกสารใช้สาขาของใบสั่งขาย (สำรองเป็นสาขาผู้ใช้ แล้วที่อยู่บริษัท)
- ช่องติ๊ก "ใช้ภาษีหัก ณ ที่จ่ายใบแจ้งหนี้/ใบวางบิล หัก 5%" (o14 อยู่ใน custom_invoice_date ซึ่ง o18 ยังไม่มี)
""",
    'author': 'Devtest',
    'category': 'Sales',
    'depends': [
        'sale',
        # pfb_amount, deposit_ref, pfb_date_of_rent
        'pfb_npd_all_customs',
        # start_rent_date, end_rent_date
        'pfb_npd_add_date_quatation_order',
        # สาขาบนใบสั่งขาย/ผู้ใช้ (res.branch)
        'multi_branch_management_aagam',
        # จำนวนเงินเป็นตัวอักษรไทย (เครื่อง o18 ไม่มีไลบรารี bahttext)
        'l10n_th_amount_to_text',
    ],
    'data': [
        'views/res_company_views.xml',
        'views/sale_order_views.xml',
        'report/pfb_npd_sale_form_Billing_sheet.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
