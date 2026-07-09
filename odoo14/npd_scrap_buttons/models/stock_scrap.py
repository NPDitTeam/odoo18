# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class StockScrap(models.Model):
    _inherit = 'stock.scrap'

    # =======================
    # STATES
    # =======================
    state = fields.Selection(
        selection_add=[
            ('cancel', 'Cancelled'),
            ('pending_repair', 'รอดำเนินการแจ้งซ่อม'),
            ('under_repair', 'อยู่ระหว่างการซ่อม'),
            ('repaired', 'ซ่อมสำเร็จ'),
        ],
        ondelete={
            'cancel': 'set default',
            'pending_repair': 'set default',
            'under_repair': 'set default',
            'repaired': 'set default',
        }
    )

    original_name = fields.Char(
        string='Original Reference',
        copy=False,
        readonly=True,
        help='เก็บเลขเอกสารเดิมไว้ เมื่อรีเซ็ตเป็นแบบร่างจะใช้เลขเดิม'
    )

    # ===== Repair Request fields (จากปุ่มแจ้งซ่อม) =====
    damage_type = fields.Char(string='ประเภทความเสียหาย', readonly=True, copy=False)
    repair_by = fields.Selection(
        [('factory', 'โรงงาน'), ('branch', 'สาขา')],
        string='ซ่อมโดย',
        readonly=True,
        copy=False,
    )
    technician_name = fields.Char(string='ชื่อผู้ซ่อม', readonly=True, copy=False)
    repair_start_date = fields.Datetime(string='วันที่เริ่มซ่อม', readonly=True, copy=False)
    damaged_attachment_ids = fields.Many2many(
        'ir.attachment',
        'rel_scrap_damaged_attachment',
        'scrap_id',
        'attachment_id',
        string='รูปสินค้าที่ชำรุด',
        copy=False,
    )

    # ===== Repair Complete fields (จากปุ่มซ่อมสำเร็จ) =====
    spare_parts_used = fields.Text(string='อะไหล่ที่ใช้ในการซ่อม', readonly=True, copy=False)
    parts_cost = fields.Float(string='ค่าอะไหล่', readonly=True, copy=False)
    labor_cost = fields.Float(string='ค่าแรง', readonly=True, copy=False)
    repair_end_date = fields.Datetime(string='วันที่ซ่อมเสร็จสิ้น', readonly=True, copy=False)
    repaired_attachment_ids = fields.Many2many(
        'ir.attachment',
        'rel_scrap_repaired_attachment',
        'scrap_id',
        'attachment_id',
        string='รูปภาพหลังซ่อม',
        copy=False,
    )

    # ===== Stock return tracking =====
    is_stock_returned = fields.Boolean(string='คืนสต็อกแล้ว', readonly=True, copy=False)
    return_move_id = fields.Many2one(
        'stock.move',
        string='การคืนสต็อก',
        readonly=True,
        copy=False,
    )
    return_date = fields.Datetime(string='วันที่คืนสต็อก', readonly=True, copy=False)

    # ===== Computed: ระยะเวลาในการซ่อม =====
    repair_duration_display = fields.Char(
        string='ระยะเวลาในการซ่อมสินค้า',
        compute='_compute_repair_duration_display',
        store=False,
    )

    @api.depends('repair_start_date', 'repair_end_date')
    def _compute_repair_duration_display(self):
        for rec in self:
            start = rec.repair_start_date
            end = rec.repair_end_date
            if not start or not end:
                rec.repair_duration_display = ''
                continue
            delta = end - start
            total_seconds = int(delta.total_seconds())
            if total_seconds <= 0:
                rec.repair_duration_display = '0 นาที'
                continue
            days = total_seconds // 86400
            hours = (total_seconds % 86400) // 3600
            minutes = (total_seconds % 3600) // 60
            parts = []
            if days:
                parts.append('%d วัน' % days)
            if hours:
                parts.append('%d ชั่วโมง' % hours)
            if minutes and not days:
                parts.append('%d นาที' % minutes)
            if not parts:
                parts.append('น้อยกว่า 1 นาที')
            rec.repair_duration_display = ' '.join(parts)

    # =======================
    # OVERRIDE METHODS
    # =======================
    def do_scrap(self):
        """
        Override do_scrap (Odoo 18):
        - ใช้เลขเอกสารเดิมถ้ามี original_name (ไม่รัน sequence ใหม่)
        - ถ้า reason_code มี is_damage_repair=True → state=pending_repair
          มิฉะนั้น state=done (พฤติกรรมเดิม) และเติมสต๊อกคืนถ้า should_replenish
        หมายเหตุ Odoo 18: stock.scrap ใช้ move_ids (One2many) — move ถูกผูกกับ scrap
        อัตโนมัติผ่าน scrap_id ใน _prepare_move_values จึงไม่ต้องเขียน move_id เอง
        """
        self._check_company()
        for scrap in self:
            if scrap.original_name:
                scrap.name = scrap.original_name
            else:
                scrap.name = self.env['ir.sequence'].next_by_code('stock.scrap') or _('New')

            move = self.env['stock.move'].create(scrap._prepare_move_values())
            move.with_context(is_scrap=True)._action_done()

            new_state = 'done'
            if scrap.reason_code_id and scrap.reason_code_id.is_damage_repair:
                new_state = 'pending_repair'

            scrap.write({
                'state': new_state,
                'original_name': scrap.name,
            })
            scrap.date_done = fields.Datetime.now()

            # เติมสต๊อกคืน (Odoo 18) เฉพาะกรณีปิดจบเป็น done ตามพฤติกรรม core
            if new_state == 'done' and scrap.should_replenish:
                scrap.do_replenish()
        return True

    # =======================
    # INTERNAL HELPERS
    # =======================
    def _create_reverse_move(self, prefix):
        """สร้าง reverse stock move คืนสินค้าจาก scrap_location → location_id เดิม
        Odoo 18: move.line ใช้ 'quantity' (ไม่ใช่ qty_done) + ตั้ง picked=True เพื่อให้ _action_done ปิดงานได้"""
        self.ensure_one()
        reverse_move_vals = {
            'name': _('%s: %s') % (prefix, self.name),
            'origin': self.name,
            'company_id': self.company_id.id,
            'product_id': self.product_id.id,
            'product_uom': self.product_uom_id.id,
            'state': 'draft',
            'product_uom_qty': self.scrap_qty,
            'location_id': self.scrap_location_id.id,
            'location_dest_id': self.location_id.id,
            'picked': True,
            'move_line_ids': [(0, 0, {
                'product_id': self.product_id.id,
                'product_uom_id': self.product_uom_id.id,
                'quantity': self.scrap_qty,
                'location_id': self.scrap_location_id.id,
                'location_dest_id': self.location_id.id,
                'package_id': self.package_id.id if self.package_id else False,
                'owner_id': self.owner_id.id if self.owner_id else False,
                'lot_id': self.lot_id.id if self.lot_id else False,
            })],
        }
        reverse_move = self.env['stock.move'].create(reverse_move_vals)
        reverse_move._action_done()
        return reverse_move

    # =======================
    # BUTTON METHODS - reset / cancel
    # =======================
    def action_reset_to_draft(self):
        states_with_move = ('done', 'pending_repair', 'under_repair')
        repair_states = ('pending_repair', 'under_repair', 'repaired')
        for record in self:
            if record.state in states_with_move and record.move_ids:
                record._create_reverse_move(_('Reverse'))

            vals = {
                'state': 'draft',
                'date_done': False,
                'original_name': record.name,
            }
            # ล้างข้อมูลการซ่อมเดิมเมื่อรีเซ็ตจากสถานะใน repair workflow
            if record.state in repair_states:
                vals.update({
                    'damage_type': False,
                    'repair_by': False,
                    'technician_name': False,
                    'repair_start_date': False,
                    'damaged_attachment_ids': [(5, 0, 0)],
                    'spare_parts_used': False,
                    'parts_cost': 0.0,
                    'labor_cost': 0.0,
                    'repair_end_date': False,
                    'repaired_attachment_ids': [(5, 0, 0)],
                    'is_stock_returned': False,
                    'return_move_id': False,
                    'return_date': False,
                })
            record.write(vals)
        return True

    def action_cancel(self):
        states_with_move = ('done', 'pending_repair', 'under_repair')
        for record in self:
            if record.state in states_with_move and record.move_ids:
                record._create_reverse_move(_('Cancel'))
            record.write({'state': 'cancel'})
        return True

    # =======================
    # BUTTON METHODS - repair workflow
    # =======================
    def action_open_repair_request_wizard(self):
        self.ensure_one()
        if self.state != 'pending_repair':
            raise UserError(_('สามารถแจ้งซ่อมได้เฉพาะเอกสารสถานะ "รอดำเนินการแจ้งซ่อม" เท่านั้น'))
        return {
            'name': _('แจ้งซ่อม'),
            'type': 'ir.actions.act_window',
            'res_model': 'npd.scrap.repair.request.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_scrap_id': self.id},
        }

    def action_open_repair_complete_wizard(self):
        self.ensure_one()
        if self.state != 'under_repair':
            raise UserError(_('สามารถบันทึกซ่อมสำเร็จได้เฉพาะเอกสารสถานะ "อยู่ระหว่างการซ่อม" เท่านั้น'))
        return {
            'name': _('ซ่อมสำเร็จ'),
            'type': 'ir.actions.act_window',
            'res_model': 'npd.scrap.repair.complete.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_scrap_id': self.id},
        }
