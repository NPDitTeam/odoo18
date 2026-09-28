# -*- coding: utf-8 -*-
"""กฎเลือกสมุดรายวันฝั่งรับชำระ จากสมุดรายวันของใบแจ้งหนี้

เดิมการจับคู่ผูกอยู่กับ "กรณีการออกใบแจ้งหนี้" 8 กรณีตายตัว
(npd.invoice.journal.config) เพิ่มกรณีใหม่เองไม่ได้ ต้องแก้โค้ด
ไฟล์นี้เปิดให้เพิ่มกฎได้ไม่จำกัด โดยยึด "สมุดรายวันของใบแจ้งหนี้" เป็นตัวตั้ง
ตรง ๆ ซึ่งเป็นสิ่งที่ผู้ใช้เห็นบนหน้าจอจริงอยู่แล้ว

ลำดับการหาสมุดรายวันฝั่งรับชำระ
  1. กฎในตารางนี้
  2. ค่าที่ตั้งไว้เดิมใน npd.invoice.journal.config (ของเก่ายังใช้ได้)
  3. สมุดรายวันธนาคารเล่มแรกของบริษัท

ค่าเดิมทั้งหมดยังทำงานเหมือนเดิม กฎนี้เป็นชั้นบนสุดที่เพิ่มเข้ามา
"""
import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# Odoo 18 ยอมให้ account.payment ใช้สมุดรายวันได้เท่านี้
# (receivable/payable เปิดเพิ่มโดยโมดูล account_payment_sequence)
PAYMENT_JOURNAL_TYPES = ('receivable', 'payable', 'bank', 'cash', 'credit')


