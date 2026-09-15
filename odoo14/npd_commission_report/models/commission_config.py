# -*- coding: utf-8 -*-
"""ตั้งค่าว่าจะอ่านยอดจากสมุดรายวันไหน — ทีละบริษัท

ของเดิมใน Odoo 14 ฝังชื่อสมุดรายวันภาษาไทยไว้ในโค้ดตรง ๆ เช่น
``'สมุดรายวันเช่า(สาขา)'`` แล้วค้นทั้งฐานโดยไม่กรองบริษัท ซึ่งใช้ได้เพราะ
ตอนนั้นแยกฐานข้อมูลต่อบริษัทอยู่แล้ว

พอมารวมทุกบริษัทไว้ในฐานเดียว การค้นแบบเดิมจะรวมยอดข้ามบริษัทกันหมด
และถ้าปล่อยเช่าให้ลูกค้า สมุดรายวันของเขาชื่อไม่เหมือนเรา ระบบจะคิดค่าคอม
เป็นศูนย์เงียบ ๆ โดยไม่มีอะไรบอก

ไฟล์นี้จึงย้ายชื่อสมุดออกมาเป็นค่าตั้งค่าต่อบริษัท และตั้งค่าเริ่มต้นให้เอง
จากชื่อเดิมที่ NPD ใช้อยู่ ติดตั้งแล้วได้ผลเท่าเดิมทันที
"""
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# ชื่อสมุดรายวันที่ NPD ใช้อยู่ — ใช้เป็นค่าตั้งต้นตอนสร้างค่าตั้งค่าครั้งแรก
DEFAULT_RENTAL_JOURNALS = ['สมุดรายวันเช่า(สาขา)']
DEFAULT_PENALTY_JOURNALS = ['สมุดรายวันค่าปรับหาย', 'สมุดรายวันค่าปรับชำรุด']
DEFAULT_PAYMENT_JOURNALS = [
    'สมุดรายวันรับชำระ',
    'สมุดรายวันรับชำระค่าปรับหาย',
    'สมุดรายวันรับชำระค่าปรับชำรุด',
]
# Odoo 14 ค้นด้วยชื่อ 'สมุดรายวันลดหนี้ขาย' ซึ่งไม่ตรงกับชื่อจริงในระบบนี้
# ('สมุดรายวันลดหนี้การขาย') จึงหาไม่เจอและไม่เคยหักใบลดหนี้ออกจากยอดเช่าเลย
DEFAULT_CREDIT_NOTE_JOURNALS = ['สมุดรายวันลดหนี้การขาย',
                               'สมุดรายวันลดหนี้ขาย']
# รับชำระค่าปรับชำรุดคิดยอดเต็ม ไม่ถอด VAT (ตามที่การเงินคิด)
DEFAULT_GROSS_PAYMENT_JOURNALS = ['สมุดรายวันรับชำระค่าปรับชำรุด']


