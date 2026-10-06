from odoo import api, fields, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    # เดิม (multi_branch_management_aagam): ช่องอิสระ ค่าเริ่มต้น = สาขาของผู้ใช้
    # เปลี่ยนเป็น compute เก็บค่า + แก้ได้: ค่าเริ่มต้นตามหัวเอกสาร แต่แก้รายบรรทัดได้
    branch_id = fields.Many2one(
        'res.branch', string='Branch',
        compute='_compute_branch_id', store=True, readonly=False, precompute=True)

    @api.depends('move_id.branch_id')
    def _compute_branch_id(self):
        for line in self:
            line.branch_id = line.move_id.branch_id

    @api.model
    def default_get(self, fields_list):
        # ค่าเริ่มต้นเดิม (สาขาของผู้ใช้) ทำให้ระบบถือว่าระบุมาแล้ว ไม่ดึงจากหัวเอกสาร
        res = super().default_get(fields_list)
        res.pop('branch_id', None)
        return res
