# -*- coding: utf-8 -*-
from odoo import models, fields, _
from odoo.exceptions import UserError


class ScrapRepairCompleteWizard(models.TransientModel):
    _name = 'npd.scrap.repair.complete.wizard'
    _description = 'Scrap Repair Complete Wizard'

    scrap_id = fields.Many2one('stock.scrap', string='Scrap Order', required=True, readonly=True)
    spare_parts_used = fields.Text(string='อะไหล่ที่ใช้ในการซ่อม', required=True)
    parts_cost = fields.Float(string='ค่าอะไหล่')
    labor_cost = fields.Float(string='ค่าแรง')
    repaired_attachment_ids = fields.Many2many(
        'ir.attachment',
        'rel_wizard_repair_complete_attachment',
        'wizard_id',
        'attachment_id',
        string='แนบรูปภาพสินค้าหลังซ่อมเสร็จ',
    )

    def action_save(self):
        self.ensure_one()
        scrap = self.scrap_id
        if scrap.state != 'under_repair':
            raise UserError(_('เอกสารไม่ได้อยู่ในสถานะ "อยู่ระหว่างการซ่อม"'))

        # Reverse stock move คืนสินค้าจาก scrap location กลับไปยัง location ตั้งต้น
        # Odoo 18: stock.scrap ใช้ move_ids (One2many) แทน move_id
        return_move = False
        if scrap.move_ids:
            return_move = scrap._create_reverse_move(_('Repaired'))

        now = fields.Datetime.now()
        scrap.write({
            'spare_parts_used': self.spare_parts_used,
            'parts_cost': self.parts_cost,
            'labor_cost': self.labor_cost,
            'repaired_attachment_ids': [(6, 0, self.repaired_attachment_ids.ids)],
            'repair_end_date': now,
            'state': 'repaired',
            'is_stock_returned': bool(return_move),
            'return_move_id': return_move.id if return_move else False,
            'return_date': now if return_move else False,
        })
        return {'type': 'ir.actions.act_window_close'}
