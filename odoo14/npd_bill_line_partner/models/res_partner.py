# -*- coding: utf-8 -*-
from odoo import fields, models

# ผู้ขายที่ต้องระบุ Partner รายบรรทัดเสมอ ไม่ต้องติ๊ก: ชื่อมีคำนี้ หรือเลขผู้เสียภาษีตรง (บมจ.ธนาคารกสิกรไทย)
# ตรวจจากชื่อเพราะแต่ละฐานตั้งชื่อไม่เหมือนกัน (บมจ.ธนาคารกสิกรไทย / บริษัท ธนาคารกสิกรไทย จำกัด (มหาชน) ...)
LINE_PARTNER_NAME_KEYWORDS = ('ธนาคารกสิกรไทย',)
LINE_PARTNER_VATS = ('0107536000315',)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    npd_require_line_partner = fields.Boolean(
        string='บังคับระบุ Partner รายบรรทัด (บิลผู้ขาย)',
        help='บิลผู้ขายของผู้ขายรายนี้ ต้องระบุ Partner ที่แท้จริงในแต่ละบรรทัด และในแท็บ Tax Invoice '
             '(เช่น บิลบัตรเติมน้ำมันจากธนาคาร ต้องระบุปั๊มที่ออกใบกำกับภาษี) '
             'ผู้ขายที่ชื่อมีคำว่า ธนาคารกสิกรไทย บังคับอยู่แล้วโดยไม่ต้องติ๊ก')

    def _npd_needs_line_partner(self):
        self.ensure_one()
        for p in (self | self.commercial_partner_id):
            if p.npd_require_line_partner:
                return True
            if any(k in (p.name or '') for k in LINE_PARTNER_NAME_KEYWORDS):
                return True
            if ''.join(ch for ch in (p.vat or '') if ch.isdigit()) in LINE_PARTNER_VATS:
                return True
        return False
