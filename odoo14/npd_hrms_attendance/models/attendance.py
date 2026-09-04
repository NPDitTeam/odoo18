# -*- coding: utf-8 -*-
"""บันทึกลงเวลาเข้า-ออกงาน

เดิมแอปยิงเข้า api_checkin_save_test1.php แล้วเขียนตาราง MySQL ``checkin_logs``
Odoo ค่อยดึงมาทีหลังด้วย cron — ตอนนี้แอปเขียนเข้าโมเดลนี้ตรง ๆ

กฎที่ย้ายมาจาก PHP ทั้งหมด:
  * กันลงเวลาซ้ำภายใน 30 นาที (DUPLICATE_CHECK_MINUTES)
  * สลับ เข้า/ออก — ลงเข้าซ้ำโดยยังไม่ออกไม่ได้
  * ตรวจรัศมีจากพิกัดสาขา (เดิม PHP ส่งค่ารัศมีให้แอปไปตรวจเอง ฝั่งเซิร์ฟเวอร์ไม่ได้ตรวจ)
"""
import logging
import math
import re
from datetime import timedelta

import pytz

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# กันกดซ้ำ/กดรัว — ค่าเดียวกับ DUPLICATE_CHECK_MINUTES ฝั่ง PHP
DUPLICATE_CHECK_MINUTES = 30

THAI_TZ = 'Asia/Bangkok'


