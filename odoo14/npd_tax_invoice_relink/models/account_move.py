# -*- coding: utf-8 -*-
"""ผูกแถวในแท็บ Tax Invoice ที่ไม่ได้ผูกกับบรรทัดภาษี (ผู้ใช้สั่ง 22 ต.ค. 2569)

เคสจริง AP-0930260001 (S Group): บิลค่าบัตรฟลีทการ์ด 6 ใบกำกับ ผูกแค่ 3 แถว
→ ภาษี 392.52 แต่ใบกำกับที่ผูกรวม 196.26 → "Invalid Tax Amount" ตอนยืนยัน
"""
from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class AccountMove(models.Model):
    _inherit = 'account.move'

    npd_taxinv_orphan_count = fields.Integer(
        string='ใบกำกับภาษีที่ไม่ได้ผูก', compute='_compute_npd_taxinv_orphan_count')

    def _compute_npd_taxinv_orphan_count(self):
        for move in self:
            move.npd_taxinv_orphan_count = len(
                move.tax_invoice_ids.filtered(lambda t: not t.move_line_id))

    def _npd_relink_tax_invoices(self, strict=False):
        """คืนจำนวนแถวที่ผูกได้ · strict=True (กดปุ่ม) = ผูกไม่ได้ให้แจ้งเหตุผล"""
        done = 0
        for move in self:
            if move.state != 'draft':
                continue
            orphans = move.tax_invoice_ids.filtered(lambda t: not t.move_line_id)
            if not orphans:
                continue
            tax_lines = move.line_ids.filtered('tax_line_id')
            if len(tax_lines) != 1:
                if strict:
                    raise UserError(_(
                        '%s มีบรรทัดภาษี %s บรรทัด ระบบเลือกให้เองไม่ได้ว่าใบกำกับไหนเป็นของบรรทัดไหน\n'
                        'กรุณาลบแถวที่ไม่ได้ผูก แล้วใช้ปุ่ม Split (ไอคอนก็อป) ท้ายแถวเดิมแทนการกด "เพิ่มรายการ"')
                        % (move.name, len(tax_lines)))
                continue
            tax_line = tax_lines
            target = abs(tax_line.balance)
            linked = move.tax_invoice_ids - orphans
            orphan_sum = sum(orphans.mapped('balance'))
            blank = linked.filtered(lambda t: not t.tax_invoice_number)
            if float_compare(abs(sum(linked.mapped('balance')) + orphan_sum), target, 2) == 0:
                orphans.write({'move_line_id': tax_line.id})
            elif blank and float_compare(
                    abs(sum((linked - blank).mapped('balance')) + orphan_sum), target, 2) == 0:
                # แถวว่างที่ระบบสร้างเอง แต่ผู้ใช้กรอกเลขจริงไว้ในแถวใหม่ครบยอดแล้ว → แถวว่างเกิน
                orphans.write({'move_line_id': tax_line.id})
                blank.with_context(force_remove_tax_invoice=True).unlink()
            else:
                if strict:
                    raise UserError(_(
                        'ยอดใบกำกับภาษีไม่ตรงกับภาษีของเอกสาร %s\n'
                        'ภาษีในเอกสาร: %s\nใบกำกับที่ผูกแล้ว: %s\nใบกำกับที่ยังไม่ผูก: %s\n'
                        'กรุณาตรวจยอดในแท็บ Tax Invoice')
                        % (move.name, '{:,.2f}'.format(target),
                           '{:,.2f}'.format(abs(sum(linked.mapped('balance')))),
                           '{:,.2f}'.format(abs(orphan_sum))))
                continue
            done += len(orphans)
        if done:
            self.invalidate_recordset(['tax_invoice_ids', 'npd_taxinv_orphan_count'])
        return done

    def action_npd_relink_tax_invoices(self):
        count = self._npd_relink_tax_invoices(strict=True)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('ผูกใบกำกับภาษีแล้ว'),
                'message': _('ผูกใบกำกับภาษี %s แถว กดยืนยันได้เลย') % count,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def action_post(self):
        # บางฐานมีขั้นอนุมัติดักก่อนถึง _post — ผูกตั้งแต่กดปุ่มด้วย
        self._npd_relink_tax_invoices()
        return super().action_post()

    def _post(self, soft=True):
        # ผูกให้เองก่อนโมดูลภาษีไทยตรวจยอด (ผูกเฉพาะเมื่อยอดตรง ไม่ตรงก็ปล่อยให้ขึ้น Invalid Tax Amount ตามเดิม)
        self._npd_relink_tax_invoices()
        return super()._post(soft=soft)
