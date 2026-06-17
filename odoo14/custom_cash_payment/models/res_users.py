from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    # ติ๊กถูกที่หน้าตั้งค่าผู้ใช้ -> เห็นเอกสารชำระเงินสดทุกบริษัท/ทุกสาขา
    cash_payment_show_all = fields.Boolean(
        string='ดูข้อมูลชำระเงินสดทั้งหมด',
        help='ถ้าติ๊ก ผู้ใช้รายนี้จะเห็นเอกสารชำระเงินสด (cash.payment) ของทุกบริษัทและทุกสาขา '
             'โดยข้ามการกรองตามบริษัท/สาขา',
    )

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ['cash_payment_show_all']
