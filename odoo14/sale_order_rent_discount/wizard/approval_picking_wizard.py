from odoo import models, fields, api


class ApprovalPickingWizard(models.TransientModel):
    _name = 'stock.picking.approval.wizard'
    _description = 'Approval Picking Wizard'

    picking_id = fields.Many2one('stock.picking', required=True)
    request_note = fields.Text(string="หมายเหตุการขอ", readonly=True)
    rent_discount = fields.Float(string="ส่วนลดค่าเช่า", readonly=True)
    action = fields.Selection([
        ('approve', 'อนุมัติ'),
        ('reject', 'แก้ไข'),
    ], string="การดำเนินการ", required=True, default='approve')
    approval_note = fields.Text(string="หมายเหตุจากผู้อนุมัติ", required=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        picking_id = self.env.context.get('active_id')
        if picking_id:
            picking = self.env['stock.picking'].browse(picking_id)
            res['picking_id'] = picking.id
            res['request_note'] = picking.request_note
            res['rent_discount'] = picking.rent_discount
        return res

    def action_process(self):
        if self.action == 'approve':
            self.picking_id.write({
                'approval_state': 'approved',
                'approval_note': self.approval_note,
            })
        else:
            self.picking_id.write({
                'approval_state': 'revise',
                'approval_note': self.approval_note,
            })
        return {'type': 'ir.actions.act_window_close'}
