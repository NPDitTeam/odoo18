# -*- coding: utf-8 -*-
"""สาขา เซลล์ และวันที่กำหนดจ่าย บนใบสำคัญจ่าย

รายงานค่าคอมใช้สามอย่างนี้:
* ``branch_id``       จับคู่ค่าขนส่งเข้าสาขา
* ``sales_contact_id``  จับคู่ค่าขนส่งเข้าเซลล์ (หักออกจากยอดเซลล์)
* ``payment_date``    รายจ่ายนับตาม "วันที่กำหนดจ่าย" ไม่ใช่วันที่ออกเอกสาร
"""
from odoo import api, fields, models

# เหมือน Odoo 14 (account_advance_sales_contact) — เลือกได้เฉพาะผู้ใช้ที่เป็นพนักงานแผนก Sales
# o14 ใช้ employee_ids.department_id ตรง ๆ แต่ o18 อยู่ DB เดียวหลายบริษัท กฎบริษัทของ hr.employee
# จะซ่อนเซลล์ที่อยู่บริษัทอื่น จึงค้นผ่านฟิลด์ npd_is_sales (sudo) แทน
SALES_USER_DOMAIN = "[('npd_is_sales', '=', True)]"


class AccountVoucher(models.Model):
    _inherit = 'account.voucher'

    branch_id = fields.Many2one(
        'res.branch', string='สาขา', copy=True, index=True,
        help='สาขาที่รับผิดชอบรายจ่ายใบนี้ ใช้จัดกลุ่มในรายงานค่าคอม')

    @api.model
    def default_get(self, fields_list):
        """สาขาเริ่มต้น = สาขาใน context หรือสาขาหลักของผู้ใช้ (เหมือน Odoo 14
        account_invoice_sale_purchase_receipt_branch)"""
        res = super().default_get(fields_list)
        if 'branch_id' in fields_list and not res.get('branch_id'):
            branch_id = self.env.context.get('branch_id') or self.env.user.branch_id.id
            if branch_id:
                res['branch_id'] = branch_id
        return res

    def action_edit_sales_contact(self):
        """แก้ Sales ที่ติดต่อ / วันที่กำหนดจ่าย หลังลงบัญชีแล้ว (ปุ่มเดียวกับ Odoo 14)"""
        self.ensure_one()
        return {
            'name': 'แก้ไข Sales และ วันที่กำหนดจ่าย',
            'type': 'ir.actions.act_window',
            'res_model': 'wizard.edit.sales.contact',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_voucher_id': self.id},
        }


class AccountVoucherLine(models.Model):
    _inherit = 'account.voucher.line'

    sales_contact_id = fields.Many2one(
        'res.users', string='Sales ที่ติดต่อ', copy=True, index=True,
        domain=SALES_USER_DOMAIN,
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
