# -*- coding: utf-8 -*-
"""บอกว่าจะดึงอะไรจาก Odoo 14 มาลงที่ไหนของ Odoo 18 และแปลงยังไง

ชื่อโมเดลสองฝั่งส่วนใหญ่ตรงกันอยู่แล้วเพราะพอร์ตมาจากกัน ที่ต่างมีไม่กี่ตัว
และเก็บไว้ในตารางข้างล่างนี้ที่เดียว ไม่กระจายไปอยู่ในโค้ด

เรื่องที่ต้องระวังเป็นพิเศษ
-------------------------
**บริษัท** ฝั่ง 14 เก็บเป็นข้อความชื่อบริษัท (ช่อง ``company``) ส่วนฝั่ง 18
เก็บเป็นการอ้างถึง ``res.company`` จริง ชื่อสองฝั่งเว้นวรรคไม่เหมือนกันด้วย
จึงมีตารางจับคู่บริษัทให้แก้เองได้ พร้อมเดาให้อัตโนมัติตอนติดตั้ง

**ค่าคอมมิชชั่น** ฝั่ง 14 ไม่มีการคำนวณ เก็บเป็นบรรทัดรายได้ในสลิป
(``payroll.salary.line`` ประเภทรายได้ ชื่อ "ค่าคอมมิชชั่น") ส่วนฝั่ง 18
มีเอนจินคำนวณของตัวเองและเก็บลงช่อง ``commission_*`` บนสลิป
สลิปที่ดึงมาจาก 14 จึงถือเป็นประวัติที่ปิดยอดแล้ว ห้ามให้ฝั่ง 18 คำนวณทับ
ตัวเอนจินจะตั้งค่าสถานะสลิปที่ดึงมาให้เป็น "ปิดแล้ว" และไม่แตะค่าคอมของมัน

**เวลาเข้าออกงาน** ฝั่ง 14 เก็บ ``checked_at`` เป็นข้อความเวลาไทย
ส่วนฝั่ง 18 เป็นช่องวันเวลาจริงซึ่ง Odoo เก็บเป็น UTC ต้องลบเจ็ดชั่วโมง
ถ้าลืมข้อนี้ เวลาเข้างานจะเพี้ยนไปเจ็ดชั่วโมงและสายกันทั้งบริษัท
"""
import logging
import re

from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

# ชื่อโมเดลที่สองฝั่งไม่ตรงกัน — นอกจากนี้ใช้ชื่อเดียวกันทั้งคู่
MODEL_RENAMES = {
    # ฝั่ง 14 ตารางนี้เก็บโควตาวันลาของพนักงาน ไม่ใช่ตารางหลักของประเภทลา
    # ปลายทางจริงจึงเป็นตารางยอดวันลา ไม่ใช่ตารางประเภทลา
    'hr.leave.type.custom': 'hrms.leave.balance',
    'hr.branch.custom': 'res.branch',
    'medical.expense.limit': 'hrms.medical.limit',
    'medical.expense.opening': 'hrms.medical.opening',
    'employee.foreign.doc.status': 'hrms.foreign.doc.status',
}

# ช่องที่เก็บของเดียวกันแต่ตั้งชื่อไม่เหมือนกัน — {โมเดลฝั่ง 14: {ชื่อ 14: ชื่อ 18}}
#
# ค่าข้างในตรงกันอยู่แล้ว ต่างแค่ชื่อช่อง เช่นรายการหักฝั่ง 14 เก็บประเภทไว้ที่
# ``category`` ด้วยค่า late/early/leave/absent/suspension ซึ่งตรงกับตัวเลือกของ
# ``kind`` ฝั่ง 18 ทุกตัว ถ้าไม่แมปชื่อให้ ช่องบังคับฝั่ง 18 จะว่างแล้วบันทึกไม่ผ่าน
# ทั้งตาราง ทำให้สลิปที่ยกมาไม่มีรายการหักเลยทั้งที่ยอดรวมยังดูถูก
FIELD_RENAMES = {
    'payroll.deduction.line': {
        'category': 'kind',
        # ฝั่ง 14 แยกเป็นคำอธิบายกับรายละเอียดเวลา ฝั่ง 18 มีช่องเดียว
        # เอารายละเอียดเวลาเป็นหลักเพราะบอกได้มากกว่า เช่น "เข้า 08:16 (กะ 08:00)"
        'time_detail': 'detail',
    },
    'payroll.ot.line': {
        'rate_multiplier': 'rate',
        'start_time_x': 'start_time_text',
        'end_time_x': 'end_time_text',
    },
}

