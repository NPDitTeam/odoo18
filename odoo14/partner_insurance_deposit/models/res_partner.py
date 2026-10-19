# -*- coding: utf-8 -*-
# models/res_partner.py
# ไฟล์นี้ทำหน้าที่เพิ่มฟิลด์ใหม่ให้กับ model res.partner
# โดยใช้วิธี _inherit เพื่อสืบทอดและขยายความสามารถของ model เดิม

from odoo import models, fields, api

# บัญชีเงินประกันการเช่า/สินค้า (สำรอง ถ้าหาจากสินค้าเงินประกันไม่ได้)
INSURANCE_ACCOUNT_CODE = '2133-01'


class ResPartnerInherit(models.Model):
    """
    Class นี้ inherit จาก res.partner เพื่อเพิ่มฟิลด์ค่าประกันสะสม

    การใช้ _inherit = 'res.partner' หมายความว่า:
    - ไม่ได้สร้าง model ใหม่ แต่เป็นการขยาย model res.partner ที่มีอยู่แล้ว
    - ฟิลด์ใหม่จะถูกเพิ่มเข้าไปใน table res_partner ในฐานข้อมูล
    - สามารถใช้ฟิลด์นี้ร่วมกับฟิลด์เดิมทั้งหมดของ res.partner ได้
    """

    _inherit = 'res.partner'  # ระบุว่าจะ inherit จาก model ไหน

    # ฟิลด์ค่าประกันสะสม (Accumulated Insurance Deposit)
    # store=False: คำนวณใหม่ทุกครั้งที่เปิดหน้า (real-time)
    accumulated_insurance_deposit = fields.Monetary(
        string='ค่าประกันสะสม',
        compute='_compute_accumulated_insurance_deposit',
        store=False,
        currency_field='currency_id',
        help='ยอดคงเหลือบัญชี 2133-01 เงินประกันการเช่า/สินค้า ของลูกค้า (เครดิต - เดบิต) '
             'ตรงกับบัญชีแยกประเภททั่วไป: รับเงินประกัน (INS) - หักค่าเช่า/ค่าปรับหาย/ค่าปรับชำรุด - คืนเงินประกัน',
    )
    # ===== ฟิลด์ประเภทลูกค้า (Customer Status) =====
    # ดึงมาจาก crm.lead field customer_status
    # เป็น Selection field: old = ลูกค้าเก่า, new = ลูกค้าใหม่
    customer_status = fields.Selection(
        selection=[
            ('old', 'ลูกค้าเก่า'),
            ('new', 'ลูกค้าใหม่'),
        ],
        string='ประเภทลูกค้า',
        compute='_compute_customer_status',
        store=False,
        help='ประเภทลูกค้า ดึงจาก CRM Lead ล่าสุด',
    )

    @api.model
    def _insurance_accounts(self):
        """ผังเงินประกันการเช่าของบริษัทปัจจุบัน
        ใช้บัญชีรายได้ของสินค้า "เงินประกันค่าเช่า" ของบริษัท (o18 ตั้งแยกบริษัทที่เมนูสมุดรายวันออกใบแจ้งหนี้
        ตัวเดียวกับปุ่มรับเงินประกัน และเมนูตรวจสอบเงินประกันการเช่าเบิกเกิน)
        ถ้าไม่มีค่อยใช้บัญชีที่รหัส o14 = 2133-01 (ผังใหม่ o18 เลขไม่ตรง o14)"""
        company = self.env.company
        product = self.env['npd.invoice.journal.config'].sudo()._get_insurance_product(company)
        if product:
            prod = product.sudo().with_company(company)
            account = prod.property_account_income_id or prod.categ_id.property_account_income_categ_id
            if account and company in account.company_ids:
                return account
        Account = self.env['account.account'].sudo().with_company(company)
        domain = [('company_ids', 'in', company.id)]
        if 'npd_o14_code' in Account._fields:
            found = Account.search(domain + [('npd_o14_code', '=', INSURANCE_ACCOUNT_CODE)])
            if found:
                return found
        return Account.search(domain + [('code', '=', INSURANCE_ACCOUNT_CODE)])

    def _get_insurance_deposit_balance(self, exclude_move_ids=None):
        """
        ยอดคงเหลือเงินประกันของลูกค้า จากบัญชี 2133-01 (เฉพาะรายการที่ลงบันทึกแล้ว)

        - นับรวมผู้ติดต่อทุกคนในบริษัทเดียวกัน (commercial partner)
        - ใช้ partner_id ของบรรทัดบัญชี (ใบ PV คืนเงินบางใบผูกผู้ติดต่อไว้ที่บรรทัด ไม่ใช่หัวเอกสาร)
        - exclude_move_ids: ไม่นับรายการของเอกสารนั้น ๆ (ใช้ดูยอด "ก่อน" เอกสารที่กำลังเปิดอยู่)
        """
        self.ensure_one()
        accounts = self._insurance_accounts()
        if not accounts:
            return 0.0
        domain = [
            ('account_id', 'in', accounts.ids),
            ('parent_state', '=', 'posted'),
            ('partner_id', 'child_of', self.commercial_partner_id.id),
        ]
        if exclude_move_ids:
            domain.append(('move_id', 'not in', list(exclude_move_ids)))
        res = self.env['account.move.line'].read_group(domain, ['debit', 'credit'], [])
        if not res:
            return 0.0
        return (res[0].get('credit') or 0.0) - (res[0].get('debit') or 0.0)

    def _compute_accumulated_insurance_deposit(self):
        for partner in self:
            partner.accumulated_insurance_deposit = (
                partner._get_insurance_deposit_balance() if partner.id else 0.0)

    def _compute_customer_status(self):
        """
        Method สำหรับดึงประเภทลูกค้าจาก CRM Lead

        หลักการทำงาน:
        1. ค้นหา crm.lead ที่ partner_id = ลูกค้ารายนี้
        2. เรียงตามวันที่สร้างล่าสุด (create_date desc)
        3. ดึง customer_status จาก lead ล่าสุด
        """
        for partner in self:
            customer_status = False

            # ค้นหา lead ที่เกี่ยวข้องกับ partner นี้
            # เรียงตาม create_date จากล่าสุด
            lead = self.env['crm.lead'].search([
                ('partner_id', 'in', [partner.id, partner.commercial_partner_id.id]),
            ], order='create_date desc', limit=1)

            if lead and hasattr(lead, 'customer_status'):
                customer_status = lead.customer_status

            partner.customer_status = customer_status
