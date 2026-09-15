# -*- coding: utf-8 -*-

from odoo import fields, models

REPORT_TAX_TYPES = [
    ('sale', 'ภาษีขาย'),
    ('purchase', 'ภาษีซื้อ'),
]

# สาขาของเอกสารต้นทางของแถวภาษี (alias ตามคิวรีของ l10n_th_tax_report)
#   t = account_move_tax_invoice, m = account_move
# อ่านจากเอกสารก่อน (การรับชำระ / การรับ / Avance Clear) แล้วค่อยใช้สาขาของรายการบัญชี
# ให้ตรงกับคอลัมน์ Branch ที่รายงานแสดง
OWN_BRANCH_SQL = """COALESCE(
    (SELECT ap.branch_id FROM account_payment ap WHERE ap.id = t.payment_id),
    (SELECT av.branch_id FROM account_voucher av WHERE av.id = t.voucher_id),
    (SELECT ac.branch_id FROM account_advance_clear ac WHERE ac.id = t.advance_clear_id),
    m.branch_id)"""

# ภาษีซื้อ: สาขาสำนักงานใหญ่ของเอกสารต้นทาง (Avance Clear / การรับ / บิลผู้ขาย)
# เอกสารที่ไม่มีค่า (เช่น การรับที่ไม่ใช่เมนูการรับ) ใช้สาขาของเอกสารเอง
HEAD_OFFICE_BRANCH_SQL = """COALESCE(
    (SELECT ac.head_office_branch_id FROM account_advance_clear ac WHERE ac.id = t.advance_clear_id),
    (SELECT av.head_office_branch_id FROM account_voucher av WHERE av.id = t.voucher_id),
    m.head_office_branch_id,
    %s)""" % OWN_BRANCH_SQL


def branch_filter_cell(report_tax_type, branch_all, branch):
    """(ป้ายชื่อ, ค่า) ของเงื่อนไขสาขา สำหรับหัวรายงาน"""
    label = 'สาขาสำนักงานใหญ่' if report_tax_type == 'purchase' else 'สาขา'
    value = 'ทุกสาขา' if branch_all or not branch else branch.name
    return label, value


class TaxReport(models.TransientModel):
    _inherit = 'report.tax.report'

    # ต้อง store ไว้: หน้า View (HTML) browse รายงานกลับมาอีก request
    report_tax_type = fields.Selection(REPORT_TAX_TYPES, string='ประเภทภาษี')
    branch_all = fields.Boolean(string='ทุกสาขา', default=True)
    filter_branch_id = fields.Many2one('res.branch', string='สาขาที่เลือก')

    def _get_extra_where(self):
        sql, params = super()._get_extra_where()
        if self.branch_all or not self.filter_branch_id:
            return sql, params
        branch_sql = (HEAD_OFFICE_BRANCH_SQL if self.report_tax_type == 'purchase'
                      else OWN_BRANCH_SQL)
        return (sql + ' and ' + branch_sql + ' = %s',
                tuple(params) + (self.filter_branch_id.id,))

    def _get_branch_filter_cell(self):
        self.ensure_one()
        return branch_filter_cell(self.report_tax_type, self.branch_all, self.filter_branch_id)
