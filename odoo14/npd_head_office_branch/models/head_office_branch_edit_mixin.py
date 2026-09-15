# -*- coding: utf-8 -*-

from odoo import api, fields, models

from .head_office_branch_common import HO_FIELD, HO_MANUAL_FIELD, resolve_head_office_branches


class HeadOfficeBranchEditMixin(models.AbstractModel):
    """ให้ผู้ใช้ที่ติ๊กสิทธิ์ในหน้าตั้งค่าผู้ใช้ แก้ฟิลด์ สาขาสำนักงานใหญ่ เองได้

    โมเดลที่ใช้ต้องกำหนด ``_head_office_doc_type`` (key ใน DOC_TYPES)
    และประกาศ HO_FIELD เป็น compute + store=True + readonly=False เอง
    """

    _name = 'npd.head.office.branch.edit.mixin'
    _description = 'สิทธิ์แก้ไขสาขาสำนักงานใหญ่เอง'

    _head_office_doc_type = None

    head_office_branch_manual = fields.Boolean(
        string='สาขาสำนักงานใหญ่ถูกแก้ไขเอง',
        readonly=True,
        copy=False,
        help='ติ๊กเองอัตโนมัติเมื่อผู้ใช้เลือกสาขาสำนักงานใหญ่ต่างจากค่าที่ระบบเติมให้\n'
             'เอกสารที่ติ๊กไว้ จะไม่ถูกปุ่ม "ปรับใช้ย้อนหลัง" คำนวณทับ',
    )
    can_edit_head_office_branch = fields.Boolean(
        compute='_compute_can_edit_head_office_branch',
    )

    @api.depends_context('uid')
    def _compute_can_edit_head_office_branch(self):
        allowed = self._can_edit_head_office_branch()
        for record in self:
            record.can_edit_head_office_branch = allowed

    @api.model
    def _can_edit_head_office_branch(self):
        # ไม่ยกเว้น superuser: โค้ดที่สร้างเอกสารผ่าน SUPERUSER_ID
        # ต้องได้ค่าอัตโนมัติเหมือนเดิม
        return self.env.user.allow_edit_head_office_branch

    def _sync_head_office_branch_manual(self):
        """ติ๊ก/เอาติ๊กออก ตามว่าค่าในใบต่างจากค่าที่ระบบเติมให้หรือไม่"""
        to_set = {True: [], False: []}
        for record, auto in resolve_head_office_branches(self, self._head_office_doc_type):
            manual = record[HO_FIELD] != auto
            if record[HO_MANUAL_FIELD] != manual:
                to_set[manual].append(record.id)
        for manual, ids in to_set.items():
            if ids:
                self.browse(ids).write({HO_MANUAL_FIELD: manual})

    @api.model_create_multi
    def create(self, vals_list):
        if not self._can_edit_head_office_branch():
            # ฟอร์มส่งค่ามาเสมอ (force_save) ตัดทิ้งให้ระบบคำนวณเอง
            vals_list = [
                {key: val for key, val in vals.items() if key != HO_FIELD}
                for vals in vals_list
            ]
        records = super().create(vals_list)
        # ใบที่ไม่ได้ส่งค่ามา ระบบคำนวณให้เอง ไม่ต้องตรวจ
        self.browse([
            record.id for record, vals in zip(records, vals_list) if HO_FIELD in vals
        ])._sync_head_office_branch_manual()
        return records

    def write(self, vals):
        if HO_FIELD in vals and not self._can_edit_head_office_branch():
            vals = {key: val for key, val in vals.items() if key != HO_FIELD}
        # ใบที่ต้องตรวจหลังบันทึก: ใบที่ค่าเปลี่ยน + ใบที่เคยแก้เอง
        # (ใบที่เคยแก้เองอาจถูกคำนวณใหม่เพราะเปลี่ยน Branch แล้วได้ค่าเดิมพอดี)
        watched = self if HO_FIELD in vals else self.filtered(HO_MANUAL_FIELD)
        before = {record.id: record[HO_FIELD] for record in watched}
        result = super().write(vals)
        watched.filtered(
            lambda record: record[HO_MANUAL_FIELD] or record[HO_FIELD] != before[record.id]
        )._sync_head_office_branch_manual()
        return result
