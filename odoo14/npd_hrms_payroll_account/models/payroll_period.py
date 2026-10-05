# -*- coding: utf-8 -*-
"""ปุ่มลงบัญชีเงินเดือนบนรอบ + กันฝ่ายบุคคลแก้รอบที่ลงบัญชีไปแล้ว"""
from odoo import api, fields, models
from odoo.exceptions import UserError

GROUP = 'npd_hrms_payroll_account.group_payroll_account'


class PayrollPeriod(models.Model):
    _inherit = 'payroll.period'

    npd_account_link_ids = fields.One2many(
        'npd.payroll.account.move', 'period_id', string='การลงบัญชีเงินเดือน',
        groups=GROUP)
    npd_account_link_count = fields.Integer(
        string='รายการบัญชี', compute='_compute_npd_account_status', groups=GROUP)
    npd_account_status = fields.Selection([
        ('none', 'ยังไม่ลงบัญชี'),
        ('partial', 'ลงบางบริษัท'),
        ('done', 'ลงครบทุกบริษัท'),
        ('outdated', 'สลิปเปลี่ยนหลังลงบัญชี'),
    ], string='สถานะลงบัญชี', compute='_compute_npd_account_status', groups=GROUP)

    def _compute_npd_account_status(self):
        Link = self.env['npd.payroll.account.move'].sudo()
        Salary = self.env['payroll.salary'].sudo()
        for period in self:
            period_id = period._origin.id
            if not period_id:
                period.npd_account_link_count = 0
                period.npd_account_status = 'none'
                continue
            links = Link.search([('period_id', '=', period_id), ('state', '=', 'posted')])
            period.npd_account_link_count = len(links)
            companies = {company.id for company, in Salary._read_group(
                [('period_id', '=', period_id)], ['company_id'])}
            if not links:
                status = 'none'
            elif any(links.mapped('is_outdated')):
                status = 'outdated'
            elif companies <= set(links.company_id.ids):
                # "ครบ" = ทุกบริษัทที่มีสลิปในรอบมีรายการบัญชีแล้ว
                status = 'done'
            else:
                status = 'partial'
            period.npd_account_status = status

    # ------------------------------------------------------------------
    def action_open_payroll_account_wizard(self):
        self.ensure_one()
        self.env['npd.payroll.account.config']._npd_check_poster()
        if self.sudo().state not in ('approved', 'paid'):
            raise UserError('ลงบัญชีได้เฉพาะรอบที่อนุมัติแล้วหรือจ่ายแล้ว')
        wizard = self.env['npd.payroll.account.post.wizard'].create({'period_id': self.id})
        wizard._npd_build_preview()
        return wizard._npd_reopen()

    def action_view_payroll_account_moves(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'ประวัติการลงบัญชีเงินเดือน — %s' % self.sudo().display_name,
            'res_model': 'npd.payroll.account.move',
            'view_mode': 'list,form',
            'domain': [('period_id', '=', self.id)],
            'context': {'create': False},
        }

    # ------------------------------------------------------------------
    # กันแก้รอบที่ลงบัญชีแล้ว: ถ้าปล่อยให้ดึงกลับเป็นร่างแล้วคำนวณใหม่
    # ยอดในสลิปจะไม่ตรงกับบัญชีโดยไม่มีใครรู้
    # ------------------------------------------------------------------
    def _npd_guard_posted(self):
        links = self.env['npd.payroll.account.move'].sudo().search([
            ('period_id', 'in', self.ids), ('state', '=', 'posted')])
        if links:
            raise UserError('รอบนี้ลงบัญชีแล้ว (บริษัท %s) ให้ฝ่ายบัญชีกลับรายการก่อน' % (
                ', '.join(sorted(set(links.mapped('company_id.name'))))))

    def action_reset_draft(self):
        self._npd_guard_posted()
        return super().action_reset_draft()

    def action_cancel(self):
        self._npd_guard_posted()
        return super().action_cancel()

    @api.ondelete(at_uninstall=False)
    def _unlink_except_payroll_account(self):
        if self.env['npd.payroll.account.move'].sudo().search_count(
                [('period_id', 'in', self.ids)]):
            raise UserError('รอบนี้มีประวัติการลงบัญชีเงินเดือนแล้ว ลบไม่ได้')
