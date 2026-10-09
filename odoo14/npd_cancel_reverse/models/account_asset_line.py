from odoo import models


class AccountAssetLine(models.Model):
    _inherit = 'account.asset.line'

    def unlink_move(self):
        """ลบรายการค่าเสื่อม -> เปิดหน้ากลับรายการเสมอ
        (เดิมถ้าโปรไฟล์ไม่เปิด allow_reversal จะลบรายการบัญชีทิ้ง เลขข้าม)"""
        self.ensure_one()
        return {
            'name': self.env._('Reverse Move'),
            'view_mode': 'form',
            'res_model': 'wiz.asset.move.reverse',
            'target': 'new',
            'type': 'ir.actions.act_window',
            'context': dict(self.env.context, active_model=self._name, active_ids=self.ids, active_id=self.id),
        }
