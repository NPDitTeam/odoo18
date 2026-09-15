# -*- coding: utf-8 -*-
"""สาขา เซลล์ และวันที่กำหนดจ่าย บนใบสำคัญจ่าย

รายงานค่าคอมใช้สามอย่างนี้:
* ``branch_id``       จับคู่ค่าขนส่งเข้าสาขา
* ``sales_contact_id``  จับคู่ค่าขนส่งเข้าเซลล์ (หักออกจากยอดเซลล์)
* ``payment_date``    รายจ่ายนับตาม "วันที่กำหนดจ่าย" ไม่ใช่วันที่ออกเอกสาร
"""
from odoo import fields, models


class AccountVoucher(models.Model):
    _inherit = 'account.voucher'

    branch_id = fields.Many2one(
        'res.branch', string='สาขา', copy=True, index=True,
        help='สาขาที่รับผิดชอบรายจ่ายใบนี้ ใช้จัดกลุ่มในรายงานค่าคอม')


class AccountVoucherLine(models.Model):
    _inherit = 'account.voucher.line'

    sales_contact_id = fields.Many2one(
        'res.users', string='Sales ที่ติดต่อ', copy=True, index=True,
        help='เซลล์ที่รับผิดชอบรายการนี้ — ค่าขนส่งจะถูกหักออกจากยอดของเซลล์คนนี้')

    payment_date = fields.Date(
        string='วันที่กำหนดจ่าย', copy=True, index=True,
        help='รายงานค่าคอมนับรายจ่ายตามวันที่กำหนดจ่าย ไม่ใช่วันที่ออกเอกสาร\n'
             'เพราะการเงินปิดยอดตามงวดที่ต้องจ่ายจริง')

    def write(self, vals):
        """ยอมให้แก้สองฟิลด์นี้ได้แม้เอกสารลงบัญชีแล้ว

        ทั้งคู่เป็นข้อมูลประกอบรายงาน ไม่กระทบยอดบัญชี แต่มักกรอกตกหล่น
        และมารู้ตัวตอนปิดค่าคอม ซึ่งตอนนั้นเอกสารลงบัญชีไปแล้วแก้ไม่ได้
        (พฤติกรรมเดียวกับ Odoo 14)
        """
        editable_after_post = {'sales_contact_id', 'payment_date'}
        if vals and set(vals).issubset(editable_after_post) \
                and not self.env.context.get('_npd_voucher_line_bypass'):
            return super(
                AccountVoucherLine,
                self.sudo().with_context(_npd_voucher_line_bypass=True)
            ).write(vals)
        return super().write(vals)
