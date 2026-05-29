from odoo import models, fields, api, _
from odoo.exceptions import AccessError, UserError


class SaleOrderApprovalWizard(models.TransientModel):
    _name = 'sale.order.approval.wizard'
    _description = 'Approval Wizard for Sale Order'

    sale_order_id = fields.Many2one('sale.order', string="Sale Order", required=True)
    approver_id = fields.Many2one('res.users', string="Approver", required=True)
    note_approver = fields.Text(string="Approval Note", required=True, store=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        sale_order_id = self.env.context.get('active_id')
        if sale_order_id:
            sale_order = self.env['sale.order'].browse(sale_order_id)
            res.update({
                'sale_order_id': sale_order.id,
                'approver_id': sale_order.approver_id.id,
                'note_approver': sale_order.note_approver,
            })
        return res

    def action_confirm_approval(self):
        if not self.env.user.has_group('base.group_user'):
            raise AccessError(_("You don't have the necessary permissions to approve this order."))
        self.sale_order_id.write({
            'approver_id': self.approver_id.id,
            'state_sale': 'waiting_to_approve',
            'note_approver': self.note_approver
        })
        return True

    def action_confirm_approve_con(self):
        if not self.sale_order_id:
            raise UserError(_("No Sale Order found to approve."))
        if not self.approver_id:
            raise UserError(_("Please select an approver before confirming the approval."))

        self.sale_order_id.write({
            'approver_id': self.approver_id.id,
            'state_sale': 'approved',
            'note_approver': self.note_approver
        })
        return True
