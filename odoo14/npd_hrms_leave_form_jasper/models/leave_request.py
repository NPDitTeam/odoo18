# -*- coding: utf-8 -*-
"""ฟิลด์เตรียมข้อมูลสำหรับพิมพ์ใบลา NPD/HR.03 ด้วย Jasper

Jasper อ่านค่าจากฟิลด์ของเรคคอร์ดตรง ๆ ค่าที่ต้องจัดรูป (เดือนไทย พ.ศ.
เวลาไทย ติ๊ก/ไม่ติ๊ก) จึงเตรียมเป็นข้อความไว้ที่นี่ทั้งหมด template แค่วาง

ช่องติ๊กส่งเป็น 'Y' / '' ให้ template ใช้ printWhen วาดเครื่องหมายถูก

ตารางประเภทการลาเป็นช่องคงที่ TYPE_SLOTS แถว (Jasper ในระบบนี้วนรายการ
ย่อยไม่สะดวก) ประเภทการลามากกว่านี้จะถูกตัด ซึ่งตอนนี้มี 8 ประเภท
"""
import re

import pytz

from odoo import api, models, fields

THAI_MONTHS = [
    'มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
    'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม',
]

# ลาไม่ถึง 8 ชม. ในวันเดียว = ลาในเวลาทำงาน (รายชั่วโมง)
# 08:00–17:00 / 07:00–16:00 = ลาทั้งวัน
HOURLY_LEAVE_MAX_MINUTES = 8 * 60

TYPE_SLOTS = 10

# ความยาวที่ช่องตำแหน่งบนใบลารับได้ (ฟอนต์ 13)
POSITION_MAX_CHARS = 40

# ฟิลด์ทั้งหมดคำนวณในเมธอดเดียว ประกาศเป็นรายการไว้ให้ไล่ง่าย
_FORM_FIELDS = [
    'doc_no', 'written_at',
    'created_day', 'created_month', 'created_year', 'created_short',
    'fullname', 'position', 'leave_type',
    'is_hourly', 'is_daily', 'start_time', 'end_time', 'hours', 'minutes',
    'start_day', 'start_month', 'start_year',
    'end_day', 'end_month', 'end_year', 'days',
    'is_pending', 'is_approved', 'is_rejected', 'is_cancelled',
    'reason', 'approver', 'approved_short',
] + ['type_%s_%d' % (kind, i)
     for i in range(1, TYPE_SLOTS + 1) for kind in ('name', 'check', 'note')]


def _minutes(text):
    match = re.match(r'^(\d{1,2}):(\d{2})', text or '')
    return int(match.group(1)) * 60 + int(match.group(2)) if match else None


def _short_position(name):
    """ตำแหน่งยาว ๆ ตัดชื่อภาษาอังกฤษในวงเล็บท้ายทิ้ง ไม่งั้นล้นช่องบนใบลา

    'เจ้าหน้าที่จัดซื้อและบริหารสินค้าคงคลัง (Procurement & Inventory Officer)'
    -> 'เจ้าหน้าที่จัดซื้อและบริหารสินค้าคงคลัง'
    """
    name = (name or '').strip()
    if len(name) > POSITION_MAX_CHARS and ' (' in name:
        name = name.split(' (', 1)[0].strip()
    return name


