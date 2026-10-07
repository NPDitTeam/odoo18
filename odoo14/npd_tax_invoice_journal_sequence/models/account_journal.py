# -*- coding: utf-8 -*-
"""เลขใบกำกับภาษี (Tax Invoice Number) แยกตามสมุดรายวันรับชำระ

ภาษีขายแบบรับชำระ (ภาษีขายยังไม่ถึงกำหนด) ออกใบกำกับภาษีตอนรับเงิน
ฝ่ายบัญชีต้องการเลขแบบ CABA แต่ให้แต่ละสมุดรับชำระของแต่ละบริษัทรันเลขของตัวเอง
ไม่รันรวมกัน คำนำหน้าตั้งเองได้ (เช่น CABA- ตามด้วยชื่อย่อบริษัท)

สมุดที่ไม่ได้ติ๊ก → ใช้ค่าเดิมของบริษัท (ตั้งค่า > Customer Tax Invoice Number)
"""
import logging
from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

TAXINV_JOURNAL_TYPES = ('receivable', 'bank', 'cash', 'credit')


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    npd_own_taxinv_sequence = fields.Boolean(
        string='ใช้เลขใบกำกับภาษีของตัวเอง',
        help='ปิดอยู่ = Tax Invoice Number ใช้ค่าเดิมของบริษัท (เลขใบรับชำระ)\n'
             'เปิด = ใบรับชำระในสมุดเล่มนี้ได้เลขใบกำกับภาษีจากเลขรันของเล่มนี้เอง',
    )
    npd_taxinv_prefix = fields.Char(
        string='คำนำหน้าเลขใบกำกับภาษี',
        help='ตัวอย่าง CABA-BKK-  ระบบจะต่อท้ายด้วยวันที่และลำดับให้เอง '
             'เช่น CABA-BKK-261007-0001',
    )
    npd_taxinv_daily = fields.Boolean(
        string='เลขใบกำกับภาษีเริ่มนับใหม่ทุกวัน', default=True,
        help='เปิด = เลขลำดับเริ่ม 0001 ใหม่ทุกวัน และมีวันที่คั่นกลาง (แบบ CABA เดิมของ Odoo 14)\n'
             'ปิด = เลขวิ่งต่อเนื่อง ไม่มีวันที่คั่น',
    )
    npd_taxinv_date_format = fields.Char(
        string='รูปแบบวันที่ของเลขใบกำกับภาษี', default='%y%m%d',
        help='ใช้เมื่อเปิด "เริ่มนับใหม่ทุกวัน" — %y%m%d = 261007, %Y%m%d = 20261007',
    )
    npd_taxinv_padding = fields.Integer(
        string='จำนวนหลักของเลขใบกำกับภาษี', default=4,
        help='4 = 0001',
    )
    npd_taxinv_sequence_id = fields.Many2one(
        'ir.sequence', string='ลำดับเลขใบกำกับภาษีที่สร้างไว้', readonly=True, copy=False,
        help='สร้างจากปุ่ม "สร้าง / อัปเดตเลขใบกำกับภาษี"',
    )
    npd_taxinv_next_number = fields.Char(
        string='ตัวอย่างเลขใบกำกับภาษี', compute='_compute_npd_taxinv_next_number',
        help='ก่อนกดสร้าง = ตัวอย่างจากค่าที่กรอกอยู่ '
             'หลังกดสร้าง = เลขจริงที่ใบถัดไปจะได้ถ้าออกวันนี้',
    )

    # ------------------------------------------------------------------
    @api.depends('npd_taxinv_sequence_id', 'npd_own_taxinv_sequence',
                 'npd_taxinv_prefix', 'npd_taxinv_daily',
                 'npd_taxinv_date_format', 'npd_taxinv_padding')
    def _compute_npd_taxinv_next_number(self):
        for journal in self:
            if not journal.npd_own_taxinv_sequence:
                journal.npd_taxinv_next_number = False
            elif journal.npd_taxinv_sequence_id:
                # อ่านอย่างเดียว ห้าม next_by_id เพราะจะกินเลขจริง
                journal.npd_taxinv_next_number = journal._npd_taxinv_preview_number()
            else:
                journal.npd_taxinv_next_number = journal._npd_taxinv_sample_number()

    def _npd_taxinv_sample_number(self):
        self.ensure_one()
        if not self.npd_taxinv_prefix:
            return _('กรอกคำนำหน้าเลขเพื่อดูตัวอย่าง')
        number = '1'.zfill(self.npd_taxinv_padding or 4)
        if not self.npd_taxinv_daily:
            return _('ตัวอย่าง: %s%s') % (self.npd_taxinv_prefix, number)
        try:
            stamp = self._npd_today().strftime(self.npd_taxinv_date_format or '%y%m%d')
        except (ValueError, TypeError):
            return _('รูปแบบวันที่ไม่ถูกต้อง')
        return _('ตัวอย่าง: %s%s-%s') % (self.npd_taxinv_prefix, stamp, number)

    def _npd_taxinv_preview_number(self):
        self.ensure_one()
        sequence = self.npd_taxinv_sequence_id
        prefix = self.npd_taxinv_prefix or ''
        padding = self.npd_taxinv_padding or 4
        if self.npd_taxinv_daily:
            today = self._npd_today()
            date_range = self.env['ir.sequence.date_range'].sudo().search([
                ('sequence_id', '=', sequence.id),
                ('date_from', '<=', today), ('date_to', '>=', today),
            ], limit=1)
            if not date_range:
                return _('ยังไม่มีช่วงวันที่ของวันนี้ — กดสร้าง/อัปเดตเลขใบกำกับภาษี')
            return '%s%s-%s' % (prefix, date_range.prefix or '',
                                str(date_range.number_next_actual).zfill(padding))
        return '%s%s' % (prefix, str(sequence.number_next_actual).zfill(padding))

    # ------------------------------------------------------------------
    def action_npd_build_taxinv_sequence(self):
        """สร้างหรืออัปเดตเลขรันใบกำกับภาษีของสมุดเล่มนี้ — กดซ้ำได้ ไม่ย้อนเลขที่ออกไปแล้ว"""
        for journal in self:
            journal._npd_build_taxinv_sequence()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('เลขใบกำกับภาษี'),
                'message': _('สร้าง/อัปเดตเลขใบกำกับภาษีให้ %s เล่มแล้ว') % len(self),
                'type': 'success', 'sticky': False,
            },
        }

    def _npd_build_taxinv_sequence(self):
        self.ensure_one()
        if self.type not in TAXINV_JOURNAL_TYPES:
            raise UserError(_('สมุดรายวัน %s เป็นประเภท %s ตั้งเลขใบกำกับภาษีไม่ได้')
                            % (self.display_name, self.type))
        if not self.npd_taxinv_prefix:
            raise UserError(_('ใส่คำนำหน้าเลขก่อน เช่น CABA-BKK- แล้วค่อยกดสร้าง'))

        values = {
            'name': _('ใบกำกับภาษี - %s') % self.display_name,
            'implementation': 'standard',
            'padding': self.npd_taxinv_padding or 4,
            'use_date_range': bool(self.npd_taxinv_daily),
            'company_id': self.company_id.id,
            # เหมือนเลขรับชำระ: วันที่อยู่ใน prefix ของช่วงรายวัน แทนที่ตรง %(prefix)s
            'prefix': ('%s%%(prefix)s-' % self.npd_taxinv_prefix
                       if self.npd_taxinv_daily else self.npd_taxinv_prefix),
        }
        sequence = self.npd_taxinv_sequence_id
        if sequence:
            sequence.write(values)
        else:
            sequence = self.env['ir.sequence'].sudo().create(dict(values, number_next=1))
            self.npd_taxinv_sequence_id = sequence.id
        if self.npd_taxinv_daily:
            self._npd_taxinv_build_date_ranges(sequence)
        _logger.info('[TAXINV SEQ] %s -> %s', self.display_name, sequence.prefix)
        return sequence

    def _npd_taxinv_build_date_ranges(self, sequence):
        """ช่วงรายวันทั้งปี — ที่มีอยู่แล้วไม่แตะ เลขจะได้ไม่ถอยหลัง"""
        self.ensure_one()
        DateRange = self.env['ir.sequence.date_range'].sudo()
        today = self._npd_today()
        year_start, year_end = date(today.year, 1, 1), date(today.year, 12, 31)
        existing = set(DateRange.search([
            ('sequence_id', '=', sequence.id),
            ('date_from', '>=', year_start), ('date_to', '<=', year_end),
        ]).mapped('date_from'))
        fmt = self.npd_taxinv_date_format or '%y%m%d'
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

    def action_npd_copy_taxinv_to_other_companies(self):
        """คัดลอกรูปแบบไปสมุดรหัสเดียวกันของบริษัทอื่น — เลขยังวิ่งแยกกันทุกบริษัท

        คำนำหน้ามักเป็นชื่อย่อบริษัท จึงคัดลอกแค่รูปแบบวันที่/จำนวนหลัก
        คำนำหน้าของบริษัทปลายทางต้องกรอกเองแล้วกดสร้าง
        """
        self.ensure_one()
        if not self.npd_own_taxinv_sequence:
            raise UserError(_('ติ๊ก "ใช้เลขใบกำกับภาษีของตัวเอง" ให้เล่มนี้ก่อน'))
        if not self.code:
            raise UserError(_('สมุดเล่มนี้ไม่มีรหัส คัดลอกด้วยรหัสไม่ได้'))
        targets = self.sudo().search([
            ('code', '=', self.code),
            ('company_id', '!=', self.company_id.id),
            ('type', '=', self.type),
        ])
        done, skipped = [], []
        for journal in targets:
            if journal.npd_own_taxinv_sequence:
                skipped.append(journal.company_id.name)
                continue
            journal.write({
                'npd_own_taxinv_sequence': True,
                'npd_taxinv_daily': self.npd_taxinv_daily,
                'npd_taxinv_date_format': self.npd_taxinv_date_format,
                'npd_taxinv_padding': self.npd_taxinv_padding,
            })
            done.append(journal.company_id.name)
        message = (_('คัดลอกรูปแบบไป %s บริษัท: %s — กรอกคำนำหน้า (ชื่อย่อบริษัท) '
                     'แล้วกดสร้างที่สมุดของแต่ละบริษัท') % (len(done), ', '.join(done))
                   if done else _('ไม่มีบริษัทไหนให้คัดลอก'))
        if skipped:
            message += chr(10) + _('ข้ามเพราะตั้งไว้แล้ว: %s') % ', '.join(skipped)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': _('คัดลอกเลขใบกำกับภาษี'), 'message': message,
                       'type': 'success', 'sticky': True},
        }

    # ------------------------------------------------------------------
    def _npd_next_taxinv_number(self, sequence_date=None):
        """เลขใบกำกับภาษีถัดไปของเล่มนี้ — None ถ้าเล่มนี้ไม่ได้ตั้งไว้"""
        self.ensure_one()
        if not self.npd_own_taxinv_sequence or not self.npd_taxinv_sequence_id:
            return None
        return self.npd_taxinv_sequence_id.sudo().next_by_id(
            sequence_date=sequence_date) or None
