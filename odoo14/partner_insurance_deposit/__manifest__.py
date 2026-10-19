# -*- coding: utf-8 -*-
# __manifest__.py
# ไฟล์ manifest สำหรับกำหนดข้อมูลโมดูล Odoo

{
    'name': 'Partner Insurance Deposit',
    'version': '18.0.1.3.2',
    'category': 'Sales',
    'summary': 'เพิ่มฟิลด์ค่าประกันสะสมและประเภทลูกค้าในข้อมูลคู่ค้า',
    'description': """
        โมดูลนี้เพิ่มฟิลด์ในหน้าข้อมูลคู่ค้า (res.partner):
        
        1. ค่าประกันสะสม (Accumulated Insurance Deposit)
           - ต่อจากฟิลด์ Tax Branch
           - ยอดคงเหลือบัญชี 2133-01 ของลูกค้า (ตรงกับบัญชีแยกประเภททั่วไป)
           - แสดงในหน้าการรับชำระ (วิธีชำระ หักเงินประกันค่าเช่า) และหน้าคืนเงินประกันค่าเช่าด้วย
           - ห้ามคืน/หักเงินประกันเกินยอดของสาย SO หรือของลูกค้า (Error บอกสาเหตุ + สิ่งที่ต้องทำ)

        3. กระทบยอดเงินประกันตามสาย SO (ปุ่ม "ตรวจเงินประกัน" ในหน้าลูกค้า)
           - บอกสาเหตุที่ยอดไม่ลงตัว เป็นภาษาไทย คำนวณใหม่ทุกคืน + ทุกครั้งที่ลงบันทึก/ยกเลิกรายการเงินประกัน
           - เมนู "ตรวจสอบเงินประกันการเช่าเบิกเกิน": เพิ่มคอลัมน์สาเหตุ ปุ่มดูสาย SO
             และแถวสาย SO ที่มีปัญหาแม้ยอดรวมลูกค้ายังไม่เกิน

        2. ประเภทลูกค้า (Customer Status)
           - ใต้ฟิลด์ Priority
           - ดึงจาก crm.lead ล่าสุด
           - ลูกค้าเก่า / ลูกค้าใหม่
    """,
    'author': 'NPD',
    'license': 'LGPL-3',
    
    # depends: โมดูลที่ต้องติดตั้งก่อน
    # - base: โมดูลพื้นฐาน (res.partner)
    # - account: โมดูลบัญชี (account.payment, account.journal)
    # - crm: โมดูล CRM (crm.lead)
    # - partner_priority: โมดูล priority (priority_id field)
    # - account_payment_invoice: หน้าการรับชำระ (payment_method_one_id / paid_ids)
    # - account_voucher_npd: หน้าคืนเงินประกันค่าเช่า
    # - npd_deposit_overdraw_check: เมนูตรวจสอบเงินประกันการเช่าเบิกเกิน (เพิ่มสาเหตุ + สาย SO ที่มีปัญหา)
    # partner_priority: ช่อง Priority (priority_id) / custom_crm_customer_status: ประเภทลูกค้าใน CRM
    # pfb_npd_all_customs: หาสินค้าเงินประกันแยกบริษัท (npd.invoice.journal.config)
    'depends': ['base', 'account', 'crm', 'partner_priority', 'custom_crm_customer_status', 'account_payment_invoice', 'account_voucher_npd',
                'npd_deposit_overdraw_check', 'pfb_npd_all_customs', 'l10n_th_partner'],

    # data: ไฟล์ XML ที่ต้องโหลด
    'data': [
        'security/ir.model.access.csv',
        'views/res_partner_views.xml',
        'views/insurance_deposit_docs_views.xml',
        'views/insurance_chain_views.xml',
    ],
    
    'installable': True,
    'auto_install': False,
    'application': False,
}
