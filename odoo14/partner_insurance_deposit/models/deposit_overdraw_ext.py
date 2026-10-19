# -*- coding: utf-8 -*-
# models/deposit_overdraw_ext.py
# ต่อยอดเมนู "ตรวจสอบเงินประกันการเช่าเบิกเกิน" (npd_deposit_overdraw_check) โดยไม่แก้ไฟล์ของโมดูลนั้น
#
# แถวเดิม (source = customer): เอกสารที่ทำให้ยอดรวมของลูกค้าเกิน — คำนวณสดเหมือนเดิม
# แถวเพิ่ม (source = chain)  : สาย SO ที่มีปัญหา แม้ยอดรวมของลูกค้ายังไม่เกิน
#                              (เงินประกันไม่เคยเข้าระบบ / ใช้เกินยอดที่รับในสาย) จากตาราง npd.insurance.chain
# ทุกแถวมีคอลัมน์ "สาเหตุ" และปุ่ม "ดูสาย SO"

from odoo import api, fields, models

# id ของแถวสาย SO = ค่านี้ + id ของ npd.insurance.chain (ไม่ชนกับ id ของ account.move.line)
CHAIN_ROW_OFFSET = 1000000000


class DepositOverdrawChain(models.Model):
    _inherit = 'npd.deposit.overdraw'

    state = fields.Selection(selection_add=[('chain', 'สาย SO มีปัญหา')])
    source = fields.Selection([
        ('customer', 'ยอดรวมลูกค้าเกิน'),
        ('chain', 'สาย SO มีปัญหา'),
    ], string='ประเภท', readonly=True)
    chain_id = fields.Many2one('npd.insurance.chain', string='สาย SO', readonly=True)
    chain_status = fields.Selection(related='chain_id.status', string='สถานะสาย SO')
    chain_action_todo = fields.Text(related='chain_id.action_todo', string='สิ่งที่ต้องทำ')
    reason = fields.Text(string='สาเหตุ', compute='_compute_reason')

    @property
    def _table_query(self):
        base = super()._table_query
        return """
            SELECT o.id, o.date, o.move_id, o.move_name, o.move_ref, o.invoice_origin, o.line_name,
                   o.partner_id, o.account_id, o.company_id, o.debit, o.cumulated, o.partner_balance,
                   o.state, 'customer' AS source,
                   (SELECT cl.chain_id FROM npd_insurance_chain_line cl
                     WHERE cl.move_id = o.move_id ORDER BY cl.id LIMIT 1) AS chain_id
              FROM (%(base)s) o
            UNION ALL
            SELECT %(offset)s + c.id AS id, l.date, l.move_id, m.name, m.ref, m.invoice_origin, l.name,
                   c.partner_id, l.account_id, c.company_id, l.debit,
                   -c.balance AS cumulated,
                   -(SELECT SUM(c2.balance) FROM npd_insurance_chain c2
                      WHERE c2.partner_id = c.partner_id AND c2.company_id = c.company_id) AS partner_balance,
                   'chain' AS state, 'chain' AS source, c.id AS chain_id
              FROM npd_insurance_chain c
              JOIN account_move_line l ON l.id = c.problem_line_id
              JOIN account_move m ON m.id = l.move_id
             WHERE c.status IN ('wrong_partner', 'no_ins', 'over')
               -- ลูกค้าที่ยอดรวมเกินอยู่แล้ว แสดงในแถวเดิมของเมนูแล้ว ไม่ซ้ำ
               AND (SELECT SUM(c2.balance) FROM npd_insurance_chain c2
                     WHERE c2.partner_id = c.partner_id AND c2.company_id = c.company_id) > -1.0
        """ % {'base': base, 'offset': CHAIN_ROW_OFFSET}

    @api.depends('chain_id', 'source', 'cumulated')
    def _compute_reason(self):
        Chain = self.env['npd.insurance.chain']
        for row in self:
            if row.chain_id and row.chain_id.status != 'ok':
                row.reason = row.chain_id.reason
            elif row.source == 'customer':
                # สายของเอกสารนี้ปกติ → ยอดรวมเกินเพราะสาย SO อื่นของลูกค้า แสดงสาเหตุของสายนั้น
                problems = Chain.search([('partner_id', '=', row.partner_id.id), ('company_id', '=', row.company_id.id),
                                         ('status', 'in', ('wrong_partner', 'no_ins', 'over'))])
                head = 'ยอดเงินประกันรวมของลูกค้าเกินที่รับไว้ %s บาท หลังเอกสาร %s' % (
                    '{:,.2f}'.format(row.cumulated or 0.0), row.move_name or '-')
                if problems:
                    row.reason = head + ' เพราะ:\n' + '\n'.join(problems.mapped('reason'))
                else:
                    row.reason = head + ' (ยังไม่ได้คำนวณสาย SO กดปุ่ม "ดูสาย SO" เพื่อดูสาเหตุ)'
            else:
                row.reason = False

    def action_open_chain(self):
        """ปุ่ม "ดูสาย SO": เปิดรายละเอียดสาย SO (คำนวณใหม่ก่อน)"""
        self.ensure_one()
        partner, move, company = self.partner_id, self.move_id, self.company_id or self.env.company
        self.env['npd.insurance.chain'].with_company(company)._refresh_partner(partner)
        chains = self.env['npd.insurance.chain'].search([
            ('partner_id', '=', partner.commercial_partner_id.id), ('company_id', '=', company.id)])
        # สายของเอกสารนี้ ถ้าสายนั้นปกติแต่ลูกค้ามีสายอื่นที่มีปัญหา ให้เปิดสายที่มีปัญหา
        chain = chains.filtered(lambda c: move in c.line_ids.mapped('move_id') and c.status != 'ok')[:1] \
            or chains.filtered(lambda c: c.status in ('wrong_partner', 'no_ins', 'over'))[:1] \
            or chains.filtered(lambda c: move in c.line_ids.mapped('move_id'))[:1]
        if chain:
            return {
                'type': 'ir.actions.act_window', 'res_model': 'npd.insurance.chain',
                'res_id': chain.id, 'view_mode': 'form', 'target': 'current',
                'name': chain.chain_label,
            }
        return partner.action_open_insurance_chains()
