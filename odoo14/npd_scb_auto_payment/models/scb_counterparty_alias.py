# -*- coding: utf-8 -*-
u"""ชื่อผู้โอนที่ธนาคารบันทึก ผูกกับลูกค้าใน Odoo (ระบบจดจำเอง)

ปัญหา: ธนาคารถอดชื่อไทยเป็นอังกฤษแบบไม่เป็นมาตรฐาน จนเทียบด้วยกฎไม่ได้
    ธราธร        -> ธนาคารเขียน "THATAROTH GHEER"   (มาตรฐานคือ THARATHORN)
    กฤษฎิ์มีชัย  -> ธนาคารเขียน "KITMEECHAI THONG"  (มาตรฐานคือ KRITMEECHAI)
ไล่เขียนกฎถอดเสียงเท่าไรก็ไม่ครบ เพราะขึ้นกับว่าธนาคารพิมพ์มาอย่างไร

วิธีแก้: ครั้งแรกให้ AI ตัดสิน แล้ว "จำ" ไว้ว่าชื่อนี้ของธนาคาร = ลูกค้าคนนี้
ครั้งต่อไปที่ลูกค้าคนเดิมโอนมา ระบบเทียบได้ทันทีโดยไม่ต้องเรียก AI อีก
— ธุรกิจให้เช่าเป็นลูกค้าประจำ โอนซ้ำทุกเดือน จึงคุ้มมาก
"""
import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class ScbCounterpartyAlias(models.Model):
    _name = 'npd.scb.counterparty.alias'
    _description = u'ชื่อผู้โอนที่จดจำไว้ (ธนาคาร -> ลูกค้า)'
    _order = 'partner_id, name'
    _rec_name = 'name'

    partner_id = fields.Many2one(
        'res.partner', string=u'ลูกค้า', required=True, index=True,
        ondelete='cascade')
    name = fields.Char(
        string=u'ชื่อที่ธนาคารบันทึก', required=True,
        help=u'ตามที่ปรากฏในคอลัมน์รายละเอียดของ statement เช่น MR.THATAROTH GHEER')
    name_key = fields.Char(
        string=u'คีย์เทียบ', index=True, readonly=True,
        help=u'ชื่อที่ย่อให้เหลือแก่นชื่อแล้ว ใช้กันบันทึกซ้ำ')
    source = fields.Selection([
        ('scb', 'SCB'), ('kbank', 'Kbank'), ('ktb', u'กรุงไทย'),
    ], string=u'ธนาคาร')
    account_digits = fields.Char(string=u'เลขบัญชีย่อ', readonly=True)
    origin = fields.Selection([
        ('auto', u'ระบบจดจำอัตโนมัติ'),
        ('manual', u'เพิ่มเอง'),
    ], string=u'ที่มา', default='manual', required=True, index=True)
    payment_id = fields.Many2one(
        'account.payment', string=u'จดจำจากใบรับชำระ', readonly=True,
        ondelete='set null')
    note = fields.Char(string=u'หมายเหตุ')
    active = fields.Boolean(string=u'ใช้งาน', default=True)

    _sql_constraints = [
        ('partner_name_uniq', 'unique(partner_id, name_key)',
         u'ชื่อผู้โอนนี้ถูกจดจำไว้กับลูกค้ารายนี้แล้ว'),
    ]

    # ------------------------------------------------------------------
    @api.model
    def _key(self, name):
        u"""ย่อชื่อให้เหลือแก่นชื่อ (ใช้ตัวเดียวกับตอนเทียบชื่อใน statement)"""
        return self.env['npd.scb.bank.statement']._normalize_name(name or '')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name'):
                vals['name_key'] = self._key(vals['name'])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('name'):
            vals['name_key'] = self._key(vals['name'])
        return super(ScbCounterpartyAlias, self).write(vals)

    @api.model
    def names_for_partner(self, partner):
        u"""ชื่อที่เคยจำไว้ทั้งหมดของลูกค้ารายนี้ (ใช้ต่อท้ายรายชื่อตอนจับคู่)"""
        if not partner:
            return []
        return self.search([('partner_id', '=', partner.id)]).mapped('name')

    @api.model
    def remember(self, partner, statement, payment=None):
        u"""จดจำว่า "ชื่อคู่ค้าในรายการธนาคารนี้" คือลูกค้ารายนี้

        เรียกทุกครั้งที่จับคู่สำเร็จ ถ้าจำไว้แล้วจะไม่สร้างซ้ำ

        ครอบด้วย savepoint เพราะการจดจำเป็นแค่ของแถม ถ้าล้มเหลว (เช่นชน unique
        constraint) ต้องไม่ทำให้ transaction ของ "การตรวจสอบการโอน" พังไปด้วย
        """
        if not partner or not statement or not statement.counterparty:
            return self.browse()
        key = self._key(statement.counterparty)
        if not key:
            return self.browse()
        # active_test=False สำคัญ — ถ้ามีรายการที่ถูก archive ไว้ search ปกติจะมองไม่เห็น
        # แล้วไปสร้างใหม่จนชน unique constraint (partner_id, name_key)
        existing = self.with_context(active_test=False).search([
            ('partner_id', '=', partner.id), ('name_key', '=', key),
        ], limit=1)
        if existing:
            return existing
        try:
            with self.env.cr.savepoint():
                return self.create({
                    'partner_id': partner.id,
                    'name': statement.counterparty,
                    'source': statement.source,
                    'account_digits': statement.counterparty_acc or False,
                    'origin': 'auto',
                    'payment_id': payment.id if payment else False,
                })
        except Exception:  # noqa: BLE001 - จดจำไม่ได้ก็ไม่เป็นไร
            _logger.warning(
                "SCB: จดจำชื่อผู้โอน %r ของลูกค้า %s ไม่สำเร็จ",
                statement.counterparty, partner.display_name, exc_info=True)
            return self.browse()