# ฟิลด์ที่ไม่ดึงข้ามฐานเด็ดขาด
# - create_uid/write_uid ชี้ไปผู้ใช้คนละชุดกัน ดึงมาแล้วจะชี้มั่ว
# - ช่องที่เก็บที่อยู่ API ของระบบ PHP เดิม ฝั่ง 18 ไม่ได้ใช้แล้ว
# - ช่องสถานะการซิงก์ของฝั่ง 14 เอง ไม่เกี่ยวกับฝั่งนี้
GLOBAL_SKIP_FIELDS = {
    'id', 'create_uid', 'write_uid', 'create_date', 'write_date',
    '__last_update', 'display_name',
    'message_ids', 'message_follower_ids', 'message_main_attachment_id',
    'activity_ids', 'website_message_ids', 'message_attachment_count',
    'lateness_api_url', 'ot_api_url',
    'sync_status', 'sync_message', 'sync_date',
}


class HrmsSyncCompanyMap(models.Model):
    """จับคู่ชื่อบริษัทฝั่ง 14 (ข้อความ) กับบริษัทจริงฝั่ง 18"""
    _name = 'npd.hrms.sync.company.map'
    _description = 'จับคู่บริษัท Odoo 14 กับ Odoo 18'
    _order = 'o14_name'

    o14_name = fields.Char(string='ชื่อบริษัทฝั่ง 14', required=True,
                           help='ค่าที่อยู่ในช่องบริษัทของพนักงานฝั่ง Odoo 14 '
                                'ตัวอักษรต้องตรงกับที่เก็บไว้จริง')
    company_id = fields.Many2one('res.company', string='บริษัทฝั่ง 18',
                                 required=True, ondelete='cascade')
    note = fields.Char(string='หมายเหตุ')

    _sql_constraints = [
        ('o14_name_uniq', 'unique(o14_name)',
         'ชื่อบริษัทฝั่ง 14 นี้ถูกจับคู่ไว้แล้ว'),
    ]

    # ------------------------------------------------------------------
    @staticmethod
    def _normalize(name):
        """ตัดสิ่งที่ทำให้ชื่อสองฝั่งดูไม่เหมือนกันออก เหลือแต่เนื้อชื่อ

        ฝั่ง 14 เขียนติดกันหมด เช่น "นภดลเอสกรุ๊ปจำกัด"
        ฝั่ง 18 เว้นวรรคและมีคำนำหน้า เช่น "บริษัท นภดล เอส กรุ๊ป จำกัด (สำนักงานใหญ่)"
        ตัดช่องว่าง คำว่าบริษัท จำกัด และวงเล็บท้ายออก จะเทียบกันติด
        """
        if not name:
            return ''
        text = re.sub(r'\([^)]*\)', '', name)
        text = text.replace('บริษัท', '').replace('จำกัด', '')
        text = text.replace('(มหาชน)', '')
        return re.sub(r'\s+', '', text).strip()

    @api.model
    def autofill(self):
        """เดาการจับคู่ให้อัตโนมัติจากชื่อที่ถอดรูปแล้ว

        คู่ไหนเดาไม่ได้จะไม่สร้างทิ้งไว้ ให้คนมาเลือกเอง ดีกว่าจับคู่ผิด
        แล้วเงินเดือนไปโผล่ผิดบริษัทโดยไม่มีใครรู้
        """
        companies = self.env['res.company'].sudo().search([])
        by_key = {self._normalize(c.name): c for c in companies}

        config = self.env['npd.hrms.sync.config'].search([('active', '=', True)], limit=1)
        if not config:
            return 0

        rows = config.execute_kw(
            'employee.salary', 'read_group',
            [[], ['company'], ['company']], {'lazy': False})
        created = 0
        for row in rows:
            raw = (row.get('company') or '').strip()
            if not raw:
                continue
            if self.search([('o14_name', '=', raw)], limit=1):
                continue
            match = by_key.get(self._normalize(raw))
            if not match:
                _logger.warning('[HRMS-SYNC] เดาบริษัทไม่ได้: "%s" '
                                'ต้องจับคู่เองที่หน้าจอจับคู่บริษัท', raw)
                continue
            self.create({'o14_name': raw, 'company_id': match.id,
                         'note': 'เดาอัตโนมัติจากชื่อ'})
            created += 1
        return created

    @api.model
    def resolve(self, o14_name):
        """แปลงชื่อบริษัทฝั่ง 14 เป็น id บริษัทฝั่ง 18 — ไม่เจอคืน False"""
        if not o14_name:
            return False
        record = self.search([('o14_name', '=', o14_name.strip())], limit=1)
        return record.company_id.id if record else False

    def action_autofill(self):
        created = self.autofill()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('จับคู่บริษัทอัตโนมัติ'),
                'message': _('จับคู่ให้ใหม่ %s บริษัท '
                             'คู่ที่เดาไม่ได้ต้องเลือกเอง') % created,
                'type': 'success' if created else 'warning',
                'sticky': False,
            },
        }


