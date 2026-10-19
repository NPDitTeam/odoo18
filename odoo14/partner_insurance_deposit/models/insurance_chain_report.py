# -*- coding: utf-8 -*-
# models/insurance_chain_report.py
# รายงานกระทบยอดเงินประกันตามสาย SO (เก็บผลลง DB เพื่อกรอง/จัดกลุ่มได้)
# - คำนวณใหม่รายลูกค้า: ปุ่ม "ตรวจเงินประกัน" ในหน้าลูกค้า
# - คำนวณใหม่ทั้งหมด: cron ทุกคืน

import logging

from odoo import models, fields, api

from .insurance_chain import STATUS_SELECTION, DOC_TYPE_SELECTION, INSURANCE_ACCOUNT_CODE

_logger = logging.getLogger(__name__)


class InsuranceChain(models.Model):
    _name = 'npd.insurance.chain'
    _description = 'กระทบยอดเงินประกันตามสาย SO'
    _order = 'status_sequence, balance, partner_id, id'
    _rec_name = 'chain_label'

    partner_id = fields.Many2one('res.partner', string='ลูกค้า', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', string='บริษัท', required=True, index=True)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')
    root_so = fields.Char(string='SO ใบแรก', index=True)
    chain_label = fields.Char(string='สาย SO')
    so_names = fields.Char(string='SO ในสาย')
    received = fields.Monetary(string='รับเข้า')
    deducted = fields.Monetary(string='หักไป')
    refunded = fields.Monetary(string='คืนไป')
    balance = fields.Monetary(string='คงเหลือ')
    status = fields.Selection(STATUS_SELECTION, string='สถานะ', index=True)
    status_sequence = fields.Integer()
    reason = fields.Text(string='สาเหตุ')
    action_todo = fields.Text(string='สิ่งที่ต้องทำ')
    line_ids = fields.One2many('npd.insurance.chain.line', 'chain_id', string='รายการ')
    computed_at = fields.Datetime(string='คำนวณเมื่อ')
    # เอกสารที่ทำให้สายนี้มีปัญหา (ติดลบครั้งแรก / ใช้เงินครั้งแรกตอนยังไม่มีเงินประกันเข้า)
    # ใช้แสดงเป็นแถวในเมนู "ตรวจสอบเงินประกันการเช่าเบิกเกิน"
    problem_line_id = fields.Many2one('account.move.line', string='บรรทัดที่เป็นปัญหา', index=True)
    problem_move_id = fields.Many2one('account.move', string='เอกสารที่เป็นปัญหา')

    @api.model
    def _refresh_partner(self, partner):
        """คำนวณสายเงินประกันของลูกค้าใหม่
        อัปเดตสายเดิมตาม SO ใบแรก (id คงที่ หน้าจอที่เปิดค้างไว้ยังใช้ได้) / สร้างสายใหม่ / ลบสายที่ไม่มีแล้ว"""
        partner = partner.commercial_partner_id
        company = self.env.company
        engine = self.env['npd.insurance.chain.engine']
        existing = {c.root_so: c for c in self.sudo().search([
            ('partner_id', '=', partner.id), ('company_id', '=', company.id)])}
        seq = {k: i for i, (k, _label) in enumerate(STATUS_SELECTION)}
        now = fields.Datetime.now()
        for root, c in engine.analyse(partner).items():
            if not c['entries']:
                continue
            # เอกสารที่เป็นปัญหา (เฉพาะฝั่งที่ยอดติดลบ แสดงเป็นแถวในเมนูตรวจสอบเงินประกันเบิกเกิน)
            first_out = next((e for e in c['entries'] if e['amount_out']), None)
            problem = None
            if c['status'] == 'over' or (c['status'] == 'wrong_partner' and c['first_negative']):
                problem = c['first_negative']
            elif c['status'] == 'no_ins' or (c['status'] == 'wrong_partner' and c['balance'] < 0):
                problem = first_out
            record = existing.pop(c['root'], False)
            if record:
                record.line_ids.unlink()
            write = record.write if record else self.sudo().create
            write({
                'problem_line_id': problem['line'].id if problem else False,
                'problem_move_id': problem['move'].id if problem else False,
                'partner_id': partner.id, 'company_id': company.id,
                'root_so': c['root'], 'chain_label': engine.chain_label(c),
                'so_names': ', '.join(c['so_names']),
                'received': c['received'], 'deducted': c['deducted'], 'refunded': c['refunded'],
                'balance': c['balance'], 'status': c['status'], 'status_sequence': seq.get(c['status'], 99),
                'reason': c['reason'], 'action_todo': c['action'], 'computed_at': now,
                'line_ids': [(0, 0, {
                    'sequence': i, 'date': e['date'], 'move_id': e['move'].id, 'doc_type': e['doc_type'],
                    'so_name': e['so_name'], 'invoice_ref': e['invoice_ref'] or False,
                    'voucher_id': e['voucher'].id if e['voucher'] else False,
                    'amount_in': e['amount_in'], 'amount_out': e['amount_out'], 'running': e['running'],
                }) for i, e in enumerate(c['entries'])],
            })
        for gone in existing.values():
            gone.unlink()

    @api.model
    def _cron_refresh_all(self):
        """คำนวณใหม่ทุกลูกค้าที่มีรายการในบัญชี 2133-01 (commit ทีละ 50 ราย)"""
        for company in self.env['res.company'].search([]):
            env = self.with_company(company)
            account = env.env['res.partner']._insurance_accounts()[:1]
            if not account:
                continue
            self.env.cr.execute("""
                select distinct coalesce(p.commercial_partner_id, p.id)
                from account_move_line l join res_partner p on p.id = l.partner_id
                where l.account_id = %s and l.parent_state = 'posted'""", (account.id,))
            partner_ids = [r[0] for r in self.env.cr.fetchall()]
            # ลบลูกค้าที่ไม่มีรายการแล้ว
            env.sudo().search([('company_id', '=', company.id), ('partner_id', 'not in', partner_ids)]).unlink()
            for i, pid in enumerate(partner_ids, 1):
                try:
                    env._refresh_partner(self.env['res.partner'].browse(pid))
                except Exception:
                    _logger.exception('insurance chain refresh failed for partner %s', pid)
                    self.env.cr.rollback()
                if i % 50 == 0:
                    self.env.cr.commit()
            self.env.cr.commit()
            _logger.info('insurance chain refreshed: company %s, %s partners', company.name, len(partner_ids))