class HrAttendanceBranchLeave(models.Model):
    _inherit = 'hr.attendance.branch.leave'

    for _name in _FORM_FIELDS:
        locals()['jasper_' + _name] = fields.Char(compute='_compute_jasper_form')
    del _name

    def _jasper_local(self, value):
        """วันเวลา UTC ของ Odoo -> วันที่ตามเวลาไทย (หรือ tz ของบริษัทผู้ใช้)"""
        if not value:
            return None
        tz = pytz.timezone(self.env.user.tz or 'Asia/Bangkok')
        return pytz.utc.localize(value).astimezone(tz).date()

    @staticmethod
    def _jasper_thai_date(value):
        if not value:
            return {'day': '', 'month': '', 'year': '', 'short': ''}
        return {
            'day': str(value.day),
            'month': THAI_MONTHS[value.month - 1],
            'year': str(value.year + 543),
            'short': '%02d/%02d/%d' % (value.day, value.month, value.year + 543),
        }

    def _jasper_leave_types(self):
        """ประเภทการลาที่พิมพ์ในตาราง = ประเภทของบริษัทพนักงาน (ตามลำดับ)

        ประเภทของใบนี้ที่ปิดใช้ไปแล้วหรือเป็นของบริษัทอื่น (ใบเก่าที่ซิงก์มา)
        ต่อท้ายไว้ ไม่งั้นใบนั้นจะไม่มีช่องไหนถูกติ๊ก
        """
        LeaveType = self.env['hrms.leave.type'].sudo()
        domain = [('company_id', '=', self.company_id.id)] if self.company_id else []
        types = LeaveType.search(domain) or LeaveType.search([])
        if self.leave_type_id and self.leave_type_id not in types:
            types |= self.leave_type_id
        return types[:TYPE_SLOTS]

    @api.depends('employee_id', 'company_id', 'branch_id', 'position_id', 'leave_type_id',
                 'leave_start_date', 'leave_end_date', 'start_time', 'end_time', 'note',
                 'state', 'reason', 'approved_by', 'approved_at', 'requested_at')
    def _compute_jasper_form(self):
        for rec in self:
            for name, value in rec._jasper_form_values().items():
                rec['jasper_' + name] = value

    def _jasper_form_values(self):
        self.ensure_one()
        emp = self.employee_id
        branch = self.branch_id.name or ''
        if branch and branch != 'สำนักงานใหญ่':
            branch = 'สาขา' + branch

        start_min, end_min = _minutes(self.start_time), _minutes(self.end_time)
        duration = (end_min - start_min) if None not in (start_min, end_min) else None
        is_hourly = (self.leave_start_date == self.leave_end_date
                     and duration is not None
                     and 0 < duration < HOURLY_LEAVE_MAX_MINUTES)

        created = self._jasper_thai_date(
            self._jasper_local(self.requested_at or self.create_date))
        start = self._jasper_thai_date(self.leave_start_date)
        end = self._jasper_thai_date(self.leave_end_date)
        state = self.state or 'รออนุมัติ'
        decided = state in ('อนุมัติ', 'ไม่อนุมัติ')
        approver = self.approved_by

        values = {
            'doc_no': str(self.id),
            'written_at': ('%s %s' % (self.company_id.name or '', branch)).strip(),
            'created_day': created['day'],
            'created_month': created['month'],
            'created_year': created['year'],
            'created_short': created['short'],
            'fullname': emp.full_name or self.username or '',
            'position': _short_position(self.position_id.name),
            'leave_type': self.leave_type_id.name or self.leave_type_name or '',
            'is_hourly': 'Y' if is_hourly else '',
            'is_daily': '' if is_hourly else 'Y',
            'start_time': (self.start_time or '')[:5] if is_hourly else '',
            'end_time': (self.end_time or '')[:5] if is_hourly else '',
            'hours': str(duration // 60) if is_hourly else '',
            'minutes': str(duration % 60) if is_hourly else '',
            'start_day': start['day'],
            'start_month': start['month'],
            'start_year': start['year'],
            'end_day': '' if is_hourly else end['day'],
            'end_month': '' if is_hourly else end['month'],
            'end_year': '' if is_hourly else end['year'],
            'days': '' if is_hourly else str(self.leave_days or ''),
            'is_pending': 'Y' if state == 'รออนุมัติ' else '',
            'is_approved': 'Y' if state == 'อนุมัติ' else '',
            'is_rejected': 'Y' if state == 'ไม่อนุมัติ' else '',
            'is_cancelled': 'Y' if state == 'ยกเลิก' else '',
            'reason': self.reason or '',
            'approver': (approver.full_name or '') if decided and approver else '',
            'approved_short': self._jasper_thai_date(
                self._jasper_local(self.approved_at))['short'] if decided else '',
        }
        types = self._jasper_leave_types()
        for i in range(1, TYPE_SLOTS + 1):
            leave_type = types[i - 1] if i <= len(types) else None
            checked = bool(leave_type) and leave_type == self.leave_type_id
            values['type_name_%d' % i] = leave_type.name if leave_type else ''
            values['type_check_%d' % i] = 'Y' if checked else ''
            values['type_note_%d' % i] = (self.note or '') if checked else ''
        return values
