# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)



class DepositOverdraw(models.Model):
    """รายการเงินประกันการเช่าที่ทำให้ยอดสะสมของลูกค้าเป็นบวก (คืน/ใช้เกินที่รับไว้)

    คิดสดทุกครั้งที่เปิด (_table_query) ไม่มีตารางเก็บ ข้อมูลจึงตรงบัญชีแยกประเภทเสมอ
    """
    _name = 'npd.deposit.overdraw'
    _description = 'ตรวจสอบเงินประกันการเช่าเบิกเกิน'
    _auto = False
    _order = 'date desc, id desc'
    _rec_name = 'move_name'

    date = fields.Date('วันที่', readonly=True)
    move_id = fields.Many2one('account.move', 'รายการบันทึกบัญชี', readonly=True)
    move_name = fields.Char('เลขเอกสาร', readonly=True)
    move_ref = fields.Char('อ้างอิง', readonly=True)
    invoice_origin = fields.Char('เอกสารต้นทาง', readonly=True)
    line_name = fields.Char('ป้ายกำกับ', readonly=True)
    partner_id = fields.Many2one('res.partner', 'คู่ค้า', readonly=True)
    account_id = fields.Many2one('account.account', 'บัญชี', readonly=True)
    company_id = fields.Many2one('res.company', 'บริษัท', readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id', readonly=True)
    debit = fields.Monetary('เดบิต (คืน/ใช้)', readonly=True)
    cumulated = fields.Monetary('ยอดที่เกิน', readonly=True,
                                help='ยอดสะสมของลูกค้าหลังรายการนี้ (บวก = คืน/ใช้เกินที่รับไว้ ไม่นับเศษปัดน้อยกว่า 1 บาท)')
    partner_balance = fields.Monetary('ยอดคงเหลือปัจจุบันของลูกค้า', readonly=True,
                                      help='ติดลบ = ยังถือเงินประกันลูกค้าอยู่ / บวก = ยังเกินอยู่')
    state = fields.Selection([
        ('over', 'ยังเกินอยู่'),
        ('settled', 'ปรับยอดแล้ว'),
    ], string='สถานะ', readonly=True,
        help='ยังเกินอยู่ = ยอดคงเหลือปัจจุบันของลูกค้ายังเป็นบวก\n'
             'ปรับยอดแล้ว = ภายหลังมีรับเงินประกันเพิ่มจนยอดกลับมาไม่เป็นบวก')

    # ------------------------------------------------------------------
    @api.model
    def _deposit_account_ids(self):
        """บัญชีรายได้ของสินค้าเงินประกันค่าเช่า ทุกบริษัท (ตัวเดียวกับปุ่มรับเงินประกัน)

        o18 สินค้าเงินประกันตั้งแยกบริษัทได้ (เมนูสมุดรายวันออกใบแจ้งหนี้) จึงหาผ่าน
        _get_insurance_product ของ pfb_npd_all_customs ทีละบริษัท
        """
        Config = self.env['npd.invoice.journal.config'].sudo()
        ids = set()
        for company in self.env['res.company'].sudo().search([]):
            product = Config._get_insurance_product(company)
            if not product:
                continue
            prod = product.sudo().with_company(company)
            account = prod.property_account_income_id or prod.categ_id.property_account_income_categ_id
            if account:
                ids.add(account.id)
        return sorted(ids)

    @property
    def _table_query(self):
        account_ids = self._deposit_account_ids()
        if not account_ids:
            _logger.warning('[DEPOSIT OVERDRAW] ไม่พบผังเงินประกัน (สินค้าเงินประกันค่าเช่า)')
            account_filter = 'FALSE'
        else:
            account_filter = 'l.account_id IN (%s)' % ','.join(str(int(i)) for i in account_ids)
        return """
            SELECT x.id, x.date, x.move_id, x.move_name, x.move_ref, x.invoice_origin, x.line_name,
                   x.partner_id, x.account_id, x.company_id, x.debit,
                   x.cumulated, x.partner_balance,
                   CASE WHEN x.partner_balance >= 1.0 THEN 'over' ELSE 'settled' END AS state
              FROM (
                SELECT l.id, l.date, l.move_id, m.name AS move_name, m.ref AS move_ref,
                       m.invoice_origin, l.name AS line_name,
                       COALESCE(p.commercial_partner_id, p.id) AS partner_id,
                       l.account_id, l.company_id, l.debit, l.balance,
                       SUM(l.balance) OVER w_running AS cumulated,
                       SUM(l.balance) OVER w_partner AS partner_balance
                  FROM account_move_line l
                  JOIN account_move m ON m.id = l.move_id
                  -- รายการไม่มีคู่ค้า (เช่น JV ปรับปิดปี) ไม่ใช่เงินประกันของลูกค้ารายใด ตัดทิ้ง
                  JOIN res_partner p ON p.id = l.partner_id
                 WHERE l.parent_state = 'posted' AND %s
                -- นับต่อบริษัทแม่ของลูกค้า: รับประกันในชื่อผู้ติดต่อ แต่คืนในชื่อบริษัท ต้องรวมกัน
                WINDOW w_partner AS (PARTITION BY l.company_id, l.account_id,
                                                  COALESCE(p.commercial_partner_id, p.id)),
                       w_running AS (w_partner ORDER BY l.date, l.move_id, l.id)
              ) x
             WHERE x.balance > 0 AND x.cumulated >= 1.0
        """ % account_filter
