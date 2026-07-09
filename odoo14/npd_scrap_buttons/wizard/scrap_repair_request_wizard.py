# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ScrapRepairRequestWizard(models.TransientModel):
    _name = 'npd.scrap.repair.request.wizard'
    _description = 'Scrap Repair Request Wizard'

    scrap_id = fields.Many2one('stock.scrap', string='Scrap Order', required=True, readonly=True)
    damage_type = fields.Char(string='ประเภทความเสียหาย', required=True)
    repair_by = fields.Selection(
        [('factory', 'โรงงาน'), ('branch', 'สาขา')],
        string='ซ่อมโดย',
        required=True,
    )
    technician_name = fields.Char(string='ชื่อผู้ซ่อม', required=True)
    damaged_attachment_ids = fields.Many2many(
        'ir.attachment',
        'rel_wizard_repair_request_attachment',
        'wizard_id',
        'attachment_id',
        string='แนบรูปสินค้าที่ชำรุด',
    )

    def action_save(self):
        self.ensure_one()
        if self.scrap_id.state != 'pending_repair':
            raise UserError(_('เอกสารไม่ได้อยู่ในสถานะ "รอดำเนินการแจ้งซ่อม"'))
        self.scrap_id.write({
            'damage_type': self.damage_type,
            'repair_by': self.repair_by,
            'technician_name': self.technician_name,
            'damaged_attachment_ids': [(6, 0, self.damaged_attachment_ids.ids)],
            'repair_start_date': fields.Datetime.now(),
            'state': 'under_repair',
        })
        return {'type': 'ir.actions.act_window_close'}
