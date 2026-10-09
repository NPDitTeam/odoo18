from odoo import api, fields, models

# บัญชีที่การโอนคืนเงินใช้ เดิม o14 ระบุด้วยรหัส (9999-99, 1112-01, 1113-01, 1151-02, 4100-01)
# แต่ผังของ o18 ฝ่ายบัญชีรันรหัสใหม่และจะรันอีกได้ รหัสเดียวกันอาจกลายเป็นคนละบัญชี
# จึงให้ตั้งเป็นรายบริษัท แล้วเติมค่าเริ่มต้นจาก "ชื่อ" บัญชีเท่าที่หาเจอแน่ ๆ
REFUND_ACCOUNT_DEFAULT_NAMES = {
    'refund_wht_account_id': ['ภาษีเงินได้ถูกหัก ณ ที่จ่าย'],
    'refund_rental_income_account_id': ['รายได้ค่าเช่า', 'รายได้จากการให้เช่า'],
    'refund_suspense_account_id': ['บัญชีพัก'],
}
REFUND_JOURNAL_DEFAULT_NAMES = ['สมุดรายวันเช่า(สาขา)', 'สมุดรายวันขาย']


class ResCompany(models.Model):
    _inherit = 'res.company'

    refund_journal_id = fields.Many2one(
        'account.journal', string='สมุดรายวันโอนคืนเงิน',
        help='สมุดที่ใช้ลงบัญชีเอกสารโอนคืนเงินลูกค้า')
    refund_suspense_account_id = fields.Many2one(
        'account.account', string='บัญชีพัก (คืนเงินโอนเกิน/คืนหัก ณ ที่จ่าย)',
        help='เดิม o14 คือ 9999-99 บัญชีพัก')
    refund_bank_current_account_id = fields.Many2one(
        'account.account', string='บัญชีธนาคารจ่ายคืนค่าเช่าส่วนต่าง',
        help='เดิม o14 คือ 1112-01 เงินฝากกระแสรายวัน (ใช้กับค่าเช่าส่วนต่างและการกลับขา)')
    refund_bank_savings_account_id = fields.Many2one(
        'account.account', string='บัญชีธนาคารคืนเงินโอนเกิน',
        help='เดิม o14 คือ 1113-01 เงินฝากออมทรัพย์')
    refund_wht_account_id = fields.Many2one(
        'account.account', string='บัญชีภาษีเงินได้ถูกหัก ณ ที่จ่าย',
        help='เดิม o14 คือ 1151-02')
    refund_rental_income_account_id = fields.Many2one(
        'account.account', string='บัญชีรายได้ค่าเช่า (ค่าเช่าส่วนต่าง)',
        help='เดิม o14 คือ 4100-01')

    def _npd_refund_fill_defaults(self):
        """เติมเฉพาะช่องที่ยังว่าง ด้วยชื่อบัญชีที่เจอแค่บัญชีเดียวในบริษัทนั้น รันซ้ำได้"""
        Account = self.env['account.account'].sudo()
        Journal = self.env['account.journal'].sudo()
        for company in self:
            vals = {}
            accounts = Account.with_company(company).search([('company_ids', 'in', company.id),
                                                             ('deprecated', '=', False)])
            for field, names in REFUND_ACCOUNT_DEFAULT_NAMES.items():
                if company[field]:
                    continue
                for name in names:
                    found = accounts.filtered(lambda a: (a.name or '').strip() == name)
                    # ชื่อซ้ำหลายบัญชีถือว่าไม่แน่ใจ ปล่อยว่างให้ฝ่ายบัญชีเลือกเอง
                    if len(found) == 1:
                        vals[field] = found.id
                        break
            if not company.refund_journal_id:
                for name in REFUND_JOURNAL_DEFAULT_NAMES:
                    journal = Journal.search([('company_id', '=', company.id), ('name', '=', name)], limit=1)
                    if journal:
                        vals['refund_journal_id'] = journal.id
                        break
            if vals:
                company.sudo().write(vals)
        return True

    @api.model
    def _npd_refund_fill_defaults_all(self):
        self.sudo().search([])._npd_refund_fill_defaults()