# ----------------------------------------------------------------------
# รายการสิ่งที่ซิงก์ เรียงตามลำดับที่ต้องทำ — ของที่ถูกอ้างถึงต้องมาก่อน
#
# key      = กุญแจธรรมชาติที่ใช้จับคู่ ถ้าเว้นว่างจะจับคู่ด้วยตารางแมปอย่างเดียว
# create   = สร้างใหม่ได้ไหม ถ้า False แปลว่าจับคู่กับของที่มีอยู่เท่านั้น
# children = ลูกที่ต้องยกมาพร้อมกัน (ลบของเดิมแล้วใส่ชุดใหม่ทั้งชุด)
# date_field = ช่องวันที่สำหรับตัดช่วง ใช้กับ "ดึงย้อนหลังถึงวันที่"
# ----------------------------------------------------------------------
SYNC_SPECS = [
    {
        'seq': 10,
        'name': 'สาขา',
        'o14_model': 'hr.branch.custom',
        'key': ['name'],
        # สาขาเป็นข้อมูลที่บัญชีใช้ร่วมด้วย แต่ถ้าไม่สร้างให้ ทุกอย่างที่อ้างถึง
        # สาขานั้นจะยกมาไม่ได้ทั้งสาย (สิทธิ์ลาวันเสาร์ ลงเวลา การลา)
        # จึงสร้างให้ครบตามฝั่ง 14 แล้วให้บัญชีมาตรวจชื่อซ้ำทีหลัง
        'create': True,
        'fields': ['name'],
    },
    {
        # ต้องมาก่อนพนักงาน ไม่งั้นช่องแผนกของพนักงานจะว่างทั้งหมด
        # เพราะตอนยกพนักงานมา ระบบหาแผนกปลายทางไม่เจอเลยปล่อยว่างไว้
        'seq': 15,
        'name': 'แผนก',
        'o14_model': 'hr.department.custom',
        'key': ['name'],
        'create': True,
    },
    {
        # ต้องมาหลังสาขา เพราะเขียนลงบนตัวสาขาโดยตรง
        'seq': 18,
        'name': 'ระยะเช็คอินรายสาขา',
        'o14_model': 'hr.checkin.distance',
        'handler': '_sync_checkin_distance',
        'check_handler': '_check_checkin_distance',
    },
    {
        'seq': 20,
        'name': 'ตำแหน่งงาน',
        'o14_model': 'hr.position.custom',
        'key': ['name'],
        'create': True,
    },
    {
        # ฝั่ง 14 ตารางนี้ชื่อเหมือนตารางหลักของประเภทลา แต่จริง ๆ เป็นโควตาวันลา
        # ของพนักงานแต่ละคน โดยเอาประเภทลาทั้งแปดมาเป็นคอลัมน์
        # ฝั่ง 18 แยกประเภทลาเป็นตารางหลัก แล้วเก็บยอดเป็นแถวต่อคนต่อประเภทต่อปี
        # เทียบช่องต่อช่องไม่ได้ จึงต้องใช้ตัวจัดการเฉพาะที่แตกคอลัมน์ออกเป็นแถว
        'seq': 95,
        'name': 'โควตาวันลารายบุคคล',
        'o14_model': 'hr.leave.type.custom',
        'handler': '_sync_leave_balance',
        'check_handler': '_check_leave_balance',
    },
    {
        'seq': 40,
        'name': 'พนักงาน',
        'o14_model': 'employee.salary',
        # รหัสพนักงานยึดของฝั่ง 14 เป็นหลักตามที่ตกลงไว้
        # ไม่สร้างรหัสใหม่ พนักงานจะได้ใช้รหัสเดิมล็อกอินแอปตัวใหม่ได้ทันที
        'key': ['employee_code'],
        'create': True,
        'transform': '_tf_employee',
        # รูปพนักงานเก็บเป็นไฟล์แนบ ปกติตัวซิงก์ข้ามไฟล์แนบทั้งหมดเพราะไฟล์ใหญ่
        # และส่วนมากไม่จำเป็น แต่รูปพนักงานใช้แสดงบนหน้าจอและในแอป จึงยกมาด้วย
        # (ฝั่ง 14 มีรูปอยู่ 18 คน รวมไม่ถึง 3 MB)
        'binary_fields': ['employee_image'],
    },
    {
        'seq': 50,
        'name': 'ตารางเวลาทำงาน',
        'o14_model': 'hr.work.schedule',
        'key': ['employee_id'],
        'create': True,
    },
    {
        # ต้องมาก่อนสิทธิ์รายคน เพราะรายคนชี้มาที่การตั้งค่าของสาขา
        'seq': 55,
        'name': 'ตั้งค่าสิทธิ์ลาวันเสาร์ (รายสาขา)',
        'o14_model': 'saturday.leave.config',
        'key': ['branch_id'],
        'create': True,
    },
    {
        'seq': 60,
        'name': 'สิทธิ์ลาวันเสาร์ (รายคน)',
        'o14_model': 'saturday.leave.employee',
        'key': ['employee_id', 'config_id'],
        'create': True,
    },
    {
        'seq': 70,
        'name': 'คำสั่งพักงาน',
        'o14_model': 'employee.suspension',
        'key': ['employee_id', 'date_start'],
        'create': True,
    },
    {
        # ต้องมาหลังพนักงานและตำแหน่ง เพราะอ้างถึงทั้งสองอย่าง
        'seq': 75,
        'name': 'กำหนดผู้อนุมัติ',
        'o14_model': 'approver.relations',
        'key': ['user_id', 'approver_user_id'],
        'create': True,
    },
    {
        'seq': 80,
        'name': 'สถานะเอกสารแรงงานต่างชาติ',
        'o14_model': 'employee.foreign.doc.status',
        'key': ['employee_id'],
        'create': True,
    },
    {
        'seq': 90,
        'name': 'รอบทำเงินเดือน',
        'o14_model': 'payroll.period',
        'key': ['name'],
        'create': True,
        'transform': '_tf_period',
    },
    {
        'seq': 100,
        'name': 'สลิปเงินเดือน',
        # รอบแรกดึงครบทุกงวดแล้ว งวดที่ปิดจ่ายไปแล้วไม่มีใครแก้อีก
        # รอบประจำวันจึงตามดูเฉพาะงวดล่าสุด (ตั้งจำนวนงวดได้ที่หน้าการเชื่อมต่อ)
        # ตัดด้วย "งวด" ไม่ใช่วันที่แก้ไข เพราะสลิปถูกคำนวณใหม่ทั้งใบได้ตลอด
        # ทำให้วันที่แก้ไขขยับทั้งที่ยอดเท่าเดิม จะกลายเป็นอ่านทุกใบทุกคืน
        'current_period_only': True,
        'o14_model': 'payroll.salary',
        'key': ['employee_id', 'period_id'],
        'create': True,
        'transform': '_tf_payroll',
        'date_field': False,
        'children': [
            {'o14_model': 'payroll.salary.line', 'parent_field': 'payroll_id'},
            {'o14_model': 'payroll.deduction.line', 'parent_field': 'payroll_id'},
            {'o14_model': 'payroll.ot.line', 'parent_field': 'payroll_id'},
            {'o14_model': 'payroll.tax.bracket', 'parent_field': 'payroll_id'},
        ],
    },
    {
        'seq': 110,
        'name': 'เข้างานออกงาน',
        # ข้อมูลเก่าที่ผ่านรอบทำเงินเดือนไปแล้วไม่มีใครแก้อีก
        # รอบประจำวันจึงอ่านเฉพาะที่เพิ่งเปลี่ยน ไม่ต้องกวาดทั้งหมดทุกคืน
        'recent_only': True,
        'o14_model': 'hr.attendance.branch',
        'key': ['employee_id', 'checked_at', 'check_type'],
        'create': True,
        'transform': '_tf_attendance',
        'date_field': 'date_requested',
    },
    {
        'seq': 120,
        'name': 'การลา',
        # ข้อมูลเก่าที่ผ่านรอบทำเงินเดือนไปแล้วไม่มีใครแก้อีก
        # รอบประจำวันจึงอ่านเฉพาะที่เพิ่งเปลี่ยน ไม่ต้องกวาดทั้งหมดทุกคืน
        'recent_only': True,
        'o14_model': 'hr.attendance.branch.leave',
        'key': ['employee_id', 'leave_start_date', 'leave_type_id'],
        'create': True,
        'transform': '_tf_leave',
        'date_field': 'leave_start_date',
    },
    {
        'seq': 130,
        'name': 'ขอลงเวลาย้อนหลัง',
        # ข้อมูลเก่าที่ผ่านรอบทำเงินเดือนไปแล้วไม่มีใครแก้อีก
        # รอบประจำวันจึงอ่านเฉพาะที่เพิ่งเปลี่ยน ไม่ต้องกวาดทั้งหมดทุกคืน
        'recent_only': True,
        'o14_model': 'hr.manual.time.log',
        'key': ['employee_id', 'work_date', 'reason_type_id'],
        'create': True,
        'transform': '_tf_manual',
        'date_field': 'work_date',
    },
    {
        'seq': 140,
        'name': 'ใบเตือน',
        'o14_model': 'employee.warning',
        'key': ['employee_id'],
        'create': True,
        'children': [
            {'o14_model': 'employee.warning.line', 'parent_field': 'warning_id'},
        ],
    },
    {
        'seq': 150,
        'name': 'หนังสือรับรองหัก ณ ที่จ่าย (50 ทวิ)',
        'o14_model': 'hr.withholding.tax.cert',
        'key': ['employee_id', 'year'],
        'create': True,
        'children': [
            {'o14_model': 'hr.withholding.tax.cert.line', 'parent_field': 'cert_id'},
        ],
    },
    # ---- การตั้งค่าที่ต้องมีก่อนจะคำนวณเงินเดือนรอบใหม่บนฝั่ง 18 ได้ ----
    {
        'seq': 22,
        'name': 'วันหยุดประจำปี',
        'o14_model': 'payroll.holiday',
        'key': ['name', 'year'],
        'create': True,
        'children': [
            {'o14_model': 'payroll.holiday.line', 'parent_field': 'holiday_id'},
        ],
    },
    {
        'seq': 24,
        'name': 'ตั้งค่าเงินสงเคราะห์ลูกจ้าง',
        'o14_model': 'welfare.fund.config',
        'key': ['name'],
        'create': True,
    },
    {
        'seq': 26,
        'name': 'จัดการค่าเบี้ยเลี้ยง',
        'o14_model': 'allowance.management',
        'key': ['name'],
        'create': True,
        'children': [
            {'o14_model': 'allowance.management.line', 'parent_field': 'allowance_id'},
        ],
    },
    {
        'seq': 28,
        'name': 'อัตราค่าคอมมิชชั่น',
        'o14_model': 'commission.rate.config',
        'key': ['comm_type', 'min_amount'],
        'create': True,
    },
    {
        'seq': 30,
        'name': 'ตั้งค่าค่าคอมมิชชั่นสาขา',
        'o14_model': 'commission.branch.config',
        'key': ['branch_id'],
        'create': True,
        'children': [
            {'o14_model': 'commission.branch.config.line', 'parent_field': 'config_id'},
        ],
    },
    {
        'seq': 32,
        'name': 'อัตราค่าคอมรายสาขา / Sales',
        'o14_model': 'commission.rate.branch.sales',
        'key': ['name'],
        'create': True,
    },
    {
        # ต้องมาหลังพนักงาน เพราะอ้างถึงพนักงาน
        'seq': 78,
        'name': 'ค่าคอม Sales สำนักงานใหญ่',
        'o14_model': 'commission.sale.headoffice',
        'key': ['employee_id'],
        'create': True,
    },
    {
        'seq': 145,
        'name': 'เงินได้อื่น',
        'o14_model': 'other.income',
        'key': ['employee_id', 'branch_id'],
        'create': True,
        'children': [
            {'o14_model': 'other.income.line', 'parent_field': 'other_income_id'},
        ],
    },
    {
        # เงินประกันการทำงานมีงวดผ่อนค้างอยู่ ต้องยกมาให้ครบก่อนตัดระบบ
        # ไม่งั้นพนักงานที่ผ่อนค้างจะหยุดถูกหักกลางคัน
        #
        # แยกเป็นสามหัวข้อแทนการยกลูกมาพร้อมใบ เพราะงวดการจ่ายเกาะอยู่กับ
        # "บรรทัดรายคน" ไม่ใช่ตัวใบ ถ้ายกลูกมาพร้อมใบ บรรทัดจะถูกลบและสร้างใหม่
        # ทุกรอบจนเลขอ้างอิงเปลี่ยน แล้วงวดการจ่ายจะกำพร้าไม่รู้ว่าของใคร
        'seq': 147,
        'name': 'เงินประกันการทำงาน',
        'o14_model': 'work.security.deposit',
        'key': ['name'],
        'create': True,
    },
    {
        'seq': 148,
        'name': 'เงินประกัน — รายคน',
        'o14_model': 'work.security.deposit.line',
        'key': ['deposit_id', 'employee_id'],
        'create': True,
    },
    {
        # ไม่มีกุญแจธรรมชาติของตัวเอง (คนเดียวกันจ่ายซ้ำเดือนละงวดได้)
        # จึงอาศัยตารางจับคู่อย่างเดียว ซึ่งทำงานได้เพราะบรรทัดแม่ยกมาก่อนแล้ว
        'seq': 149,
        'name': 'เงินประกัน — งวดการจ่าย',
        'o14_model': 'work.security.deposit.line.payment',
        'key': [],
        'create': True,
        'transform': '_tf_deposit_payment',
    },
    {
        # ฝั่ง 18 ไม่มีโมเดลนี้ เพราะรวมคำขอค่ารักษาเข้ากับใบขอลงเวลาย้อนหลัง
        # (ติ๊กช่อง "เป็นค่ารักษาพยาบาล" บนใบเดียวกัน) หัวข้อนี้จึงถูกข้ามเอง
        # พร้อมข้อความบอกเหตุผล เก็บไว้ในรายการเพื่อให้เห็นว่าไม่ได้ลืม
        'seq': 155,
        'name': 'คำขอค่ารักษาพยาบาล',
        'o14_model': 'medical.expense',
        'key': ['employee_id', 'amount'],
        'create': True,
    },
    {
        # ภ.ง.ด.1 รายบรรทัด — ฝั่ง 14 แยกเมนูตามบริษัทแต่เป็นตารางเดียวกัน
        # ฝั่ง 18 สร้างเองจากสลิปได้ แต่ยกประวัติมาด้วยเพื่อให้ย้อนดูปีเก่าได้
        # ตัวเอนจินสั่งไม่ให้ฝั่ง 18 สร้างซ้ำระหว่างยกข้อมูลอยู่แล้ว
        'seq': 170,
        'name': 'ภ.ง.ด.1 (รายบรรทัด)',
        'o14_model': 'pnd1.line',
        'key': ['employee_id', 'period_id', 'source_type'],
        'create': True,
    },
    {
        'seq': 160,
        'name': 'วงเงินค่ารักษาพยาบาล',
        'o14_model': 'medical.expense.limit',
        # ฝั่ง 14 มีแถวตั้งต้นที่ไม่ผูกพนักงาน ใช้เป็นค่ามาตรฐานของระบบ
        # ฝั่ง 18 บังคับว่าต้องมีพนักงานเสมอ แถวนั้นจึงยกมาไม่ได้และไม่ควรยก
        'domain': [('employee_id', '!=', False)],
        'key': ['employee_id'],
        'create': True,
    },
    {
        'seq': 170,
        'name': 'ยอดค่ารักษาที่เบิกไปแล้วก่อนใช้ระบบ',
        'o14_model': 'medical.expense.opening',
        'key': ['employee_id'],
        'create': True,
    },
]


def spec_o18_model(spec):
    """ชื่อโมเดลปลายทางของรายการนี้"""
    o14 = spec['o14_model'] if isinstance(spec, dict) else spec
    return MODEL_RENAMES.get(o14, o14)