class InsuranceChainLine(models.Model):
    _name = 'npd.insurance.chain.line'
    _description = 'รายการเงินประกันในสาย SO'
    _order = 'chain_id, sequence'

    chain_id = fields.Many2one('npd.insurance.chain', required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one('res.currency', related='chain_id.currency_id')
    sequence = fields.Integer()
    date = fields.Date(string='วันที่')
    move_id = fields.Many2one('account.move', string='เอกสาร')
    doc_type = fields.Selection(DOC_TYPE_SELECTION, string='ประเภท')
    so_name = fields.Char(string='SO')
    invoice_ref = fields.Char(string='หักชำระใบแจ้งหนี้')
    voucher_id = fields.Many2one('account.voucher', string='ใบคืนเงินประกัน')
    amount_in = fields.Monetary(string='รับเข้า')
    amount_out = fields.Monetary(string='ใช้ไป')
    running = fields.Monetary(string='คงเหลือสะสม')


class ResPartnerInsuranceChain(models.Model):
    _inherit = 'res.partner'

    def action_open_insurance_chains(self):
        """ปุ่ม "ตรวจเงินประกัน": คำนวณใหม่แล้วเปิดรายงานของลูกค้ารายนี้"""
        self.ensure_one()
        partner = self.commercial_partner_id
        self.env['npd.insurance.chain']._refresh_partner(partner)
        return {
            'type': 'ir.actions.act_window',
            'name': 'เงินประกัน: %s' % partner.display_name,
            'res_model': 'npd.insurance.chain',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', partner.id), ('company_id', '=', self.env.company.id)],
            'context': {'search_default_group_status': 0},
        }
