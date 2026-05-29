from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.model
    def search(self, args, offset=0, limit=None, order=None):
        user = self.env.user
        user_branch = getattr(user, 'branch_id', False)

        # ตรวจสอบว่าพนักงานอยู่แผนก Sales หรือไม่
        employee = self.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
        is_sales_department = employee and employee.department_id and employee.department_id.name == 'Sales'

        if is_sales_department:
            sales_domain = [('sales_contact_id', '=', user.id)]
            args = sales_domain + (args or [])
        elif not user.bypass_branch_filter and user_branch:
            branch_domain = ['|', ('branch_id', '=', False), ('branch_id', '=', user_branch.id)]
            args = branch_domain + (args or [])

        return super().search(args, offset=offset, limit=limit, order=order)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    @api.model
    def search(self, args, offset=0, limit=None, order=None):
        user = self.env.user
        user_branch = getattr(user, 'branch_id', False)

        employee = self.env['hr.employee'].sudo().search([('user_id', '=', user.id)], limit=1)
        is_sales_department = employee and employee.department_id and employee.department_id.name == 'Sales'

        if is_sales_department:
            my_invoice_ids = self.env['account.move'].sudo().search([
                ('sales_contact_id', '=', user.id)
            ]).ids
            if 'account.payment.invoice' in self.env:
                my_payment_ids = self.env['account.payment.invoice'].sudo().search([
                    ('invoice_id', 'in', my_invoice_ids)
                ]).mapped('payment_id').ids
            else:
                my_payment_ids = []
            sales_domain = [('id', 'in', my_payment_ids)]
            args = sales_domain + (args or [])
        elif not user.bypass_branch_filter_payment and user_branch:
            branch_domain = ['|', ('branch_id', '=', False), ('branch_id', '=', user_branch.id)]
            args = branch_domain + (args or [])

        return super().search(args, offset=offset, limit=limit, order=order)
