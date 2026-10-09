import re

from odoo import api, fields, models

# บัญชีที่การโอนคืนเงินใช้ เดิม o14 ระบุด้วยรหัส (9999-99, 1112-01, 1113-01, 1151-02, 4100-01)
# แต่รหัสเดียวกันใน o14 แต่ละฐานไม่ใช่บัญชีเดียวกัน (เช่น Logistics 1151-02 = ภาษีนิติบุคคลจ่ายล่วงหน้า)
# และผังของ o18 ฝ่ายบัญชีรันรหัสใหม่ จึงจับจาก "ชื่อ" บัญชีแทน แล้วเก็บเป็นค่าตั้งรายบริษัท
REFUND_ACCOUNT_RULES = {
    'refund_wht_account_id': {
        'names': ['ภาษีเงินได้ถูกหัก ณ ที่จ่าย'],
    },
    'refund_rental_income_account_id': {
        'names': ['รายได้ค่าเช่า', 'รายได้จากการให้เช่า'],
    },
    'refund_suspense_account_id': {
        'names': ['บัญชีพัก'],
    },
    # บัญชีธนาคาร ชื่อใน o14 มีเลขบัญชีต่อท้าย (1112-01 / 1113-01 ของแต่ละฐาน)
    # ผังใหม่ยังเป็นชื่อกลาง "เงินฝากกระแสรายวัน - ธ." หลายบัญชี จึงจับเลขบัญชีก่อน
    # ไม่เจอค่อยจับคำนำหน้า แล้วถ้ายังซ้ำให้เลือกรหัสที่ตรงกับ o14
    'refund_bank_current_account_id': {
        'bank_numbers': ['025-2-90298-8', '020-8-93777-4', '035-1-39757-8', '117-178329-8'],
        'prefix': 'เงินฝากกระแสรายวัน',
        'code': '1112-01',
    },
    'refund_bank_savings_account_id': {
        'bank_numbers': ['186-2-24773-9', '408-5-46107-1', '186-2-22160-2', '439-044811-6',
                         '035-1-39757-8'],
        'prefix': 'เงินฝากออมทรัพย์',
        'code': '1113-01',
    },
}
REFUND_JOURNAL_DEFAULT_NAMES = ['สมุดรายวันเช่า(สาขา)', 'สมุดรายวันขาย', 'สมุดรายวันการขาย']


def _digits(text):
    return re.sub(r'\D', '', text or '')


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

    def _npd_refund_match_account(self, accounts, rule):
        """คืนบัญชีเดียวที่ตรงกฎ ถ้าไม่เจอหรือยังซ้ำหลายบัญชีคืนค่าว่าง ให้ฝ่ายบัญชีเลือกเอง"""
        self.ensure_one()
        for name in rule.get('names', []):
            found = accounts.filtered(lambda a: (a.name or '').strip() == name)
            if len(found) == 1:
                return found
        prefix = rule.get('prefix')
        if rule.get('bank_numbers'):
            numbers = {_digits(n) for n in rule['bank_numbers']}
            found = accounts.filtered(lambda a: any(n in _digits(a.name) for n in numbers))
            if len(found) > 1 and prefix:
                found = found.filtered(lambda a: (a.name or '').startswith(prefix))
            if len(found) == 1:
                return found
            if found:
                return accounts.browse()
        if prefix:
            found = accounts.filtered(lambda a: (a.name or '').strip().startswith(prefix))
            if len(found) > 1 and rule.get('code'):
                found = found.filtered(lambda a: a.with_company(self).code == rule['code'])
            if len(found) == 1:
                return found
        return accounts.browse()

    def _npd_refund_fill_defaults(self):
        """เติมเฉพาะช่องที่ยังว่าง ไม่ทับที่ฝ่ายบัญชีตั้งไว้ รันซ้ำได้"""
        Account = self.env['account.account'].sudo()
        Journal = self.env['account.journal'].sudo()
        for company in self:
            vals = {}
            accounts = Account.with_company(company).search([('company_ids', 'in', company.id),
                                                             ('deprecated', '=', False)])
            for field, rule in REFUND_ACCOUNT_RULES.items():
                if company[field]:
                    continue
                account = company._npd_refund_match_account(accounts, rule)
                if account:
                    vals[field] = account.id
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