class CommissionConfig(models.Model):
    _name = 'npd.commission.config'
    _description = 'ตั้งค่ารายงานค่าคอมมิชชั่น'
    _rec_name = 'company_id'

    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True,
        default=lambda self: self.env.company, ondelete='cascade')

    rental_journal_ids = fields.Many2many(
        'account.journal', 'npd_comm_cfg_rental_rel', 'config_id', 'journal_id',
        string='สมุดรายวันยอดเช่า',
        help='ใบแจ้งหนี้ในสมุดเหล่านี้ถูกนับเป็น "ยอดเช่า"')
    penalty_journal_ids = fields.Many2many(
        'account.journal', 'npd_comm_cfg_penalty_rel', 'config_id', 'journal_id',
        string='สมุดรายวันค่าปรับ',
        help='ค่าปรับหาย/ชำรุด — ไม่นับเป็นยอดเช่า แต่ถ้ายังไม่จ่าย ณ สิ้นรอบ '
             'จะนับเป็นหนี้ค้างชำระ')
    payment_journal_ids = fields.Many2many(
        'account.journal', 'npd_comm_cfg_payment_rel', 'config_id', 'journal_id',
        string='สมุดรายวันรับชำระ')
    gross_payment_journal_ids = fields.Many2many(
        'account.journal', 'npd_comm_cfg_gross_rel', 'config_id', 'journal_id',
        string='สมุดรับชำระที่ไม่ถอด VAT',
        help='ปกติยอดรับชำระถูกถอด VAT ออกก่อน สมุดที่เลือกไว้ตรงนี้จะใช้ยอดเต็ม')
    credit_note_journal_id = fields.Many2one(
        'account.journal', string='สมุดรายวันลดหนี้ขาย',
        help='ใบลดหนี้ในสมุดนี้จะถูกหักออกจากยอดเช่า')

    vat_rate = fields.Float(
        string='อัตรา VAT (%)', default=7.0,
        help='ใช้ถอด VAT ออกจากยอดรับชำระและยอดหนี้ค้าง')

    include_salary_in_expense = fields.Boolean(
        string='รวมค่าจ้างพนักงานเป็นรายจ่าย', default=True,
        help='บวกเงินได้รวมของพนักงานในสาขานั้นเข้าไปในรายจ่าย '
             'เฉพาะสาขาที่มีรายจ่ายอื่นอยู่แล้ว (ตามที่การเงินคิดใน Odoo 14)')

    _sql_constraints = [
        ('company_uniq', 'unique(company_id)',
         'บริษัทนี้มีค่าตั้งค่ารายงานค่าคอมอยู่แล้ว'),
    ]

    # ------------------------------------------------------------------
    @api.model
    def _journals_by_name(self, names, company):
        return self.env['account.journal'].sudo().search([
            ('name', 'in', names), ('company_id', '=', company.id)])

    @api.model
    def get_for(self, company=None):
        """ค่าตั้งค่าของบริษัทนั้น สร้างให้อัตโนมัติถ้ายังไม่มี

        เติมสมุดรายวันตามชื่อที่ NPD ใช้อยู่ให้เลย ถ้าหาไม่เจอก็ปล่อยว่าง
        แล้วให้ผู้ใช้มาเลือกเอง ดีกว่าเดาสมุดผิดแล้วยอดเพี้ยน
        """
        company = company or self.env.company
        config = self.sudo().search([('company_id', '=', company.id)], limit=1)
        if config:
            return config
        vals = {'company_id': company.id}
        for field, names in (
                ('rental_journal_ids', DEFAULT_RENTAL_JOURNALS),
                ('penalty_journal_ids', DEFAULT_PENALTY_JOURNALS),
                ('payment_journal_ids', DEFAULT_PAYMENT_JOURNALS),
                ('gross_payment_journal_ids', DEFAULT_GROSS_PAYMENT_JOURNALS)):
            found = self._journals_by_name(names, company)
            if found:
                vals[field] = [(6, 0, found.ids)]
        cn = self._journals_by_name(DEFAULT_CREDIT_NOTE_JOURNALS, company)
        if cn:
            vals['credit_note_journal_id'] = cn[0].id
        config = self.sudo().create(vals)
        _logger.info('[COMMISSION] สร้างค่าตั้งค่ารายงานค่าคอมของ %s อัตโนมัติ',
                     company.name)
        return config

    def check_ready(self):
        """ตรวจว่าตั้งค่าพอจะคำนวณได้ไหม — บอกให้ชัดดีกว่าคืนยอด 0 เงียบ ๆ"""
        self.ensure_one()
        if not self.rental_journal_ids:
            raise UserError(_(
                'ยังไม่ได้เลือก "สมุดรายวันยอดเช่า" ของบริษัท %s\n'
                'ถ้าไม่เลือก ระบบจะคิดยอดเช่าเป็น 0 ทุกสาขา'
            ) % self.company_id.name)
        return True

    @property
    def vat_divisor(self):
        return 1.0 + (self.vat_rate or 0.0) / 100.0