class HrAttendanceBranch(models.Model):
    _name = 'hr.attendance.branch'
    _description = 'เข้างานออกงาน'
    _order = 'checked_at desc'
    _rec_name = 'employee_id'

    _sql_constraints = [
        ('unique_attendance', 'unique(employee_id, checked_at, check_type)',
         'ข้อมูลการลงเวลาซ้ำ!'),
    ]

    employee_id = fields.Many2one(
        'employee.salary', string='พนักงาน', required=True,
        ondelete='cascade', index=True)
    employee_code = fields.Char(
        string='รหัสพนักงาน', related='employee_id.employee_code',
        store=True, readonly=True, index=True)
    username = fields.Char(
        string='ชื่อผู้ใช้งาน', related='employee_id.full_name',
        store=True, readonly=True)

    branch_id = fields.Many2one(
        'res.branch', string='สาขา', related='employee_id.branch_id',
        store=True, readonly=True)
    department_id = fields.Many2one(
        'hr.department.custom', string='แผนก',
        related='employee_id.department_id', store=True, readonly=True)
    position_id = fields.Many2one(
        'hr.position.custom', string='ตำแหน่ง',
        related='employee_id.position_id', store=True, readonly=True)
    company_id = fields.Many2one(
        'res.company', string='บริษัท', related='employee_id.company_id',
        store=True, readonly=True)

    check_type = fields.Selection([
        ('in', 'เข้า'),
        ('out', 'ออก'),
    ], string='ประเภทการลงเวลา', required=True, index=True)

    checked_at = fields.Datetime(
        string='ลงเวลาเมื่อ', required=True, index=True,
        default=fields.Datetime.now)
    work_date = fields.Date(
        string='วันที่ทำงาน', compute='_compute_work_date', store=True, index=True,
        help='วันที่ของ "ลงเวลาเมื่อ" ตามเวลาไทย — ใช้กรอง/จัดกลุ่มโดยไม่ติดปัญหาขอบวัน')

    latitude = fields.Char(string='ละติจูด')
    longitude = fields.Char(string='ลองจิจูด')
    accuracy = fields.Float(string='ความแม่นยำ (เมตร)', digits=(8, 2))
    address = fields.Char(string='ที่อยู่ (GPS)')
    distance_from_branch = fields.Float(
        string='ระยะจากสาขา (เมตร)', digits=(10, 2), readonly=True)
    is_offsite = fields.Boolean(
        string='ลงเวลานอกรัศมี', readonly=True,
        help='บันทึกไว้เพื่อให้ฝ่ายบุคคลตรวจย้อนหลังได้ ไม่ได้ปิดกั้นการลงเวลา')
    source = fields.Selection([
        ('app', 'แอป HR'),
        ('manual', 'บันทึกโดยเจ้าหน้าที่'),
        ('import', 'นำเข้าจากระบบเดิม'),
    ], string='ที่มา', default='manual', required=True)
    note = fields.Char(string='หมายเหตุ')

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    @api.depends('checked_at')
    def _compute_work_date(self):
        tz = pytz.timezone(THAI_TZ)
        for rec in self:
            if rec.checked_at:
                rec.work_date = pytz.utc.localize(rec.checked_at).astimezone(tz).date()
            else:
                rec.work_date = False

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------
    @staticmethod
    def _clean_address(addr):
        """คลีนที่อยู่ที่ได้จาก reverse geocoding ฝั่งแอป

        ตัด Plus Code นำหน้า และแก้คำซ้ำซ้อนแบบ 'ต.ตำบล X' → 'ต.X'
        (ยกมาจาก Odoo 14 ตรง ๆ — ที่อยู่จาก Google มารูปแบบเดิมเสมอ)
        """
        if not addr:
            return addr
        text = str(addr)
        text = re.sub(r'^\s*[A-Z0-9]{4,}\+[A-Z0-9]{2,4}\s*', '', text)
        text = re.sub(r'ต\.\s*ตำบล\s*', 'ต.', text)
        text = re.sub(r'อ\.\s*อำเภอ\s*', 'อ.', text)
        text = re.sub(r'จ\.\s*จังหวัด\s*', 'จ.', text)
        text = re.sub(r'แขวง\s*แขวง\s*', 'แขวง', text)
        text = re.sub(r'เขต\s*เขต\s*', 'เขต', text)
        return re.sub(r'\s+', ' ', text).strip()

    @staticmethod
    def _haversine_meters(lat1, lng1, lat2, lng2):
        """ระยะทางระหว่างสองพิกัดเป็นเมตร"""
        radius = 6371000.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        d_phi = math.radians(lat2 - lat1)
        d_lambda = math.radians(lng2 - lng1)
        a = (math.sin(d_phi / 2) ** 2
             + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2)
        return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    @api.model
    def _last_log_today(self, employee):
        """รายการลงเวลาล่าสุดของวันนี้ (เวลาไทย)"""
        tz = pytz.timezone(THAI_TZ)
        today = fields.Datetime.now().replace(tzinfo=pytz.utc).astimezone(tz).date()
        return self.sudo().search([
            ('employee_id', '=', employee.id),
            ('work_date', '=', today),
        ], order='checked_at desc', limit=1)

    # ------------------------------------------------------------------
    # สถานะปุ่มเช็คอินในแอป (แทน api_checkin_status1.php)
    # ------------------------------------------------------------------
    @api.model
    def api_checkin_status(self, employee_id):
        employee = self.env['employee.salary'].sudo().browse(int(employee_id))
        if not employee.exists():
            raise UserError('ไม่พบข้อมูลผู้ใช้')

        last = self._last_log_today(employee)
        last_type = last.check_type if last else False
        branch = employee.branch_id
        company = employee.company_id or self.env.company

        return {
            'firstName': employee.firstname or '',
            'lastName': employee.lastname or '',
            'canCheckIn': not last_type or last_type == 'out',
            'canCheckOut': last_type == 'in',
            'targetLat': float(branch.hr_checkin_latitude or 13.7563),
            'targetLng': float(branch.hr_checkin_longitude or 100.5018),
            'allowedMeter': (branch._hr_effective_radius(company) if branch
                             else company.hrms_checkin_default_radius or 50),
            # ส่งเป็น 0/1 ไม่ใช่ true/false — แอปเอาค่านี้ไปประกอบเป็น "ลายนิ้วมือ config"
            # แล้วเทียบกับที่เก็บไว้ในเครื่อง ถ้าชนิดข้อมูลเปลี่ยน ("0" -> "false")
            # แอปจะถือว่า config เปลี่ยนแล้วบังคับพนักงานทุกคนล็อกอินใหม่ทั้งบริษัท
            'allowOffsiteTime': int(bool(
                employee.allow_offsite_time
                or (branch.hr_allow_offsite_checkin if branch else False))),
            'employeeStatus': employee.status or 'active',
            'branch': branch.name or '',
        }

    # ------------------------------------------------------------------
    # บันทึกลงเวลา (แทน api_checkin_save_test1.php)
    # ------------------------------------------------------------------
    @api.model
    def api_save_checkin(self, employee_id, check_type, latitude, longitude,
                         accuracy=None, address=None):
        """บันทึกการลงเวลาจากแอป — คืน dict {status, message}

        ตรรกะกันซ้ำเป็นชุดเดียวกับ PHP เดิม แต่บังคับที่ระดับฐานข้อมูลด้วย
        (unique constraint) จึงกัน race condition ได้โดยไม่ต้อง SELECT FOR UPDATE
        """
        if check_type not in ('in', 'out'):
            raise UserError('ประเภทการลงเวลาไม่ถูกต้อง')
        if not latitude or not longitude:
            raise UserError('ข้อมูลไม่ครบถ้วน (ต้องมีพิกัด GPS)')

        employee = self.env['employee.salary'].sudo().browse(int(employee_id))
        if not employee.exists():
            raise UserError('ไม่พบผู้ใช้ในระบบ')
        if employee.status != 'active':
            raise UserError('บัญชีพนักงานนี้ไม่อยู่ในสถานะใช้งาน')

        now = fields.Datetime.now()

        # 1) กันกดซ้ำภายใน 30 นาที
        recent = self.sudo().search([
            ('employee_id', '=', employee.id),
            ('check_type', '=', check_type),
            ('checked_at', '>=', now - timedelta(minutes=DUPLICATE_CHECK_MINUTES)),
        ], order='checked_at desc', limit=1)
        if recent:
            tz = pytz.timezone(THAI_TZ)
            local = pytz.utc.localize(recent.checked_at).astimezone(tz)
            raise UserError(
                'คุณลงเวลา%sไปแล้วเมื่อ %s น. กรุณารออีก %d นาที'
                % ('เข้างาน' if check_type == 'in' else 'ออกงาน',
                   local.strftime('%H:%M'), DUPLICATE_CHECK_MINUTES))

        # 2) ต้องสลับ เข้า → ออก → เข้า
        last = self._last_log_today(employee)
        if check_type == 'in' and last and last.check_type == 'in':
            raise UserError('คุณลงเวลาเข้างานไปแล้ว กรุณาลงเวลาออกก่อน')
        if check_type == 'out' and (not last or last.check_type == 'out'):
            raise UserError('ยังไม่พบการลงเวลาเข้างานของวันนี้')

        # 3) คำนวณระยะจากสาขา — บันทึกไว้ให้ฝ่ายบุคคลตรวจย้อนหลัง
        distance = 0.0
        is_offsite = False
        branch = employee.branch_id
        if branch and branch.hr_checkin_latitude and branch.hr_checkin_longitude:
            try:
                distance = self._haversine_meters(
                    float(latitude), float(longitude),
                    float(branch.hr_checkin_latitude),
                    float(branch.hr_checkin_longitude))
                allowed = branch._hr_effective_radius(employee.company_id)
                is_offsite = distance > allowed
            except (TypeError, ValueError):
                _logger.warning(
                    'พิกัดไม่ถูกต้อง emp=%s lat=%s lng=%s',
                    employee.employee_code, latitude, longitude)

        record = self.sudo().create({
            'employee_id': employee.id,
            'check_type': check_type,
            'checked_at': now,
            'latitude': str(latitude),
            'longitude': str(longitude),
            'accuracy': float(accuracy) if accuracy not in (None, '', False) else 0.0,
            'address': self._clean_address(address),
            'distance_from_branch': distance,
            'is_offsite': is_offsite,
            'source': 'app',
        })
        return {
            'id': record.id,
            'message': 'ลงเวลาเข้าเรียบร้อย' if check_type == 'in'
            else 'ลงเวลาออกเรียบร้อย',
            'is_offsite': is_offsite,
            'distance_from_branch': round(distance, 2),
        }

    # ------------------------------------------------------------------
    # ประวัติการลงเวลา (แทน get_checkin_history.php / ส่วนหนึ่งของ menu_data)
    # ------------------------------------------------------------------
    def _as_history_dict(self):
        """รูปแบบเดียวกับที่ PHP ส่งให้แอป"""
        self.ensure_one()
        tz = pytz.timezone(THAI_TZ)
        local = pytz.utc.localize(self.checked_at).astimezone(tz)
        return {
            'id': self.id,
            'full_datetime': local.strftime('%Y-%m-%d %H:%M:%S'),
            'work_date': local.strftime('%Y-%m-%d'),
            'work_time': local.strftime('%H:%M'),
            'check_type': self.check_type,
        }

    @api.model
    def api_get_history(self, employee_id, month=None, year=None):
        """ประวัติลงเวลาของเดือน/ปีที่เลือก (ค่าเริ่มต้น = เดือนปัจจุบัน)"""
        import calendar
        today = fields.Date.context_today(self)
        month = int(month) if month else today.month
        year = int(year) if year else today.year
        if not 1 <= month <= 12:
            month = today.month
        if not 2020 <= year <= 2100:
            year = today.year

        last_day = calendar.monthrange(year, month)[1]
        logs = self.sudo().search([
            ('employee_id', '=', int(employee_id)),
            ('work_date', '>=', fields.Date.to_date('%04d-%02d-01' % (year, month))),
            ('work_date', '<=', fields.Date.to_date(
                '%04d-%02d-%02d' % (year, month, last_day))),
        ], order='checked_at desc')
        return {
            'month': month,
            'year': year,
            'total_records': len(logs),
            'checkin_history': [log._as_history_dict() for log in logs],
        }

    @api.model
    def api_get_recent_history(self, employee_id, days=3):
        """รายการลงเวลาของ N วันล่าสุดที่ "มีข้อมูล" (ไม่ใช่ N วันปฏิทินล่าสุด)

        ตรงกับพฤติกรรมของ menu_data_test.php ที่ดึง 100 แถวล่าสุดมาจัดกลุ่มตามวัน
        แล้วเอาแค่ 3 วันที่มีข้อมูลจริง — วันหยุดยาวจึงยังเห็นประวัติได้
        """
        logs = self.sudo().search(
            [('employee_id', '=', int(employee_id))],
            order='checked_at desc', limit=100)
        wanted_dates = sorted({log.work_date for log in logs if log.work_date})[-days:]
        return [
            log._as_history_dict()
            for log in logs
            if log.work_date in wanted_dates
        ]
