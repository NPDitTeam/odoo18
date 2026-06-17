import pytz
from datetime import datetime

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.addons.base.models.ir_sequence import _select_nextval, _update_nogap


class IrSequence(models.Model):
    _inherit = "ir.sequence"

    def _get_prefix_suffix(self, date=None, date_range=None):
        """ขยายมาตรฐาน: รองรับตัวแปร %(prefix)s / %(suffix)s ใน prefix/suffix
        ของ sequence หลัก โดยค่าจะถูกเติมจาก prefix/suffix ของ date_range
        (ส่งผ่าน context: ir_sequence_dr_prefix / ir_sequence_dr_suffix)

        ถ้า sequence ไม่ได้ใช้ %(prefix)s / %(suffix)s เลย จะ fallback ไปใช้
        ของมาตรฐานทั้งหมด เพื่อไม่กระทบ sequence อื่นในระบบ
        """
        seq_prefix = self.prefix or ''
        seq_suffix = self.suffix or ''
        uses_dr_var = (
            '%(prefix)' in seq_prefix or '%(suffix)' in seq_prefix
            or '%(prefix)' in seq_suffix or '%(suffix)' in seq_suffix
        )
        if not uses_dr_var:
            return super()._get_prefix_suffix(date=date, date_range=date_range)

        dr_prefix = self._context.get('ir_sequence_dr_prefix') or ''
        dr_suffix = self._context.get('ir_sequence_dr_suffix') or ''

        def _interpolate(s, d):
            return (s % d) if s else ''

        def _interpolation_dict():
            now = range_date = effective_date = datetime.now(
                pytz.timezone(self._context.get('tz') or 'UTC'))
            if date or self._context.get('ir_sequence_date'):
                effective_date = fields.Datetime.from_string(
                    date or self._context.get('ir_sequence_date'))
            if date_range or self._context.get('ir_sequence_date_range'):
                range_date = fields.Datetime.from_string(
                    date_range or self._context.get('ir_sequence_date_range'))

            sequences = {
                'year': '%Y', 'month': '%m', 'day': '%d', 'y': '%y', 'doy': '%j',
                'woy': '%W', 'weekday': '%w', 'h24': '%H', 'h12': '%I',
                'min': '%M', 'sec': '%S',
            }
            res = {}
            for key, fmt in sequences.items():
                res[key] = effective_date.strftime(fmt)
                res['range_' + key] = range_date.strftime(fmt)
                res['current_' + key] = now.strftime(fmt)
            res.update({'prefix': dr_prefix, 'suffix': dr_suffix})
            return res

        self.ensure_one()
        d = _interpolation_dict()
        try:
            interpolated_prefix = _interpolate(seq_prefix, d)
            interpolated_suffix = _interpolate(seq_suffix, d)
        except (ValueError, TypeError, KeyError):
            raise UserError(_('Invalid prefix or suffix for sequence "%s"', self.name))
        return interpolated_prefix, interpolated_suffix

    # ---- ปุ่มบนฟอร์ม ir.sequence ----
    def generate_sub_sequences(self):
        self.ensure_one()
        return {
            'name': _('Generate Sub Sequence'),
            'res_model': 'generate.sub.sequences',
            'view_mode': 'form',
            'context': {
                'active_model': 'ir.sequence',
                'active_ids': self.ids,
            },
            'target': 'new',
            'type': 'ir.actions.act_window',
        }

    def delete_sub_sequences(self):
        """ลบเฉพาะช่วงวันที่ที่ยังไม่ถูกใช้ออกเลข (number_next_actual <= 1)"""
        for seq in self:
            for sub in seq.date_range_ids:
                if sub.number_next_actual <= 1:
                    sub.sudo().unlink()


class IrSequenceDateRange(models.Model):
    _inherit = "ir.sequence.date_range"

    prefix = fields.Char(
        help="Prefix เฉพาะของช่วงวันที่นี้ (เติมในตำแหน่ง %(prefix)s ของ sequence หลัก)")
    suffix = fields.Char(
        help="Suffix เฉพาะของช่วงวันที่นี้ (เติมในตำแหน่ง %(suffix)s ของ sequence หลัก)")

    def _next(self):
        # ถ้าช่วงนี้ไม่มี prefix/suffix เฉพาะ -> ใช้พฤติกรรมมาตรฐาน
        if not self.prefix and not self.suffix:
            return super()._next()
        seq = self.sequence_id.with_context(
            ir_sequence_dr_prefix=self.prefix or '',
            ir_sequence_dr_suffix=self.suffix or '',
        )
        if seq.implementation == 'standard':
            number_next = _select_nextval(
                self._cr, 'ir_sequence_%03d_%03d' % (seq.id, self.id))
        else:
            number_next = _update_nogap(self, seq.number_increment)
        return seq.get_next_char(number_next)
