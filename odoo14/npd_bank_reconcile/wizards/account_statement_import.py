# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class AccountStatementImport(models.TransientModel):
    _inherit = 'account.statement.import'

    # วิซาร์ดของ OCA หาสมุดจาก context อย่างเดียว เปิดจากเมนูจึงพัง
    # ("start the wizard from the right bank journal") เพราะไฟล์ธนาคารไทยไม่มีเลขบัญชี
    npd_journal_id = fields.Many2one(
        'account.journal',
        string='สมุดบัญชีธนาคาร',
        domain="[('type', '=', 'bank')]",
        default=lambda self: self.env.context.get('journal_id'),
    )

    @api.onchange('npd_journal_id')
    def _onchange_npd_journal_id(self):
        if self.npd_journal_id.default_sheet_mapping_id:
            self.sheet_mapping_id = self.npd_journal_id.default_sheet_mapping_id

    def _npd_import_ctx(self):
        """ตรวจความพร้อมของสมุดก่อนอ่านไฟล์ แล้วส่งสมุดต่อให้ OCA ทาง context

        แจ้งเป็นภาษาไทยตั้งแต่ต้น แทนข้อความอังกฤษที่โผล่กลางทางของ core/OCA
        """
        self.ensure_one()
        journal = self.npd_journal_id or self.env['account.journal'].browse(
            self.env.context.get('journal_id')
        )
        if not journal:
            raise UserError('กรุณาเลือกสมุดบัญชีธนาคารที่จะนำเข้า')
        if not journal.default_account_id:
            raise UserError(
                'สมุด %s ยังไม่ได้กำหนดบัญชีเงินฝากธนาคาร (Bank Account)' % journal.display_name
            )
        if not journal.suspense_account_id:
            raise UserError(
                'สมุด %s ยังไม่ได้กำหนดบัญชีพักธนาคาร ให้ฝ่ายบัญชีเพิ่มบัญชีพักธนาคารในผัง'
                'แล้วตั้งที่สมุดก่อนนำเข้า' % journal.display_name
            )
        if not self.sheet_mapping_id:
            raise UserError('กรุณาเลือกรูปแบบไฟล์ของธนาคาร')
        return self.with_context(journal_id=journal.id)

    def import_file_button(self):
        return super(AccountStatementImport, self._npd_import_ctx()).import_file_button()

    def import_file_and_reconcile_button(self):
        # ปุ่มนี้ของ OCA อ่าน journal_id จาก context เพื่อเปิดหน้ากระทบยอดของสมุดนั้น
        return super(
            AccountStatementImport, self._npd_import_ctx()
        ).import_file_and_reconcile_button()
