# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.tools import SQL

from .lock_fields import LOCK_DATE_FIELDS, LOCK_FIELD_HELP, LOCK_FIELD_LABELS


class NpdAccountLockStatus(models.Model):
    """ภาพรวมวันล็อกของทุกบริษัทที่ผู้ใช้มีสิทธิ์ (อ่านอย่างเดียว)

    ทำเป็นโมเดล _table_query ของตัวเองแทนการเปิดรายการ res.company ตรง ๆ
    เพราะกฎ res.company ให้พนักงานอ่านได้เฉพาะบริษัทที่ติ๊กอยู่มุมขวาบน
    แต่หน้านี้ต้องเห็นทุกบริษัทใน user.company_ids (กฎของโมเดลนี้กรองแทน)
    อ่าน res_company สด ๆ ทุกครั้ง จึงไม่ต้องสร้าง view ในฐานข้อมูลหรือ init()
    """
    _name = 'npd.account.lock.status'
    _description = 'สถานะการล็อกงวดบัญชีทุกบริษัท'
    _auto = False
    _order = 'id'
    _rec_name = 'company_id'
    # ให้ ORM flush ค่าที่ยังค้างในหน่วยความจำลงฐานก่อนคิวรี ไม่งั้นเพิ่งล็อกแล้วเปิดหน้านี้จะเห็นค่าเก่า
    _depends = {
        'res.company': [*LOCK_DATE_FIELDS, 'active'],
        'npd.account.lock.log': ['company_id', 'change_datetime', 'user_id'],
        'account.lock_exception': ['company_id', 'active', 'end_datetime'],
    }

    company_id = fields.Many2one('res.company', string='บริษัท', readonly=True)
    fiscalyear_lock_date = fields.Date(
        string=LOCK_FIELD_LABELS['fiscalyear_lock_date'],
        help=LOCK_FIELD_HELP['fiscalyear_lock_date'], readonly=True,
    )
    tax_lock_date = fields.Date(
        string=LOCK_FIELD_LABELS['tax_lock_date'],
        help=LOCK_FIELD_HELP['tax_lock_date'], readonly=True,
    )
    sale_lock_date = fields.Date(
        string=LOCK_FIELD_LABELS['sale_lock_date'],
        help=LOCK_FIELD_HELP['sale_lock_date'], readonly=True,
    )
    purchase_lock_date = fields.Date(
        string=LOCK_FIELD_LABELS['purchase_lock_date'],
        help=LOCK_FIELD_HELP['purchase_lock_date'], readonly=True,
    )
    hard_lock_date = fields.Date(
        string=LOCK_FIELD_LABELS['hard_lock_date'],
        help=LOCK_FIELD_HELP['hard_lock_date'], readonly=True,
    )
    effective_lock_date = fields.Date(
        string='ล็อกทุกสมุดมีผลถึง', readonly=True,
        help='วันที่ที่มากกว่าระหว่าง ปิดงวดบัญชี กับ ล็อกถาวร '
             '(ไม่นับข้อยกเว้นการล็อก ถ้ามีข้อยกเว้นที่ยังมีผล บางคน/ทุกคนอาจแก้เอกสารก่อนวันนี้ได้)',
    )
    active_exception_count = fields.Integer(
        string='ข้อยกเว้นที่ยังมีผล', readonly=True,
        help='จำนวนข้อยกเว้นการล็อก (ปลดล็อกให้บางคน/ชั่วคราว) ที่ยังไม่หมดอายุและยังไม่ถูกยกเลิก '
             'ดูรายละเอียดได้ในประวัติการล็อกงวด ช่องทาง = ข้อยกเว้นการล็อก',
    )
    last_change_date = fields.Datetime(string='แก้ล่าสุดเมื่อ', readonly=True)
    last_change_user_id = fields.Many2one('res.users', string='แก้ล่าสุดโดย', readonly=True)

    @property
    def _table_query(self):
        # GREATEST ของ PostgreSQL ข้าม NULL ให้เอง ช่องที่ไม่ล็อกจึงไม่ทำให้ผลเป็นค่าว่าง
        return SQL("""
            SELECT c.id AS id,
                   c.id AS company_id,
                   c.fiscalyear_lock_date,
                   c.tax_lock_date,
                   c.sale_lock_date,
                   c.purchase_lock_date,
                   c.hard_lock_date,
                   GREATEST(c.fiscalyear_lock_date, c.hard_lock_date) AS effective_lock_date,
                   last.change_datetime AS last_change_date,
                   last.user_id AS last_change_user_id,
                   (SELECT COUNT(*)
                      FROM account_lock_exception e
                     WHERE e.company_id = c.id
                       AND e.active
                       AND (e.end_datetime IS NULL OR e.end_datetime >= (NOW() AT TIME ZONE 'UTC'))
                   ) AS active_exception_count
              FROM res_company c
              LEFT JOIN LATERAL (
                    SELECT l.change_datetime, l.user_id
                      FROM npd_account_lock_log l
                     WHERE l.company_id = c.id
                  ORDER BY l.change_datetime DESC, l.id DESC
                     LIMIT 1
              ) last ON TRUE
             WHERE c.active
        """)

    @api.depends('company_id')
    def _compute_display_name(self):
        # ค่าตั้งต้นของ Odoo ใช้ชื่อบริษัทตาม _rec_name โดยอ่านในสิทธิ์ผู้ใช้
        # กฎ res.company ให้อ่านได้แค่บริษัทที่ติ๊กอยู่มุมขวาบน กดเปิดแถวบริษัทอื่นจะขึ้น AccessError
        # ทั้งที่หน้านี้ทำมาเพื่อดูบริษัทที่ไม่ได้ติ๊กโดยเฉพาะ จึงอ่านชื่อด้วย sudo
        for rec in self:
            rec.display_name = rec.company_id.sudo().display_name
