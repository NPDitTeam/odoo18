# -*- coding: utf-8 -*-

from odoo import api, fields, models

from .head_office_branch_common import compute_head_office_branch


class AccountAdvanceClear(models.Model):
    """เมนู Avance Clear"""

    _name = 'account.advance.clear'
    _inherit = ['account.advance.clear', 'npd.head.office.branch.edit.mixin']

    _head_office_doc_type = 'advance_clear'

    # readonly=False: ผู้ใช้ที่ได้รับสิทธิ์แก้ทับค่าที่ระบบเติมให้ได้
    # (ค่าจะคำนวณใหม่เองเมื่อเปลี่ยน Branch / บริษัท)
    head_office_branch_id = fields.Many2one(
        'res.branch',
        string='สาขาสำนักงานใหญ่',
        compute='_compute_head_office_branch_id',
        store=True,
        readonly=False,
        copy=False,
        help='เติมอัตโนมัติจากเมนู การกำหนดค่า > กำหนดค่าสาขา (สำนักงานใหญ่)\n'
             'ผู้ใช้ที่ติ๊ก "แก้ไขสาขาสำนักงานใหญ่เองได้" ในหน้าตั้งค่าผู้ใช้ แก้ไขเองได้',
    )

    @api.depends('branch_id', 'company_id')
    def _compute_head_office_branch_id(self):
        compute_head_office_branch(self, 'advance_clear')
