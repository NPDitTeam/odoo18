# -*- coding: utf-8 -*-
"""เซลล์ผู้ติดต่อและประเภทสินค้าบนใบแจ้งหนี้

``contact_type`` มีอยู่แล้วในระบบ (จาก pfb_npd_all_customs) ไฟล์นี้จึงเพิ่ม
เฉพาะสองฟิลด์ที่ยังขาด และรายงานค่าคอมต้องใช้
"""
from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    sales_contact_id = fields.Many2one(
        'res.users', string='Sales ที่ติดต่อ',
        tracking=True, copy=True, index=True, readonly=True,
        help='เซลล์ที่ติดต่อลูกค้า คัดลอกมาจากใบสั่งขายตอนออกใบแจ้งหนี้\n'
             'ล็อกไม่ให้แก้ที่ใบแจ้งหนี้ เพื่อให้ยอดค่าคอมตรงกับใบสั่งขายเสมอ '
             '(แก้ผ่านโค้ด/นำเข้าข้อมูลยังได้)')

    reason_code_id = fields.Many2one(
        'scrap.reason.code', string='ประเภทสินค้า', copy=True, index=True,
        help='ใช้แยกว่าใบนี้เป็นใบค่าปรับสินค้าหาย/ชำรุด '
             'รายงานค่าคอมนับใบพวกนี้เป็นหนี้ค้างชำระ แต่ไม่นับเป็นยอดเช่า')

    DEFAULT_REASON_CODE = 'ใบแจ้งหนี้ค่าเช่า'

    @api.model
    def _npd_default_reason_code(self):
        """ประเภทสินค้าค่าเริ่มต้นของใบแจ้งหนี้ลูกค้า = ใบแจ้งหนี้ค่าเช่า (ไม่มี xmlid จึงหาจากชื่อ)"""
        return self.env['scrap.reason.code'].sudo().search(
            [('name', '=', self.DEFAULT_REASON_CODE)], limit=1)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if ('reason_code_id' in fields_list and not res.get('reason_code_id')
                and (res.get('move_type') or self.env.context.get('default_move_type')) == 'out_invoice'):
            code = self._npd_default_reason_code()
            if code:
                res['reason_code_id'] = code.id
        return res
