from odoo import models, fields, api


class RentDiscountWizard(models.TransientModel):
    _name = 'rent.discount.wizard'
    _description = 'Rent Discount Wizard'

    discount_amount = fields.Float(string="จำนวนส่วนลด", required=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        picking_id = self.env.context.get('active_id')
        if picking_id:
            picking = self.env['stock.picking'].browse(picking_id)
            res['discount_amount'] = picking.rent_discount or 0.0
        return res

    def action_confirm_discount(self):
        picking_id = self.env.context.get('active_id')
        if picking_id:
            picking = self.env['stock.picking'].browse(picking_id)
            picking.write({'rent_discount': self.discount_amount})
        return {'type': 'ir.actions.act_window_close'}


class RequestPickingApprovalWizard(models.TransientModel):
    _name = 'stock.picking.request.approval.wizard'
    _description = 'Request Picking Approval Wizard'

    picking_id = fields.Many2one('stock.picking', required=True)
    approver_id = fields.Many2one('res.users', string="ผู้อนุมัติ",
                                   domain=[('active', '=', True)], required=True)
    request_note = fields.Text(string="หมายเหตุ", required=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        picking_id = self.env.context.get('active_id')
        if picking_id:
            picking = self.env['stock.picking'].browse(picking_id)
            res['picking_id'] = picking.id
            if picking.approval_state == 'revise' and picking.approver_id:
                res['approver_id'] = picking.approver_id.id
            if picking.request_note:
                res['request_note'] = picking.request_note
        return res

    def action_send_approval(self):
        self.picking_id.write({
            'approval_state': 'waiting',
            'approver_id': self.approver_id.id,
            'request_note': self.request_note,
        })
        return {'type': 'ir.actions.act_window_close'}