class NpdPaymentJournalRule(models.Model):
    _name = 'npd.payment.journal.rule'
    _description = 'กฎสมุดรายวันฝั่งรับชำระ'
    _order = 'company_id, sequence, id'

    sequence = fields.Integer(string='ลำดับ', default=10,
                              help='เลขน้อยมาก่อน ใช้ตอนมีกฎซ้อนกัน')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True, index=True,
        ondelete='cascade', default=lambda self: self.env.company)
    invoice_journal_id = fields.Many2one(
        'account.journal', string='สมุดรายวันของใบแจ้งหนี้', required=True,
        index=True, check_company=True,
        domain="[('company_id', '=', company_id), "
               " ('type', 'in', ('sale', 'purchase', 'general'))]",
        help='เมื่อใบแจ้งหนี้ที่กำลังจะชำระอยู่ในสมุดรายวันเล่มนี้')
    payment_journal_id = fields.Many2one(
        'account.journal', string='สมุดรายวันฝั่งรับชำระ', required=True,
        check_company=True,
        domain="[('company_id', '=', company_id), "
               " ('type', 'in', ('receivable', 'payable', 'bank', 'cash', 'credit'))]",
        help='หน้ารับชำระจะเลือกเล่มนี้ให้อัตโนมัติ')
    payment_sequence_hint = fields.Char(
        string='เลขรันของเล่มปลายทาง', readonly=True,
        compute='_compute_payment_sequence_hint',
        help='ดูว่าเล่มปลายทางใช้เลขของตัวเองหรือเลขกลางของบริษัท '
             'ตั้งได้ที่หน้าสมุดรายวัน แท็บ "เลขใบรับ/จ่ายชำระ"')
    note = fields.Char(string='หมายเหตุ')

    _sql_constraints = [(
        'uniq_company_invoice_journal',
        'unique(company_id, invoice_journal_id)',
        'สมุดรายวันใบแจ้งหนี้เล่มนี้มีกฎอยู่แล้ว — หนึ่งเล่มตั้งได้กฎเดียว',
    )]

    @api.depends('payment_journal_id.npd_own_payment_sequence',
                 'payment_journal_id.npd_payment_prefix')
    def _compute_payment_sequence_hint(self):
        for rule in self:
            journal = rule.payment_journal_id
            if not journal:
                rule.payment_sequence_hint = False
            elif journal.npd_own_payment_sequence and journal.npd_payment_prefix:
                rule.payment_sequence_hint = _('เลขของตัวเอง (%s)') % (
                    journal.npd_payment_prefix)
            else:
                rule.payment_sequence_hint = _('ใช้เลขกลางของบริษัท')

    @api.constrains('company_id', 'invoice_journal_id', 'payment_journal_id')
    def _check_company(self):
        for rule in self:
            for journal in (rule.invoice_journal_id | rule.payment_journal_id):
                if journal.company_id != rule.company_id:
                    raise ValidationError(_(
                        'สมุดรายวัน %(journal)s เป็นของบริษัท %(jcompany)s '
                        'ไม่ตรงกับบริษัท %(company)s ของกฎนี้',
                        journal=journal.display_name,
                        jcompany=journal.company_id.display_name,
                        company=rule.company_id.display_name))

    @api.constrains('payment_journal_id')
    def _check_payment_journal_type(self):
        for rule in self:
            if rule.payment_journal_id.type not in PAYMENT_JOURNAL_TYPES:
                raise ValidationError(_(
                    'สมุดรายวัน %s เป็นประเภท %s ใช้กับหน้ารับชำระไม่ได้',
                    rule.payment_journal_id.display_name,
                    rule.payment_journal_id.type))

    # ------------------------------------------------------------------
    @api.model
    def _resolve(self, company, invoice_journals):
        """สมุดรายวันฝั่งรับชำระตามกฎ — คืน recordset ว่างถ้าไม่มีกฎตรง

        sudo เพราะคนที่รับชำระต้องอ่านกฎได้ แต่ไม่ควรมีสิทธิ์แก้
        """
        Journal = self.env['account.journal']
        if not company or not invoice_journals:
            return Journal
        rules = self.sudo().search([
            ('company_id', '=', company.id),
            ('invoice_journal_id', 'in', invoice_journals.ids),
        ])
        by_journal = {}
        for rule in rules:
            by_journal.setdefault(rule.invoice_journal_id.id,
                                  rule.payment_journal_id.id)
        # ไล่ตามลำดับใบแจ้งหนี้ที่ส่งเข้ามา ไม่ใช่ลำดับที่ฐานข้อมูลคืนมา
        # ผลจะได้คงที่เมื่อชำระหลายใบพร้อมกัน
        for journal in invoice_journals:
            target = by_journal.get(journal.id)
            if target:
                return Journal.browse(target)
        return Journal

    # ------------------------------------------------------------------
    @api.model
    def action_seed_from_existing(self):
        """สร้างกฎตั้งต้นจากค่าที่ตั้งไว้เดิมในเมนูสมุดรายวันออกใบแจ้งหนี้

        กดซ้ำได้ ของที่มีกฎแล้วจะไม่ถูกเขียนทับ — คนอาจแก้กฎเองไปแล้ว
        """
        Config = self.env.get('npd.invoice.journal.config')
        if Config is None:
            return 0
        created = 0
        for config in Config.sudo().search([]):
            target = config.payment_bank_journal_id or config.payment_journal_id
            if not config.journal_id or not target:
                continue
            existing = self.sudo().search([
                ('company_id', '=', config.company_id.id),
                ('invoice_journal_id', '=', config.journal_id.id),
            ], limit=1)
            if existing:
                continue
            self.sudo().create({
                'company_id': config.company_id.id,
                'invoice_journal_id': config.journal_id.id,
                'payment_journal_id': target.id,
                'note': _('สร้างจากค่าเดิม (%s)') % config.usage,
            })
            created += 1
        _logger.info('[PAYMENT RULE] สร้างกฎตั้งต้น %s ข้อ', created)
        return created

    def action_seed_button(self):
        created = self.action_seed_from_existing()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('กฎสมุดรายวันรับชำระ'),
                'message': (_('สร้างกฎตั้งต้นเพิ่ม %s ข้อ') % created
                            if created else _('มีกฎครบแล้ว ไม่มีอะไรต้องเพิ่ม')),
                'type': 'success', 'sticky': False,
            },
        }
