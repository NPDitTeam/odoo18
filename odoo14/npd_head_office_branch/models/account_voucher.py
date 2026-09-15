# -*- coding: utf-8 -*-

from odoo import api, fields, models

from .head_office_branch_common import compute_head_office_branch


class AccountVoucher(models.Model):
    """เมนู การรับ - ใช้เฉพาะเอกสารที่ check_type_show_selection = False"""

    _name = 'account.voucher'
    _inherit = ['account.voucher', 'npd.head.office.branch.edit.mixin']

    _head_office_doc_type = 'voucher'

    # readonly=False: ผู้ใช้ที่ได้รับสิทธิ์แก้ทับค่าที่ระบบเติมให้ได้
    head_office_branch_id = fields.Many2one(
        'res.branch',
        string='สาขาสำนักงานใหญ่',
        compute='_compute_head_office_branch_id',
        store=True,
        readonly=False,
        copy=False,
        help='เติมอัตโนมัติจากเมนู การกำหนดค่า > กำหนดค่าสาขา (สำนักงานใหญ่)\n'
             'ใช้เฉพาะเอกสารในเมนู การรับ (check_type_show_selection = False)\n'
             'ผู้ใช้ที่ติ๊ก "แก้ไขสาขาสำนักงานใหญ่เองได้" ในหน้าตั้งค่าผู้ใช้ แก้ไขเองได้',
    )

    @api.depends('branch_id', 'company_id', 'check_type_show_selection')
    def _compute_head_office_branch_id(self):
        compute_head_office_branch(self, 'voucher')
