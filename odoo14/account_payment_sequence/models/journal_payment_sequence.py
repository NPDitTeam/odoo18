# -*- coding: utf-8 -*-
"""เลขรันใบรับ/จ่ายชำระ แยกตามสมุดรายวันได้

เดิมทุกสมุดรายวันในบริษัทเดียวกันใช้เลขชุดเดียวกัน (CUST.IN-260928-0008)
พอมีสมุดรับชำระหลายเล่ม (ค่าประกัน / ค่าปรับหาย / ค่าปรับชำรุด / ลดหนี้)
เลขจึงวิ่งปนกันทั้งที่เป็นคนละประเภทเอกสาร ตามหาย้อนหลังลำบาก

ไฟล์นี้เปิดให้ตั้งเลขรันของแต่ละเล่มได้ โดย **ไม่แตะค่าเดิม**
เล่มที่ไม่ได้ติ๊กจะยังใช้เลขกลางของบริษัทเหมือนเดิมทุกประการ
"""
import logging
from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# ประเภทสมุดรายวันที่ตั้งเลขรับ/จ่ายชำระของตัวเองได้
PAYMENT_JOURNAL_TYPES = ('receivable', 'payable', 'bank', 'cash', 'credit')


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    npd_own_payment_sequence = fields.Boolean(
        string='ใช้เลขรับชำระของตัวเอง',
        help='ปิดอยู่ = ใช้เลขกลางของบริษัท (CUST.IN / SUPP.OUT) เหมือนเดิม\n'
             'เปิด = สมุดเล่มนี้มีเลขรันของตัวเอง ไม่ปนกับเล่มอื่น',
    )
    npd_payment_prefix = fields.Char(
        string='คำนำหน้าเลข',
        help='ตัวอย่าง INS.IN-  ระบบจะต่อท้ายด้วยวันที่และลำดับให้เอง '
             'เช่น INS.IN-260928-0001',
    )
    npd_payment_daily = fields.Boolean(
        string='เริ่มนับใหม่ทุกวัน', default=True,
        help='เปิด = เลขลำดับเริ่ม 0001 ใหม่ทุกวัน และมีวันที่คั่นกลาง '
             '(แบบเดียวกับเลขกลาง CUST.IN ที่ใช้อยู่)\n'
             'ปิด = เลขวิ่งต่อเนื่องทั้งปี ไม่มีวันที่คั่น',
    )
    npd_payment_date_format = fields.Char(
        string='รูปแบบวันที่', default='%y%m%d',
        help='ใช้เมื่อเปิด "เริ่มนับใหม่ทุกวัน" — %y%m%d = 260928, '
             '%%m%%d%%y = 092826, %%Y%%m%%d = 20260928',
    )
    npd_payment_padding = fields.Integer(
        string='จำนวนหลักของลำดับ', default=4,
        help='4 = 0001  ถ้าคาดว่าจะเกินหมื่นใบต่อวันค่อยเพิ่ม',
    )
    npd_payment_sequence_id = fields.Many2one(
        'ir.sequence', string='ลำดับเลขที่สร้างไว้', readonly=True, copy=False,
        help='สร้างจากปุ่ม "สร้าง/อัปเดตเลขรัน" ด้านบน',
    )
    npd_payment_next_number = fields.Char(
        string='เลขถัดไป', compute='_compute_npd_payment_next_number',
        help='เลขที่ใบถัดไปจะได้ ถ้าออกวันนี้',
    )

    # ------------------------------------------------------------------
    @api.depends('npd_payment_sequence_id', 'npd_own_payment_sequence')
    def _compute_npd_payment_next_number(self):
        for journal in self:
            sequence = journal.npd_payment_sequence_id
            if not journal.npd_own_payment_sequence or not sequence:
                journal.npd_payment_next_number = False
                continue
            # อ่านอย่างเดียว ห้ามใช้ next_by_id เพราะจะกินเลขจริงไปหนึ่งหมายเลข
            journal.npd_payment_next_number = journal._npd_preview_number()

    def _npd_preview_number(self):
        """เลขถัดไปแบบดูเฉย ๆ ไม่กินเลขจริง"""
        self.ensure_one()
        sequence = self.npd_payment_sequence_id
        if not sequence:
            return False
        today = self._npd_today()
        prefix = self.npd_payment_prefix or ''
        if self.npd_payment_daily:
            date_range = self.env['ir.sequence.date_range'].sudo().search([
                ('sequence_id', '=', sequence.id),
                ('date_from', '<=', today), ('date_to', '>=', today),
            ], limit=1)
            if not date_range:
                return _('ยังไม่มีช่วงวันที่ของวันนี้ — กดสร้าง/อัปเดตเลขรัน')
            return '%s%s-%s' % (prefix, date_range.prefix or '',
                                str(date_range.number_next_actual).zfill(
                                    self.npd_payment_padding or 4))
        return '%s%s' % (prefix, str(sequence.number_next_actual).zfill(
            self.npd_payment_padding or 4))

    @api.model
    def _npd_today(self):
        return fields.Datetime.context_timestamp(
            self.with_context(tz='Asia/Bangkok'), fields.Datetime.now()).date()

    # ------------------------------------------------------------------
    def action_npd_build_payment_sequence(self):
        """สร้างหรืออัปเดตลำดับเลขของสมุดเล่มนี้ — กดซ้ำได้ ไม่ย้อนเลขที่ออกไปแล้ว"""
        for journal in self:
            journal._npd_build_payment_sequence()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('เลขรับชำระ'),
                'message': _('สร้าง/อัปเดตเลขรันให้ %s เล่มแล้ว') % len(self),
                'type': 'success', 'sticky': False,
            },
        }

    def _npd_build_payment_sequence(self):
        self.ensure_one()
        if self.type not in PAYMENT_JOURNAL_TYPES:
            raise UserError(_(
                'สมุดรายวัน %s เป็นประเภท %s ตั้งเลขรับชำระไม่ได้')
                % (self.display_name, self.type))
        if not self.npd_payment_prefix:
            raise UserError(_(
                'ใส่คำนำหน้าเลขก่อน เช่น INS.IN- แล้วค่อยกดสร้าง'))

        Sequence = self.env['ir.sequence'].sudo()
        values = {
            'name': _('รับ/จ่ายชำระ - %s') % self.display_name,
            'implementation': 'standard',
            'padding': self.npd_payment_padding or 4,
            'use_date_range': bool(self.npd_payment_daily),
            'company_id': self.company_id.id,
            # ช่วงรายวันเก็บวันที่ไว้ใน prefix ของช่วง ส่วน sequence หลักใส่
            # ตัวแปร %(prefix)s ไว้ให้โมดูล npd_generate_subsequences แทนค่าให้
            # ผลออกมาเป็น INS.IN-260928-0001
            'prefix': ('%s%%(prefix)s-' % self.npd_payment_prefix
                       if self.npd_payment_daily else self.npd_payment_prefix),
        }
        sequence = self.npd_payment_sequence_id
        if sequence:
            sequence.write(values)
        else:
            sequence = Sequence.create(dict(values, number_next=1))
            self.npd_payment_sequence_id = sequence.id

        if self.npd_payment_daily:
            self._npd_build_date_ranges(sequence)
        _logger.info('[PAYMENT SEQ] %s -> %s', self.display_name, sequence.prefix)
        return sequence

    def _npd_build_date_ranges(self, sequence):
        """สร้างช่วงรายวันทั้งปีให้ครบ — ที่มีอยู่แล้วไม่แตะ เลขจะได้ไม่ถอยหลัง"""
        self.ensure_one()
        DateRange = self.env['ir.sequence.date_range'].sudo()
        today = self._npd_today()
        year_start, year_end = date(today.year, 1, 1), date(today.year, 12, 31)
        existing = set(DateRange.search([
            ('sequence_id', '=', sequence.id),
            ('date_from', '>=', year_start), ('date_to', '<=', year_end),
        ]).mapped('date_from'))
        fmt = self.npd_payment_date_format or '%y%m%d'
        days = [year_start + timedelta(days=i)
                for i in range((year_end - year_start).days + 1)]
        missing = [d for d in days if d not in existing]
        if missing:
            DateRange.create([{
                'sequence_id': sequence.id,
                'date_from': day, 'date_to': day,
                'prefix': day.strftime(fmt),
            } for day in missing])
        return len(missing)

    # ------------------------------------------------------------------
    def _npd_next_payment_number(self, sequence_date=None):
        """เลขถัดไปของสมุดเล่มนี้ — คืน None ถ้าเล่มนี้ไม่ได้ตั้งเลขของตัวเอง

        ตัวที่เรียกต้องถอยไปใช้เลขกลางของบริษัทเมื่อได้ None
        """
        self.ensure_one()
        if not self.npd_own_payment_sequence or not self.npd_payment_sequence_id:
            return None
        # next_by_id หาช่วงวันที่ให้เอง และโมดูล npd_generate_subsequences
        # จะเติมวันที่ลงตำแหน่ง %(prefix)s ให้ตอนออกเลข
        number = self.npd_payment_sequence_id.sudo().next_by_id(
            sequence_date=sequence_date)
        return number or None
