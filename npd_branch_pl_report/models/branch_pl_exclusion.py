# -*- coding: utf-8 -*-
"""ตั้งค่าบัญชีที่ไม่ให้แสดงในงบรายรับ-รายจ่ายรายสาขา

บางบัญชีที่โผล่ในงบของบางสาขาไม่ใช่รายจ่ายจริงของสาขานั้น เช่น เงินประกันผลงาน
ซึ่งเป็นหนี้สิน ไม่ใช่ค่าใช้จ่าย พอถูกนับรวมเข้าไป ยอด "รวมรายจ่าย" กับ "คงเหลือ"
ก็เพี้ยนตามไปด้วย

ที่นี่จึงให้ตั้งได้ว่าสาขาไหนไม่ต้องเอาบัญชีไหนมาคิด ตั้งเป็นรายสาขา
สาขาที่ไม่ได้ตั้งค่าไว้ รายงานจะออกเหมือนเดิมทุกประการ
"""
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class BranchPLExclusion(models.Model):
    _name = 'npd.branch.pl.exclusion'
    _description = 'บัญชีที่ไม่แสดงในงบรายรับ-รายจ่ายรายสาขา'
    _order = 'branch_id'
    _rec_name = 'branch_id'

    branch_id = fields.Many2one('res.branch', string='สาขา', required=True,
                                ondelete='cascade', index=True)
    account_ids = fields.Many2many(
        'account.account', 'npd_branch_pl_exclusion_account_rel',
        'exclusion_id', 'account_id', string='บัญชีที่ไม่ต้องแสดง',
        help='บัญชีที่เลือกไว้จะไม่ถูกนำมาแสดงและไม่ถูกนับใน "รวมรายจ่าย" '
             'กับ "คงเหลือ" ของสาขานี้')
    account_count = fields.Integer(string='จำนวนบัญชี',
                                   compute='_compute_account_count', store=True)
    active = fields.Boolean(string='ใช้งาน', default=True,
                            help='ปิดไว้ชั่วคราวได้ โดยไม่ต้องลบรายการบัญชีที่เลือกไว้')
    note = fields.Text(string='หมายเหตุ',
                       help='บันทึกเหตุผลไว้ เช่น ใครสั่งให้ตัดออก และตั้งแต่เมื่อไร')

    _sql_constraints = [
        ('branch_uniq', 'unique(branch_id)',
         'สาขานี้มีการตั้งค่าอยู่แล้ว กรุณาแก้ไขรายการเดิมแทนการสร้างใหม่'),
    ]

    @api.depends('account_ids')
    def _compute_account_count(self):
        for rec in self:
            rec.account_count = len(rec.account_ids)

    @api.constrains('branch_id')
    def _check_branch_unique_including_archived(self):
        """กันซ้ำให้ครอบถึงรายการที่ปิดใช้งานไว้ด้วย

        _sql_constraints กันซ้ำได้อยู่แล้ว แต่ข้อความที่ผู้ใช้เห็นจะงง
        ถ้าตัวที่ซ้ำถูกปิดใช้งานอยู่และมองไม่เห็นในหน้าจอ
        """
        for rec in self:
            other = self.search([
                ('branch_id', '=', rec.branch_id.id),
                ('id', '!=', rec.id),
                ('active', 'in', (True, False)),
            ], limit=1)
            if other:
                raise ValidationError(_(
                    'สาขา "%s" มีการตั้งค่าอยู่แล้ว%s\n'
                    'กรุณาแก้ไขรายการเดิมแทนการสร้างใหม่'
                ) % (rec.branch_id.name or '',
                     ' (แต่ถูกปิดใช้งานไว้ ให้เปิดตัวกรองรายการที่เก็บถาวร)'
                     if not other.active else ''))

    @api.model
    def excluded_account_ids_for(self, branch):
        """คืน set ของ account id ที่สาขานี้สั่งไม่ให้แสดง

        สาขาที่ไม่ได้ตั้งค่าไว้จะได้ set ว่าง รายงานจึงออกเหมือนเดิม
        """
        if not branch:
            return set()
        config = self.sudo().search([('branch_id', '=', branch.id)], limit=1)
        return set(config.account_ids.ids) if config else set()
