# -*- coding: utf-8 -*-
from odoo import api, models


class AccountMoveReversal(models.TransientModel):
    _inherit = 'account.move.reversal'

    # ต้องประกาศ depends เดิมซ้ำ เพราะ override ไปแทนที่ method ใน MRO
    # ถ้าไม่ประกาศ ฟิลด์จะไม่ recompute เลย
    @api.depends('move_ids')
    def _compute_journal_id(self):
        for record in self:
            if record.journal_id:
                # ผู้ใช้เลือกเองแล้ว ไม่ทับ
                continue
            company = record.company_id or record.move_ids.company_id[:1]
            record.journal_id = self.env['npd.invoice.journal.config']._get_journal(
                company, 'credit_note',
            ) or False
        # ใบที่ยังว่างอยู่ (ยังไม่ได้ตั้งค่าในเมนู) ปล่อยให้ Odoo
        # ใช้สมุดรายวันของใบแจ้งหนี้ต้นทางตามเดิม
        return super()._compute_journal_id()
