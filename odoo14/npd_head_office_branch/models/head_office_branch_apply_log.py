# -*- coding: utf-8 -*-

from odoo import _, api, fields, models

from .head_office_branch_common import DOC_TYPE_SELECTION


class NpdHeadOfficeBranchApplyLog(models.Model):
    _name = 'npd.head.office.branch.apply.log'
    _description = 'ประวัติการปรับใช้สาขาสำนักงานใหญ่ย้อนหลัง'
    _order = 'apply_date desc, id desc'
    _rec_name = 'apply_date'

    config_id = fields.Many2one(
        'npd.head.office.branch.config',
        string='การกำหนดค่า',
        ondelete='cascade',
        required=True,
        index=True,
    )
    company_id = fields.Many2one('res.company', string='บริษัท', required=True)
    apply_date = fields.Datetime(
        string='วันที่ปรับใช้', required=True, default=fields.Datetime.now)
    user_id = fields.Many2one(
        'res.users', string='ผู้ปรับใช้', required=True,
        default=lambda self: self.env.user)

    # ---- สำเนาการกำหนดค่า ณ เวลาที่กดปรับใช้ (ไว้ตรวจย้อนหลัง) ----
    head_office_branch_id = fields.Many2one('res.branch', string='สาขาสำนักงานใหญ่')
    fallback_own_branch = fields.Boolean(string='ใช้สาขาของเอกสารเองเมื่อไม่ตรงรายการ')
    bill_branch_names = fields.Char(string='สาขาที่ระบุ (บิลผู้ขาย)')
    advance_clear_branch_names = fields.Char(string='สาขาที่ระบุ (Avance Clear)')
    voucher_branch_names = fields.Char(string='สาขาที่ระบุ (การรับ)')

    scanned_count = fields.Integer(string='เอกสารที่ตรวจ')
    updated_count = fields.Integer(string='เอกสารที่เปลี่ยนค่า')
    line_ids = fields.One2many(
        'npd.head.office.branch.apply.log.line', 'log_id', string='รายการที่เปลี่ยนค่า')

    # Odoo 18 ไม่มี name_get แล้ว
    @api.depends('apply_date', 'updated_count')
    def _compute_display_name(self):
        for log in self:
            label = fields.Datetime.to_string(log.apply_date) or ''
            log.display_name = _('ปรับใช้ %s (เปลี่ยน %s รายการ)') % (label, log.updated_count)


class NpdHeadOfficeBranchApplyLogLine(models.Model):
    _name = 'npd.head.office.branch.apply.log.line'
    _description = 'รายการเอกสารที่ถูกปรับค่าสาขาสำนักงานใหญ่'
    _order = 'log_id desc, doc_type, id'

    log_id = fields.Many2one(
        'npd.head.office.branch.apply.log', string='ประวัติการปรับใช้',
        ondelete='cascade', required=True, index=True)
    doc_type = fields.Selection(DOC_TYPE_SELECTION, string='เมนู', required=True)
    res_model = fields.Char(string='โมเดล', required=True)
    res_id = fields.Integer(string='รหัสเอกสาร', required=True)
    doc_name = fields.Char(string='เอกสาร')
    branch_id = fields.Many2one('res.branch', string='Branch ของเอกสาร')
    old_branch_id = fields.Many2one('res.branch', string='ค่าเดิม')
    new_branch_id = fields.Many2one('res.branch', string='ค่าใหม่')

    def action_open_document(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.res_model,
            'view_mode': 'form',
            'res_id': self.res_id,
            'target': 'current',
        }
