from odoo import _, models
from odoo.exceptions import UserError


class AccountAdvanceClear(models.Model):
    _inherit = 'account.advance.clear'

    def cancel_advance(self):
        """ยกเลิก Advance Clear ที่ลงบัญชีแล้วด้วยการกลับรายการ (เดิมลบรายการบัญชี)"""
        self.write({'is_approved': False})
        for clear in self:
            if clear.move_id:
                clear.move_id._npd_cancel_by_reverse(_('ยกเลิก %s') % (clear.name or ''))
        self._sync_wht_cert_state('cancel')
        self.write({'state': 'cancel'})
        return True

    def _npd_block_if_posted(self):
        for clear in self:
            if clear.move_id:
                raise UserError(_('%s เคยลงบัญชีแล้ว รีเซตเป็นฉบับร่างไม่ได้ (เลขรายการบัญชีจะข้าม)\n'
                                  'ให้กด "ยกเลิก" ระบบจะกลับขาบัญชีให้ แล้วทำใบใหม่') % (clear.name or ''))

    def set_draft(self):
        self._npd_block_if_posted()
        return super().set_draft()

    def action_reset_draft_keep_ai(self):
        self._npd_block_if_posted()
        return super().action_reset_draft_keep_ai()
