from odoo import api, fields, models


class AccountAccount(models.Model):
    _inherit = 'account.account'

    # ผังของ o18 ฝ่ายบัญชีรันรหัสใหม่ทั้งหมด (และต่างกันในแต่ละบริษัท) แต่โมดูลที่พอร์ตจาก o14
    # หลายตัวกำหนดขาบัญชีด้วยรหัส o14 จึงเก็บรหัสเดิมไว้ตามแผ่นจับคู่ที่ฝ่ายบัญชีทำ
    # ("ผังบัญชี_รวม5บริษัท_v18_นำเข้า" แผ่น แก้ไขข้อมูลรวม)
    npd_o14_code = fields.Char(string='รหัสบัญชี o14', index=True, copy=False)

    @api.model
    def _npd_o14_account(self, code, company=None):
        """บัญชีในผังใหม่ที่ตรงกับรหัส o14 ของบริษัทนั้น

        ถ้ายังไม่เคยลงรหัส o14 ไว้เลย (เช่นฐานทดสอบ) ใช้รหัสตรง ๆ แบบเดิม
        """
        company = company or self.env.company
        Account = self.with_company(company)
        account = Account.search([('npd_o14_code', '=', code),
                                  ('company_ids', 'in', company.id)], limit=1)
        if account:
            return account
        if Account.search_count([('npd_o14_code', '!=', False),
                                 ('company_ids', 'in', company.id)], limit=1):
            return Account.browse()
        return Account.search([('code', '=', code), ('company_ids', 'in', company.id)], limit=1)
