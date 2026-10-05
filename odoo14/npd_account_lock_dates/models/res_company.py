# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.exceptions import AccessError

from .lock_fields import LOCK_DATE_FIELDS, LOCK_FIELD_LABELS, SOFT_LOCK_DATE_FIELDS, is_unlock, may_unlock


class ResCompany(models.Model):
    _inherit = 'res.company'

    def write(self, vals):
        """บันทึกประวัติทุกครั้งที่วันล็อกเปลี่ยน และกันการปลดล็อกจากช่องทางที่ไม่มีสิทธิ์

        ดักที่นี่แทนที่ตัวหน้าจอ เพราะ AI-IT (ปิดงบ/ย้อนกลับ) สคริปต์ และงานตั้งเวลา
        เขียนวันล็อกตรงเข้าบริษัท ไม่ผ่านหน้าจอ
        เรียก super() ก่อนบันทึก: ตัวตรวจของ account (_validate_locks) ยังทำงานครบ
        ถ้าตัวตรวจไม่ผ่าน จะไม่มีแถวประวัติ และธุรกรรมย้อนกลับทั้งก้อน
        """
        fnames = [f for f in LOCK_DATE_FIELDS if f in vals]
        if not fnames:
            return super().write(vals)
        companies = self.sudo()
        before = {c.id: {f: c[f] for f in fnames} for c in companies}
        companies._npd_check_unlock_right(before, vals)
        res = super().write(vals)
        self.env['npd.account.lock.log'].sudo()._log_lock_changes(companies, before, fnames)
        return res

    def _npd_check_unlock_right(self, before, vals):
        """ปลดล็อก/ถอยวันล็อกได้เฉพาะกลุ่มผู้ปิดงวดบัญชี ไม่ว่าจะมาจากช่องทางไหน

        Odoo เองไม่ตรวจการถอยล็อกธรรมดาเลย (ตรวจแค่ล็อกถาวร) และ AI-IT "ถอยทั้งหมด"
        เขียนค่าเดิมกลับด้วย sudo โดยไม่ดูค่าปัจจุบัน ถ้าไม่กันที่นี่ ล็อกที่ฝ่ายบัญชีเพิ่งเลื่อนไปข้างหน้า
        จะถูกถอยกลับจนงวดเปิดหมดโดยไม่มีใครรู้ ล็อกถาวรไม่ต้องตรวจซ้ำ Odoo ห้ามถอยอยู่แล้ว
        """
        soft = [f for f in SOFT_LOCK_DATE_FIELDS if f in vals]
        if not soft:
            return
        for company in self:
            for fname in soft:
                if not is_unlock(before[company.id][fname], fields.Date.to_date(vals[fname])):
                    continue
                if may_unlock(self.env):
                    return
                raise AccessError(
                    'ปลดล็อก/ถอยวัน "%s" ของ %s ได้เฉพาะผู้ใช้กลุ่ม ผู้ปิดงวดบัญชี '
                    'ผ่านเมนู การกำหนดค่า > การบัญชี > ล็อกงวดบัญชี'
                    % (LOCK_FIELD_LABELS[fname], company.name)
                )
