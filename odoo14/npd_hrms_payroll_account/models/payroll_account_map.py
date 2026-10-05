# -*- coding: utf-8 -*-
"""แถวผังบัญชีเงินเดือน: ชื่อบรรทัดในสลิป (หรือฟิลด์ย่อยที่แยกจากบรรทัดรวม) -> บัญชี

แถวที่ระบุแผนกชนะแถวทั้งบริษัท เช่น เงินเดือนแผนกขนส่งเป็นต้นทุนขาย
ส่วนแผนกอื่นเป็นค่าใช้จ่ายบริหาร
"""
from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .constants import (
    EMPLOYER_SSO_LINE, EXPENSE_TYPES, LINE_TYPE_SELECTION, SPLIT_KEY_PARENT,
)


class NpdPayrollAccountMap(models.Model):
    _name = 'npd.payroll.account.map'
    _description = 'ผังบัญชีเงินเดือน'
    _order = 'sequence, line_type, line_name, id'
    _check_company_auto = True

    config_id = fields.Many2one(
        'npd.payroll.account.config', string='การตั้งค่า', required=True,
        ondelete='cascade', index=True)
    # precompute: ให้บริษัทลงไปพร้อม INSERT เลย unique index จะได้เห็นค่าจริงทันที
    company_id = fields.Many2one(
        related='config_id.company_id', store=True, index=True, precompute=True,
        string='บริษัท')
    sequence = fields.Integer(string='ลำดับ', default=10)
    line_type = fields.Selection(
        LINE_TYPE_SELECTION, string='ประเภท', required=True)
    line_name = fields.Char(
        string='ชื่อรายการในสลิป', required=True,
        help='พิมพ์ให้ตรงกับชื่อบรรทัดในสลิปทุกตัวอักษร เช่น "เงินเดือน" หรือ '
             '"ภาษีหัก ณ ที่จ่าย" หรือชื่อฟิลด์ย่อยที่แยกจากบรรทัดรวม เช่น '
             '"income_deposit_refund_total" (คืนเงินประกันการทำงาน) '
             'ประเภทนายจ้างสมทบใช้ได้เฉพาะ "ประกันสังคม"')
    line_label = fields.Char(
        string='ความหมาย', compute='_compute_line_label')
    account_id = fields.Many2one(
        'account.account', string='บัญชี', check_company=True,
        domain=[('deprecated', '=', False)])
    reduce_expense = fields.Boolean(
        string='หักลดค่าใช้จ่ายเงินเดือน',
        help='ใช้กับรายการหักสาย/ลา/ขาด/พักงาน ซึ่งเป็นเงินเดือนที่ไม่ได้จ่ายจริง '
             'ถ้าไม่เลือกบัญชี ระบบจะเครดิตเข้าบัญชีเดียวกับบรรทัด "เงินเดือน" '
             'ของแผนกนั้นให้เอง')
    department_id = fields.Many2one(
        'hr.department.custom', string='เฉพาะแผนก',
        help='ว่าง = ใช้ทั้งบริษัท ถ้ามีแถวของแผนกจะใช้แถวของแผนกก่อน')
    note = fields.Char(string='หมายเหตุ')

    def init(self):
        # กันแถวซ้ำระดับฐานข้อมูล (department ว่างถือเป็นค่าเดียวกัน)
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS npd_payroll_account_map_uniq
            ON npd_payroll_account_map
               (company_id, line_type, line_name, COALESCE(department_id, 0))
        """)

    @api.depends('line_type', 'line_name')
    def _compute_line_label(self):
        Salary = self.env['payroll.salary']
        for rec in self:
            key = (rec.line_name or '').strip()
            parent = SPLIT_KEY_PARENT.get(key)
            if parent and key in Salary._fields:
                rec.line_label = '%s (แยกจาก %s)' % (Salary._fields[key].string, parent[1])
            elif rec.line_type == 'employer':
                rec.line_label = '%s (ส่วนนายจ้าง)' % key
            else:
                rec.line_label = key

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('line_name'):
                vals['line_name'] = vals['line_name'].strip()
        self._npd_assert_unique([
            (vals.get('config_id'), vals.get('line_type'), vals.get('line_name'),
             vals.get('department_id')) for vals in vals_list], exclude_ids=[])
        return super().create(vals_list)

    def write(self, vals):
        # ตัดช่องว่างหัวท้ายเสมอ ไม่งั้นแถวที่ดูเหมือนกันจะหลุดการกันซ้ำและจับคู่ไม่เจอ
        if vals.get('line_name'):
            vals = dict(vals, line_name=vals['line_name'].strip())
        if {'config_id', 'line_type', 'line_name', 'department_id'} & set(vals):
            self._npd_assert_unique([
                (vals.get('config_id', rec.config_id.id),
                 vals.get('line_type', rec.line_type),
                 vals.get('line_name', rec.line_name),
                 vals.get('department_id', rec.department_id.id)) for rec in self],
                exclude_ids=self.ids)
        return super().write(vals)

    def _npd_assert_unique(self, keys, exclude_ids):
        """ตรวจแถวซ้ำก่อนถึง unique index

        ถ้าปล่อยให้ index จับ ผู้ใช้จะเห็นข้อความ SQL ภาษาอังกฤษ ไม่รู้ว่าซ้ำแถวไหน
        เทียบด้วย config_id (1 บริษัทมี 1 การตั้งค่า) เพราะ company_id เป็นฟิลด์ related
        """
        seen = set()
        Map = self.sudo().with_context(active_test=False)
        for config_id, line_type, line_name, department_id in keys:
            if not (config_id and line_type and line_name):
                continue
            key = (config_id, line_type, line_name.strip(), department_id or False)
            if key in seen or Map.search_count([
                    ('id', 'not in', exclude_ids),
                    ('config_id', '=', config_id),
                    ('line_type', '=', line_type),
                    ('line_name', '=', key[2]),
                    ('department_id', '=', key[3])]):
                department = self.env['hr.department.custom'].sudo().browse(key[3])
                raise ValidationError(
                    'มีแถวผังบัญชีเงินเดือน "%s" %s อยู่แล้ว แก้แถวเดิมแทนการเพิ่มใหม่' % (
                        key[2], ('แผนก %s' % department.name) if key[3] else '(ทั้งบริษัท)'))
            seen.add(key)

    @api.constrains('line_type', 'line_name', 'reduce_expense', 'account_id',
                    'department_id', 'company_id')
    def _check_row(self):
        for rec in self:
            key = (rec.line_name or '').strip()
            if rec.reduce_expense and rec.line_type != 'deduction':
                raise ValidationError(
                    '"หักลดค่าใช้จ่ายเงินเดือน" ใช้ได้กับรายการหักเท่านั้น (%s)' % key)
            if rec.reduce_expense and rec.account_id \
                    and rec.account_id.account_type not in EXPENSE_TYPES:
                raise ValidationError(
                    'รายการ "%s" ตั้งให้หักลดค่าใช้จ่ายเงินเดือน '
                    'บัญชีที่เลือกต้องเป็นบัญชีค่าใช้จ่าย' % key)
            if rec.line_type == 'employer' and key != EMPLOYER_SSO_LINE:
                raise ValidationError(
                    'ประเภทนายจ้างสมทบใช้ได้เฉพาะรายการ "%s"' % EMPLOYER_SSO_LINE)
            parent = SPLIT_KEY_PARENT.get(key)
            if parent and parent[0] != rec.line_type:
                raise ValidationError(
                    'รายการ "%s" แยกมาจากบรรทัด%s "%s" ต้องเลือกประเภทให้ตรงกัน' % (
                        key, 'รายได้' if parent[0] == 'income' else 'รายการหัก',
                        parent[1]))
            duplicate = self.sudo().search_count([
                ('id', '!=', rec.id),
                ('company_id', '=', rec.company_id.id),
                ('line_type', '=', rec.line_type),
                ('line_name', '=', key),
                ('department_id', '=', rec.department_id.id or False),
            ])
            if duplicate:
                raise ValidationError(
                    'มีแถวผังบัญชีเงินเดือน "%s" %s ของบริษัทนี้อยู่แล้ว' % (
                        key, ('แผนก %s' % rec.department_id.name)
                        if rec.department_id else '(ทั้งบริษัท)'))
