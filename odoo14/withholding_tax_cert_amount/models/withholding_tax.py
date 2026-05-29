from odoo import api, fields, models


class WithholdingTaxType(models.Model):
    _name = 'withholding.tax.type'
    _description = 'ประเภทภาษีหัก ณ ที่จ่าย'

    wt_cert_income_type = fields.Selection([
        ('1', '40(1) เงินเดือน ค่าจ้าง'),
        ('2', '40(2) ค่านายหน้า'),
        ('3', '40(3) ค่าลิขสิทธิ์'),
        ('5', '40(4)ก การลงทุน'),
        ('6', '40(4)ข อื่นๆ'),
        ('7', '40(5)-(8)'),
        ('8', 'อื่นๆ (3 เตรส)'),
    ], string='ประเภทเงินได้', required=True)
    percent_tax = fields.Float(string='อัตราภาษี (%)')
    title_number_form = fields.Char(string='แบบฟอร์ม')

    _sql_constraints = [
        ('unique_income_type', 'unique(wt_cert_income_type)', 'ประเภทเงินได้ซ้ำ!'),
    ]


class WithholdingTaxCert(models.Model):
    _inherit = 'withholding.tax.cert'

    # Extra fields needed by account_advance and other modules
    number = fields.Char(string='เลขที่หนังสือ')
    advance_clear_id = fields.Many2one('account.advance.clear', string='Account Advance Clear', ondelete='cascade')
    base_amount = fields.Monetary(string='ฐานภาษี', compute='_compute_amounts_custom', store=True)
    tax_amount = fields.Monetary(string='ภาษีที่หัก', compute='_compute_amounts_custom', store=True)

    @api.depends('wht_line.base', 'wht_line.amount')
    def _compute_amounts_custom(self):
        for cert in self:
            cert.base_amount = sum(cert.wht_line.mapped('base'))
            cert.tax_amount = sum(cert.wht_line.mapped('amount'))
