# -*- coding: utf-8 -*-
from datetime import timedelta
from odoo import models, fields, api, _


class CashflowSummaryWizard(models.TransientModel):
    _name = 'npd.scb.cashflow.summary.wizard'
    _description = 'สรุปกระแสเงินสด'

    source = fields.Selection([
        ('all', 'ทุกธนาคาร'),
        ('scb', 'SCB'),
        ('kbank', 'Kbank'),
        ('ktb', 'กรุงไทย'),
    ], string='ธนาคาร')
    bank_name = fields.Char('ธนาคาร', readonly=True)
    date_from = fields.Date('วันที่เริ่มต้น')
    date_to = fields.Date('วันที่สิ้นสุด')
    line_ids = fields.One2many('npd.scb.cashflow.summary.line', 'wizard_id', string='รายการ')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id.id)

    def _latest_balance_by_account(self, domain):
        """คืน dict {account_no: (account_name, balance_eod ของแถวล่าสุด)} ตาม domain ที่ให้"""
        Cash = self.env['npd.scb.cashflow']
        result = {}
        for rec in Cash.search(domain, order='date desc, id desc'):
            if not rec.account_no or rec.account_no in result:
                continue
            result[rec.account_no] = (rec.account_name or 'ไม่ระบุ', rec.balance_eod or 0.0)
        return result

    def _build_summary_lines(self, source, date_from, date_to):
        """คำนวณบรรทัดสรุป (รวมตามบริษัท) แล้วคืนเป็นชุดคำสั่ง one2many"""
        Cash = self.env['npd.scb.cashflow']
        currency = self.env.company.currency_id.id
        # source ว่าง หรือ 'all' = ดูทุกธนาคาร (ไม่กรอง)
        base_domain = [] if (not source or source == 'all') else [('source', '=', source)]

        def blank():
            return {'open': 0.0, 'in': 0.0, 'out': 0.0, 'bal': 0.0}
        companies = {}

        # ยอดยกมา = ยอดคงเหลือสิ้นวันล่าสุด "ก่อน" วันที่เริ่มต้น (= คงเหลือสิ้นงวดก่อน)
        if date_from:
            open_domain = base_domain + [('date', '<', date_from)]
            for name, bal in self._latest_balance_by_account(open_domain).values():
                companies.setdefault(name, blank())['open'] += bal

        # รับ / จ่าย ภายในช่วงวันที่ [date_from, date_to]
        money_domain = list(base_domain)
        if date_from:
            money_domain.append(('date', '>=', date_from))
        if date_to:
            money_domain.append(('date', '<=', date_to))
        groups = Cash.read_group(
            money_domain, ['money_in:sum', 'money_out:sum'], ['account_name'])
        for g in groups:
            name = g.get('account_name') or 'ไม่ระบุ'
            c = companies.setdefault(name, blank())
            c['in'] = g.get('money_in') or 0.0
            c['out'] = g.get('money_out') or 0.0

        # คงเหลือ = ยอดคงเหลือสิ้นวันล่าสุด ณ "วันที่สิ้นสุด"
        bal_domain = list(base_domain)
        if date_to:
            bal_domain.append(('date', '<=', date_to))
        for name, bal in self._latest_balance_by_account(bal_domain).values():
            companies.setdefault(name, blank())['bal'] += bal

        # เรียงตามยอดคงเหลือมาก -> น้อย
        commands = []
        for name, c in sorted(companies.items(), key=lambda kv: kv[1]['bal'], reverse=True):
            commands.append((0, 0, {
                'company_name': name,
                'opening': c['open'],
                'money_in': c['in'],
                'money_out': c['out'],
                'balance': c['bal'],
                'currency_id': currency,
            }))
        return commands

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        # เปิดจากเมนู (ไม่มี context) -> ตั้งค่าเริ่มต้นเป็น SCB
        source = self.env.context.get('summary_source') or self.env.context.get('default_source') or 'scb'

        # ค่าเริ่มต้น = เดือนปัจจุบัน (ต้นเดือน -> เมื่อวาน)
        # ข้อมูลบัญชีช้ากว่าปัจจุบัน 1 วัน จึงตั้งวันสิ้นสุดเป็นเมื่อวาน (ข้อมูลล่าสุดที่มีจริง)
        today = fields.Date.context_today(self)
        first = today.replace(day=1)
        date_to = today - timedelta(days=1)

        bank_map = {'scb': 'SCB', 'kbank': 'Kbank', 'ktb': 'กรุงไทย'}
        res['source'] = source
        res['bank_name'] = bank_map.get(source, 'ทุกธนาคาร')
        res['date_from'] = first
        res['date_to'] = date_to
        res['line_ids'] = self._build_summary_lines(source, first, date_to)
        return res

    def _get_latest_data_date(self):
        """วันที่ล่าสุดที่มีข้อมูลจริงใน npd.scb.cashflow (กรองตามธนาคารที่เลือก)
        ปกติข้อมูลบัญชีช้ากว่าปัจจุบัน 1 วัน จึงใช้ค่านี้เตือนเมื่อเลือกวันสิ้นสุดเกินข้อมูลที่มี"""
        base_domain = [] if (not self.source or self.source == 'all') else [('source', '=', self.source)]
        latest = self.env['npd.scb.cashflow'].search(base_domain, order='date desc', limit=1)
        return latest.date if latest else False

    @api.onchange('source', 'date_from', 'date_to')
    def _onchange_period(self):
        """เปลี่ยนธนาคาร/ช่วงวันที่ -> คำนวณตารางใหม่ทันที
        ถ้าวันที่สิ้นสุดเลยวันที่ข้อมูลล่าสุด -> แจ้งเตือน (ไม่บล็อก)"""
        bank_map = {'scb': 'SCB', 'kbank': 'Kbank', 'ktb': 'กรุงไทย'}
        self.bank_name = bank_map.get(self.source, 'ทุกธนาคาร')
        self.line_ids = [(5, 0, 0)] + self._build_summary_lines(
            self.source, self.date_from, self.date_to)

        latest = self._get_latest_data_date()
        if self.date_to and latest and self.date_to > latest:
            return {
                'warning': {
                    'title': _('ข้อมูลยังไม่อัปเดตถึงวันที่เลือก'),
                    'message': _(
                        'ข้อมูลบัญชีล่าสุดมีถึงวันที่ %s เท่านั้น '
                        '(ปกติข้อมูลช้ากว่าปัจจุบัน 1 วัน)\n'
                        'ยอด "รับ/จ่าย/คงเหลือ" หลังวันดังกล่าวจึงยังไม่มีข้อมูล'
                    ) % latest.strftime('%d/%m/%Y'),
                }
            }


class CashflowSummaryLine(models.TransientModel):
    _name = 'npd.scb.cashflow.summary.line'
    _description = 'บรรทัดสรุปกระแสเงินสด'
    _order = 'balance desc'

    wizard_id = fields.Many2one('npd.scb.cashflow.summary.wizard', ondelete='cascade')
    company_name = fields.Char('บริษัท')
    opening = fields.Monetary('ยอดยกมา', currency_field='currency_id')
    money_in = fields.Monetary('รับ', currency_field='currency_id')
    money_out = fields.Monetary('จ่าย', currency_field='currency_id')
    balance = fields.Monetary('คงเหลือ', currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id.id)
