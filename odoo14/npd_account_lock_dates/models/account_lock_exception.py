# -*- coding: utf-8 -*-
from odoo import api, models
from odoo.exceptions import AccessError, UserError

from .lock_fields import may_unlock


class AccountLockException(models.Model):
    """ข้อยกเว้นการล็อกของ Odoo = ปลดล็อกให้บางคน/ทุกคน (ชั่วคราวหรือถาวร) โดยไม่แตะวันล็อกบนบริษัท

    Community ไม่มีหน้าจอสร้าง แต่ ACL ของ account ให้ผู้ดูแลบัญชีทุกคน (บน prod 83 คน) สร้างผ่าน RPC ได้
    ถ้าไม่กัน จะเป็นทางอ้อมที่ปลดล็อกได้โดยไม่ต้องอยู่กลุ่ม ไม่ต้องมีเหตุผล และไม่เข้าประวัติ
    จึงบังคับกติกาเดียวกับการถอยวันล็อก: เฉพาะกลุ่มผู้ปิดงวดบัญชี ต้องมีเหตุผล และบันทึกประวัติ
    """
    _inherit = 'account.lock_exception'

    @api.model_create_multi
    def create(self, vals_list):
        # สำเนาที่ Odoo สร้างเองตอนบริษัทเปลี่ยนวันล็อก (_recreate ด้านล่าง) ไม่ใช่การปลดล็อกใหม่
        # ต้องเป็น sudo ด้วย context ฝั่งเดียวปลอมผ่าน RPC ได้ แต่ RPC ได้ sudo ไม่ได้
        if self.env.su and self.env.context.get('npd_lock_exception_recreate'):
            return super().create(vals_list)
        if not may_unlock(self.env):
            raise AccessError(
                'สร้างข้อยกเว้นการล็อกงวด (ปลดล็อกให้บางคน/ชั่วคราว) ได้เฉพาะผู้ใช้กลุ่ม ผู้ปิดงวดบัญชี'
            )
        if any(not (vals.get('reason') or '').strip() for vals in vals_list):
            raise UserError('ข้อยกเว้นการล็อกงวดต้องกรอกเหตุผล')
        exceptions = super().create(vals_list)
        self.env['npd.account.lock.log'].sudo()._log_lock_exceptions(exceptions)
        return exceptions

    def _recreate(self):
        # Odoo เรียกตอน res.company.write เพื่อคัดลอกข้อยกเว้นเดิมให้ตรงวันล็อกใหม่
        # ทำผ่าน sudo + ป้าย เพื่อไม่ให้ติดตัวกันด้านบน (ผู้ดูแลระบบที่ไม่อยู่กลุ่มเขียนบริษัทจะล้มทั้งก้อน)
        # และไม่ให้เกิดแถวประวัติซ้ำ ตัวตรวจสิทธิ์ใน action_revoke ของ Odoo ยังดูผู้ใช้จริงเหมือนเดิม
        recs = self.sudo().with_context(npd_lock_exception_recreate=True)
        return super(AccountLockException, recs)._recreate()
