# -*- coding: utf-8 -*-
{
    'name': 'NPD Product Withholding Tax',
    'version': '18.0.1.0.0',
    'summary': 'หมวดหมู่ภาษีหัก ณ ที่จ่ายบนสินค้า + สร้างใบหัก ณ ที่จ่ายอัตโนมัติจาก Advance Clear / ใบสำคัญ',
    'description': """
พอร์ตจาก o14 (pfb1 npd_product_wht 14.0.1.3.0, commit ac6087d5)

* หมวดหมู่ WHT (อัตรา 0/1/2/3/5%) ผูกกับสินค้า เลือกสินค้าใน Advance Clear / ใบสำคัญแล้วดึงหมวดหมู่มาให้
* ปุ่ม "สร้าง WHT อัตโนมัติ" สร้าง/อัปเดตหนังสือรับรองหัก ณ ที่จ่ายจากรายการ (คงเลขเดิม ไม่เกิดเลขข้าม)
* เตือนก่อนลงรายการถ้ามีรายการที่ต้องหักแต่ยังไม่ได้สร้างใบ
* เลขหนังสือรับรองออกตามวันที่ในใบและแยกตามบริษัท ห้ามแก้วันที่หลังออกเลข
* ปุ่มเลือกใบหัก ณ ที่จ่ายที่มีอยู่มาผูกกับเอกสาร
* ใบสำคัญแสดงยอดจ่ายสุทธิ (รวม - หัก ณ ที่จ่าย)

ต่างจาก o14
* o14 แยกฐาน NPD_Logistics_New ด้วยชื่อฐานข้อมูล (ช่อง "หัก VAT")
  o18 ทุกบริษัทอยู่ฐานเดียว จึงดูจากบริษัทของเอกสาร (บริษัท เอ็นพีดี โลจิสติกส์)
* ใบหัก ณ ที่จ่ายของ o18 (OCA l10n_th_account_tax) ใช้ partner_id / wht_line / wht_percent
  และออกเลขในช่อง number ตอน action_done
""",
    'category': 'Accounting',
    'author': 'NPD Dev',
    'license': 'LGPL-3',
    'depends': [
        'account',
        'product',
        'account_advance',
        'account_voucher_npd',
        'l10n_th_account_tax',
        'l10n_th_account_wht_cert_form',
        'withholding_tax_cert_amount',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/wht_account_data.xml',
        'views/wht_category_views.xml',
        'views/product_template_views.xml',
        'views/account_advance_clear_views.xml',
        'views/account_voucher_views.xml',
        'views/wt_cert_link_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
}
