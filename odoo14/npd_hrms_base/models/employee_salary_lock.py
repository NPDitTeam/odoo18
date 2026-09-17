# -*- coding: utf-8 -*-
"""ล็อกการแก้ไขข้อมูลค่าจ้างรายผู้ใช้ (พอร์ตจากโมดูล employee_salary_field_lock ของ Odoo 14)

ผู้ใช้ที่ติ๊ก "ล็อคการแก้ไขค่าจ้าง/เงินเพิ่ม" ในหน้าตั้งค่าผู้ใช้:
  - ฟอร์มพนักงานเป็นอ่านอย่างเดียวทั้งฟอร์ม ยกเว้นสาขา ตำแหน่ง และแท็บข้อมูลต่างชาติ
    (เอกสารแรงงานต่างชาติต้องอัปเดตบ่อยและไม่เกี่ยวกับค่าจ้าง)
  - ค่าจ้าง/เงินเพิ่ม 5 ช่อง ถูก "ซ่อน" ไม่ใช่แค่แก้ไม่ได้ ทั้งในฟอร์มและในรายการ
  - ชั้น ORM บล็อกการเขียนฟิลด์การเงินที่ค่าเปลี่ยนจริง (กันช่องทางอื่นนอกจากฟอร์ม)

ต่างจาก Odoo 14 ตรงที่ Odoo 18 cache โครงหน้าจอไว้ตามกลุ่มสิทธิ์ ไม่ใช่รายผู้ใช้
จึงต้องใส่สถานะล็อกลงใน cache key (_get_view_cache_key) ไม่งั้นผู้ใช้ที่ไม่ถูกล็อก
จะได้หน้าจอแบบล็อกของคนอื่นไปด้วย (หรือกลับกัน) ถ้าอยู่กลุ่มสิทธิ์เดียวกัน
"""
from odoo import api, fields, models
from odoo.exceptions import UserError

# แท็บที่ยังแก้ไขได้ทั้งแท็บแม้ผู้ใช้จะถูกล็อก (อ้างด้วย name ของ page)
SALARY_LOCK_EDITABLE_PAGES = ('foreign_worker',)

# ฟิลด์ที่ยังแก้ไขได้แม้ผู้ใช้จะถูกล็อก
SALARY_LOCK_EDITABLE_FIELDS = ('branch_id', 'position_id')

# ค่าจ้าง/เงินเพิ่มที่ซ่อนไปเลยเมื่อผู้ใช้ถูกล็อก
HIDDEN_SALARY_FIELDS = (
    'salary',
    'cost_of_living',
    'position_allowance',
    'experience_allowance',
    'professional_allowance',
)

# ฟิลด์การเงินที่บล็อกระดับ ORM ด้วย — จำกัดเฉพาะการเงิน ไม่ให้กระทบปุ่ม/กระบวนการอื่น
LOCKED_SALARY_FIELDS = HIDDEN_SALARY_FIELDS + (
    'enable_social_security',
    'social_security_condition',
    'social_security_fixed_amount',
    'social_security_start_date',
    'enable_tax',
    'tax_condition',
    'tax_exception',
    'tax_start_date_condition',
)


class ResUsers(models.Model):
    _inherit = 'res.users'

    lock_salary_fields = fields.Boolean(
        string='ล็อคการแก้ไขค่าจ้าง/เงินเพิ่ม',
        help='ถ้าติ๊กถูก ผู้ใช้คนนี้จะแก้ไขข้อมูลพนักงานไม่ได้ (ยกเว้นสาขา ตำแหน่ง '
             'และแท็บข้อมูลต่างชาติ) และจะไม่เห็นค่าจ้าง เงินค่าครองชีพ เงินประจำตำแหน่ง '
             'เงินค่าประสบการณ์ และเงินค่าวิชาชีพ')


class EmployeeSalary(models.Model):
    _inherit = 'employee.salary'

    def _salary_lock_active(self):
        """ผู้ใช้ปัจจุบันถูกล็อกไหม (superuser ไม่ถูกล็อก)"""
        return bool(self.env.user.lock_salary_fields) and not self.env.su

    @api.model
    def _get_view_cache_key(self, view_id=None, view_type='form', **options):
        key = super()._get_view_cache_key(view_id, view_type, **options)
        return key + (self._salary_lock_active(),)

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if not self._salary_lock_active():
            return arch, view
        if view_type == 'form':
            self._apply_salary_lock_form(arch)
        elif view_type == 'list':
            for node in arch.xpath('//field'):
                if node.get('name') in HIDDEN_SALARY_FIELDS:
                    node.set('column_invisible', '1')
                    # ยอดรวมท้ายคอลัมน์ก็เปิดเผยค่าจ้างรวม — เอาออกด้วย
                    node.attrib.pop('sum', None)
        return arch, view

    @staticmethod
    def _apply_salary_lock_form(arch):
        # เทียบด้วยตัวโหนด ไม่ใช่ชื่อ — ฟิลด์ชื่อเดียวกันอาจอยู่หลายแท็บ
        # และแท็บอื่นยังต้องถูกล็อกอยู่
        editable_nodes = set()
        for page_name in SALARY_LOCK_EDITABLE_PAGES:
            editable_nodes.update(arch.xpath("//page[@name='%s']//field" % page_name))

        for node in arch.xpath('//field'):
            name = node.get('name')
            if name in HIDDEN_SALARY_FIELDS:
                node.set('invisible', '1')
                node.set('readonly', '1')
                # ช่องที่มองไม่เห็นต้องไม่บังคับกรอก ไม่งั้นบันทึกไม่ผ่านโดยไม่รู้สาเหตุ
                node.set('required', '0')
                continue
            if name in SALARY_LOCK_EDITABLE_FIELDS or node in editable_nodes:
                continue
            node.set('readonly', '1')

        # แท็บที่เหลือแต่ฟิลด์ที่ถูกซ่อน ไม่ต้องโชว์แท็บเปล่า
        for page in arch.xpath('//page'):
            page_fields = page.xpath('.//field')
            if page_fields and all(
                    f.get('name') in HIDDEN_SALARY_FIELDS for f in page_fields):
                page.set('invisible', '1')

    def write(self, vals):
        # บล็อกเฉพาะเมื่อค่าเปลี่ยนจริง — บันทึกซ้ำค่าเดิมจากฟอร์มต้องไม่ติด
        if self._salary_lock_active():
            blocked = [f for f in LOCKED_SALARY_FIELDS if f in vals]
            for rec in self:
                for field_name in blocked:
                    field = rec._fields[field_name]
                    try:
                        new_value = field.convert_to_cache(vals[field_name], rec)
                        old_value = field.convert_to_cache(rec[field_name], rec)
                    except Exception:
                        new_value, old_value = vals[field_name], rec[field_name]
                    if new_value != old_value:
                        raise UserError(
                            'คุณไม่มีสิทธิ์แก้ไขข้อมูลค่าจ้าง/เงินเพิ่ม/ประกันสังคม/ภาษี '
                            'ของพนักงาน (บัญชีผู้ใช้ของคุณถูกตั้งค่าให้ล็อคการแก้ไข)')
        return super().write(vals)
