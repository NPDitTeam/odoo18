# -*- coding: utf-8 -*-


from itertools import groupby

from odoo import api, fields, models, SUPERUSER_ID, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_is_zero, float_compare


class SaleOrder(models.Model):
    _inherit = "sale.order"

    branch_id = fields.Many2one('res.branch', string='Branch Name', help='The default branch for this user.',
                                context={'user_preference': True}, default=lambda self: self.env.user.branch_id.id)

    def _create_invoices(self, grouped=False, final=False, date=None):
        """เรียก _create_invoices ของ Odoo 18 ตามปกติ แล้วค่อย stamp branch_id
        ลง invoice + บรรทัด ตาม branch ของ sale order ต้นทางของแต่ละ move

        เดิมโมดูลนี้ copy โค้ดทั้งเมธอดมาจาก Odoo รุ่นเก่า ทำให้:
          - ขาด keyword `date` (sale_invoice_plan ส่งเข้ามา) → TypeError ตอนสร้างใบแจ้งหนี้
          - ใช้ API ที่ถูกตัดใน O18 (check_access_rights ฯลฯ)
        การเรียก super() แทน ทำให้ตามรุ่น O18 ได้เสมอ และยังคงหน้าที่ตั้ง branch ไว้
        """
        moves = super()._create_invoices(grouped=grouped, final=final, date=date)
        for move in moves:
            branch = move.line_ids.sale_line_ids.order_id.branch_id[:1]
            if branch:
                move.sudo().write({'branch_id': branch.id})
                move.line_ids.sudo().write({'branch_id': branch.id})
        return moves


class SaleOrderLine(models.Model):
    """inherited purchase order line"""
    _inherit = 'sale.order.line'

    branch_id = fields.Many2one(related='order_id.branch_id',
                                string='Branch', store=True)


from odoo import fields, models


class SaleReport(models.Model):
    _inherit = "sale.report"

    branch_id = fields.Many2one('res.branch', readonly=True)

    def _select_additional_fields(self):
        res = super()._select_additional_fields()
        res['branch_id'] = "s.branch_id"
        return res

    def _group_by_sale(self):
        res = super()._group_by_sale()
        res += """,
            s.branch_id"""
        return res
