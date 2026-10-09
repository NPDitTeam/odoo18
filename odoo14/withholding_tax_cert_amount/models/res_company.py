from odoo import api, fields, models

# แบบ ภ.ง.ด. -> ฟิลด์บัญชีของบริษัท (ยกมาจาก o14 โมดูล account_config)
PND_ACCOUNT_FIELDS = {
    'pnd1': 'account_pnd1_withholding_tax_id',
    'pnd1a': 'account_pnd1a_withholding_tax_id',
    'pnd3': 'account_pnd3_withholding_tax_id',
    'pnd3a': 'account_pnd3a_withholding_tax_id',
    'pnd53': 'account_pnd53_withholding_tax_id',
}


class ResCompany(models.Model):
    _inherit = 'res.company'

    account_pnd1_withholding_tax_id = fields.Many2one('account.account', string='บัญชีภาษีหัก ณ ที่จ่าย ภ.ง.ด.1')
    account_pnd1a_withholding_tax_id = fields.Many2one('account.account', string='บัญชีภาษีหัก ณ ที่จ่าย ภ.ง.ด.1ก')
    account_pnd3_withholding_tax_id = fields.Many2one('account.account', string='บัญชีภาษีหัก ณ ที่จ่าย ภ.ง.ด.3')
    account_pnd3a_withholding_tax_id = fields.Many2one('account.account', string='บัญชีภาษีหัก ณ ที่จ่าย ภ.ง.ด.3ก')
    account_pnd53_withholding_tax_id = fields.Many2one('account.account', string='บัญชีภาษีหัก ณ ที่จ่าย ภ.ง.ด.53')


class WithholdingTaxCert(models.Model):
    _inherit = 'withholding.tax.cert'

    # หน้ารับชำระ (account_payment_invoice) และใบสำคัญ (account_voucher_npd) ลงขาภาษีหัก ณ ที่จ่าย
    # ด้วยบัญชีนี้ เหมือน o14 ที่คำนวณจากแบบ ภ.ง.ด. + บัญชีที่ตั้งไว้ในบริษัท
    account_id = fields.Many2one('account.account', string='บัญชีภาษีหัก ณ ที่จ่าย',
                                 compute='_compute_npd_wht_account', store=True, readonly=False)

    @api.depends('income_tax_form', 'company_id')
    def _compute_npd_wht_account(self):
        for cert in self:
            field = PND_ACCOUNT_FIELDS.get(cert.income_tax_form)
            cert.account_id = cert.company_id[field] if field else False
