# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext, is_html_empty, plaintext2html


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ช่องเงื่อนไขและข้อกำหนดแบบข้อความธรรมดาบนฟอร์ม (ผู้ใช้ไม่เอาตัวแก้ HTML, 22 ต.ค. 2569)
    # ข้อมูลยังเก็บใน narration (Html) เดิม รายงานที่อ่าน narration จึงใช้ได้เหมือนเดิม
    npd_narration_text = fields.Text(
        string='เงื่อนไขและข้อกำหนด',
        compute='_compute_npd_narration_text', inverse='_inverse_npd_narration_text')

    def _compute_npd_narration_text(self):
        for move in self:
            move.npd_narration_text = '' if is_html_empty(move.narration) else html2plaintext(move.narration)

    def _inverse_npd_narration_text(self):
        for move in self:
            text = (move.npd_narration_text or '').strip()
            move.narration = plaintext2html(text) if text else False

    def action_post(self):
        # ใบลดหนี้ลูกค้าที่ยืนยันครั้งแรกต้องมี เงื่อนไขและข้อกำหนด (ผู้ใช้สั่ง 22 ต.ค. 2569)
        missing = self.filtered(
            lambda m: m.move_type == 'out_refund' and not m.posted_before
            and is_html_empty(m.narration))
        if missing:
            raise UserError(
                'กรุณากรอก "เงื่อนไขและข้อกำหนด" (หมายเหตุ) ของใบลดหนี้ก่อนยืนยัน\n%s'
                % ', '.join(missing.mapped(lambda m: m.name if m.name and m.name != '/' else 'ใบลดหนี้ร่าง')))
        return super().action_post()
