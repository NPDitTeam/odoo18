from datetime import date, datetime

from dateutil.rrule import rrule, DAILY, MONTHLY

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class GenerateSubSequences(models.TransientModel):
    _name = "generate.sub.sequences"
    _description = "Generate Sub Sequences Wizard"

    prefix = fields.Char('Format Sub Seq', default="%(month)s%(day)s", required=True)
    year = fields.Integer(
        'Year', required=True,
        default=lambda self: fields.Date.context_today(self).year)
    generate_date_month = fields.Selection([
        ('date', 'Date'),
        ('month', 'Month'),
    ], string='Generate', default='date', required=True)

    @api.onchange('generate_date_month')
    def _onchange_generate_date_month(self):
        if self.generate_date_month == 'date':
            self.prefix = '%(month)s%(day)s'
        else:
            self.prefix = '%(month)s'

    def _interpolated_prefix(self, the_date):
        """แปลงรูปแบบ prefix (เช่น %(month)s%(day)s) เป็นข้อความจริงของวันนั้น
        เพื่อเก็บลงใน date_range.prefix (ค่าคงที่ของช่วงวันนั้น)"""
        self.ensure_one()
        d = datetime(the_date.year, the_date.month, the_date.day)
        mapping = {
            'year': d.strftime('%Y'), 'month': d.strftime('%m'), 'day': d.strftime('%d'),
            'y': d.strftime('%y'), 'doy': d.strftime('%j'), 'woy': d.strftime('%W'),
            'weekday': d.strftime('%w'), 'h24': d.strftime('%H'), 'h12': d.strftime('%I'),
            'min': d.strftime('%M'), 'sec': d.strftime('%S'),
        }
        try:
            return (self.prefix % mapping) if self.prefix else ''
        except (ValueError, KeyError, TypeError):
            raise UserError(_('รูปแบบ Format Sub Seq ไม่ถูกต้อง: %s') % self.prefix)

    def action_generate(self):
        self.ensure_one()
        sequences = self.env['ir.sequence'].browse(self._context.get('active_ids', []))
        sequences = sequences.exists()
        if not sequences:
            raise UserError(_('ไม่พบ Sequence ที่เลือก'))

        DateRange = self.env['ir.sequence.date_range'].sudo()
        start_date = date(self.year, 1, 1)
        end_date = date(self.year, 12, 31)

        for seq in sequences:
            if self.generate_date_month == 'date':
                for dt in rrule(DAILY, dtstart=start_date, until=end_date):
                    d = dt.date()
                    self._create_or_update_range(DateRange, seq, d, d)
            else:
                for dt in rrule(MONTHLY, dtstart=start_date, until=end_date, bymonthday=-1):
                    d_to = dt.date()
                    d_from = date(d_to.year, d_to.month, 1)
                    self._create_or_update_range(DateRange, seq, d_from, d_to)
        return {'type': 'ir.actions.act_window_close'}

    def _create_or_update_range(self, DateRange, seq, date_from, date_to):
        """สร้างช่วงวันที่ ถ้ามีอยู่แล้ว (ติด unique constraint) ให้อัปเดต prefix แทน"""
        prefix_val = self._interpolated_prefix(date_from)
        existing = DateRange.search([
            ('sequence_id', '=', seq.id),
            ('date_from', '=', date_from),
            ('date_to', '=', date_to),
        ], limit=1)
        if existing:
            existing.write({'prefix': prefix_val})
        else:
            DateRange.create({
                'sequence_id': seq.id,
                'date_from': date_from,
                'date_to': date_to,
                'prefix': prefix_val,
            })
