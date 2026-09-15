# -*- coding: utf-8 -*-

import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .head_office_branch_common import DOC_TYPES, HO_FIELD, HO_MANUAL_FIELD

_logger = logging.getLogger(__name__)

# ขนาด batch ตอนปรับใช้ย้อนหลัง
APPLY_BATCH_SIZE = 200

# ชื่อสาขาที่ถือว่าเป็นสำนักงานใหญ่ (ใช้เดาค่าเริ่มต้นให้ตอนเปิดหน้ากำหนดค่าครั้งแรก)
HEAD_OFFICE_NAME_HINTS = ['สำนักงานใหญ่', 'สํานักงานใหญ่', 'Head Office']

# Odoo 18 (multi_branch_management_aagam): สาขาหนึ่งผูกได้หลายบริษัทผ่าน company_ids
BRANCH_DOMAIN = "['|', ('company_id', '=', company_id), ('company_ids', 'in', [company_id])]"


def _branch_company_domain(company):
    return ['|', ('company_id', '=', company.id), ('company_ids', 'in', company.ids)]


def _branch_in_company(branch, company):
    return company in (branch.company_id | branch.company_ids)


class NpdHeadOfficeBranchConfig(models.Model):
    _name = 'npd.head.office.branch.config'
    _description = 'กำหนดค่าสาขาที่ให้ออกเอกสารในนามสำนักงานใหญ่'
    _rec_name = 'company_id'

    company_id = fields.Many2one(
        'res.company',
        string='บริษัท',
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    head_office_branch_id = fields.Many2one(
        'res.branch',
        string='สาขาสำนักงานใหญ่',
        domain=BRANCH_DOMAIN,
        help='สาขาที่จะถูกเติมให้อัตโนมัติในฟิลด์ "สาขาสำนักงานใหญ่" ของเอกสาร '
             'เมื่อ Branch ของเอกสารตรงกับสาขาที่ระบุไว้ในเมนูนั้น',
    )
    fallback_own_branch = fields.Boolean(
        string='ถ้าไม่ตรงรายการ ให้ใช้สาขาของเอกสารเอง',
        default=True,
        help='ติ๊กไว้: เอกสารที่เลือกสาขาอื่นซึ่งไม่ได้ระบุไว้ จะแสดงสาขาของเอกสารเองในฟิลด์ใหม่\n'
             'ไม่ติ๊ก: เอกสารที่ไม่ตรงรายการ จะปล่อยฟิลด์ใหม่ว่างไว้',
    )

    bill_branch_ids = fields.Many2many(
        'res.branch',
        'npd_ho_branch_cfg_bill_rel', 'config_id', 'branch_id',
        string='สาขาที่ระบุ (บิลผู้ขาย)',
        domain=BRANCH_DOMAIN,
    )
    advance_clear_branch_ids = fields.Many2many(
        'res.branch',
        'npd_ho_branch_cfg_clear_rel', 'config_id', 'branch_id',
        string='สาขาที่ระบุ (Avance Clear)',
        domain=BRANCH_DOMAIN,
    )
    voucher_branch_ids = fields.Many2many(
        'res.branch',
        'npd_ho_branch_cfg_voucher_rel', 'config_id', 'branch_id',
        string='สาขาที่ระบุ (การรับ)',
        domain=BRANCH_DOMAIN,
    )

    apply_log_ids = fields.One2many(
        'npd.head.office.branch.apply.log', 'config_id',
        string='ประวัติการปรับใช้ย้อนหลัง',
        readonly=True,
    )

    _sql_constraints = [
        ('company_uniq', 'unique(company_id)',
         'มีการกำหนดค่าสาขาสำนักงานใหญ่ของบริษัทนี้อยู่แล้ว'),
    ]

    # ------------------------------------------------------------------
    # ค่าเริ่มต้น / การเข้าถึงการกำหนดค่า
    # ------------------------------------------------------------------
    @api.model
    def _default_head_office_branch_id(self, company):
        Branch = self.env['res.branch'].sudo()
        for hint in HEAD_OFFICE_NAME_HINTS:
            branch = Branch.search(
                _branch_company_domain(company) + [('name', '=', hint)], limit=1)
            if branch:
                return branch
        return Branch.browse()

    @api.model
    def _get_config(self, company):
        """คืนการกำหนดค่าของบริษัทนั้น (อาจเป็น recordset ว่าง)"""
        if not company:
            return self.browse()
        return self.sudo().search([('company_id', '=', company.id)], limit=1)

    @api.model
    def _get_or_create_config(self, company=None):
        company = company or self.env.company
        config = self._get_config(company)
        if not config:
            config = self.sudo().create({
                'company_id': company.id,
                'head_office_branch_id': self._default_head_office_branch_id(company).id,
            })
        return config

    # ------------------------------------------------------------------
    # ตรรกะหลัก: สาขาของเอกสาร -> สาขาที่ควรแสดงในฟิลด์ใหม่
    # ------------------------------------------------------------------
    def _branches_for(self, doc_type):
        self.ensure_one()
        return self[DOC_TYPES[doc_type]['config']]

    def _resolve_branch(self, doc_type, branch):
        """``self`` คือการกำหนดค่า (เป็น recordset ว่างได้ ถ้ายังไม่เคยตั้งค่า)"""
        empty = self.env['res.branch'].browse()
        if self and self.head_office_branch_id and branch \
                and branch in self._branches_for(doc_type):
            return self.head_office_branch_id
        if not self or self.fallback_own_branch:
            return branch or empty
        return empty

    # ------------------------------------------------------------------
    # หน้าจอ
    # ------------------------------------------------------------------
    @api.model
    def action_open_config(self):
        """เปิด popup กำหนดค่าของบริษัทปัจจุบัน"""
        config = self._get_or_create_config(self.env.company)
        form_view = self.env.ref(
            'npd_head_office_branch.view_npd_head_office_branch_config_form')
        return {
            'type': 'ir.actions.act_window',
            'name': _('กำหนดค่าสาขา (สำนักงานใหญ่)'),
            'res_model': self._name,
            'view_mode': 'form',
            'views': [(form_view.id, 'form')],
            'res_id': config.id,
            'target': 'new',
        }

    def action_save_close(self):
        """ปุ่ม บันทึก - ฟอร์มบันทึกให้แล้วก่อนเรียกเมธอด จึงแค่ปิดหน้าต่าง"""
        return {'type': 'ir.actions.act_window_close'}

    def action_apply_history(self):
        """ปุ่ม บันทึก + ปรับใช้ย้อนหลัง"""
        self.ensure_one()
        log = self._apply_to_existing_records()
        return {
            'type': 'ir.actions.act_window',
            'name': _('ผลการปรับใช้ย้อนหลัง'),
            'res_model': log._name,
            'view_mode': 'form',
            'res_id': log.id,
            'target': 'new',
        }

    # ------------------------------------------------------------------
    # ปรับใช้ย้อนหลัง (เคสเก่า)
    # ------------------------------------------------------------------
    def _apply_to_existing_records(self):
        """คำนวณฟิลด์ใหม่ให้เอกสารเดิมทั้งหมด แล้วเก็บประวัติไว้ตรวจย้อนหลัง"""
        self.ensure_one()
        log = self.env['npd.head.office.branch.apply.log'].create({
            'config_id': self.id,
            'company_id': self.company_id.id,
            'head_office_branch_id': self.head_office_branch_id.id,
            'fallback_own_branch': self.fallback_own_branch,
            'bill_branch_names': ', '.join(self.bill_branch_ids.mapped('name')),
            'advance_clear_branch_names': ', '.join(self.advance_clear_branch_ids.mapped('name')),
            'voucher_branch_names': ', '.join(self.voucher_branch_ids.mapped('name')),
        })
        scanned = updated = 0
        for doc_type in DOC_TYPES:
            doc_scanned, doc_updated = self._apply_doc_type(doc_type, log)
            scanned += doc_scanned
            updated += doc_updated
        log.write({'scanned_count': scanned, 'updated_count': updated})
        return log

    def _apply_doc_type(self, doc_type, log):
        self.ensure_one()
        spec = DOC_TYPES[doc_type]
        Model = self.env[spec['model']].sudo().with_context(active_test=False)
        field = Model._fields.get(HO_FIELD)
        if field is None:
            # โมดูลของเมนูนั้นไม่ได้ติดตั้งไว้ ก็ข้ามไป
            return 0, 0

        domain = list(spec['domain'])
        if 'company_id' in Model._fields:
            domain = [('company_id', '=', self.company_id.id)] + domain
        if HO_MANUAL_FIELD in Model._fields:
            # ใบที่ผู้ใช้แก้สาขาสำนักงานใหญ่เอง ห้ามคำนวณทับ
            domain = [(HO_MANUAL_FIELD, '=', False)] + domain
        records = Model.search(domain)

        scanned = len(records)
        updated = 0
        for index in range(0, scanned, APPLY_BATCH_SIZE):
            batch = records[index:index + APPLY_BATCH_SIZE]
            before = {record.id: record[HO_FIELD].id for record in batch}

            self.env.add_to_compute(field, batch)
            batch._recompute_recordset([HO_FIELD])
            batch.flush_recordset([HO_FIELD])

            lines = []
            for record in batch:
                new_branch = record[HO_FIELD]
                if new_branch.id == before[record.id]:
                    continue
                updated += 1
                lines.append((0, 0, {
                    'doc_type': doc_type,
                    'res_model': spec['model'],
                    'res_id': record.id,
                    'doc_name': record.display_name,
                    'branch_id': record.branch_id.id,
                    'old_branch_id': before[record.id],
                    'new_branch_id': new_branch.id,
                }))
            if lines:
                log.write({'line_ids': lines})
        _logger.info(
            'npd_head_office_branch: apply history on %s -> scanned %s, updated %s',
            spec['model'], scanned, updated)
        return scanned, updated

    # ------------------------------------------------------------------
    @api.constrains('company_id', 'head_office_branch_id', 'bill_branch_ids',
                    'advance_clear_branch_ids', 'voucher_branch_ids')
    def _check_branch_company(self):
        for config in self:
            branches = config.head_office_branch_id | config.bill_branch_ids \
                | config.advance_clear_branch_ids | config.voucher_branch_ids
            wrong = branches.filtered(lambda b: not _branch_in_company(b, config.company_id))
            if wrong:
                raise ValidationError(
                    _('สาขาต่อไปนี้ไม่ได้อยู่ในบริษัท %s: %s')
                    % (config.company_id.name, ', '.join(wrong.mapped('name'))))
