# -*- coding: utf-8 -*-
"""เครื่องคำนวณ สาย / ขาด / ลา / OT จากข้อมูลลงเวลา

พอร์ตตรงจาก ``calculate_lateness.php`` + ``get_ot_data.php`` มาเป็น Python
เพราะข้อมูลลงเวลาย้ายมาอยู่ใน Odoo แล้ว ไม่ต้องยิงข้าม MySQL อีก

กฎเดิมถูกเก็บไว้ครบ แต่ "ตัวเลขทุกตัว" อ่านจาก ``payroll.policy`` ของบริษัทนั้น
เพื่อให้บริษัทที่เช่าระบบไปตั้งสูตรของตัวเองได้ (ค่าเริ่มต้น = ของ NPD เดิม):

  * หักช่วงพักเที่ยงออกจากเวลาสาย/ออกก่อน/เวลาลา  → policy.lunch_*
  * ตัดช่วงที่ทับกับใบลาก่อนแล้วค่อยปัดเศษ         → policy.exclude_leave_overlap
    (ถ้าปัดก่อน เศษนาทีจากการปัดจะกลายเป็นยอดหักทั้งที่อยู่ในช่วงลา)
  * สายปัดลง / ออกก่อนปัดขึ้น                      → policy.late_rounding / early_rounding
  * วันแรกที่เริ่มงานไม่นับสาย                     → policy.skip_late_on_first_workday
  * ข้ามวันก่อนเริ่มงาน วันหลังลาออก และวันที่ยังมาไม่ถึง (กฎตายตัว)

ประเภทการลา/ประเภทการเพิ่มเวลา อ่านจากข้อมูลหลัก (``is_paid`` /
``requires_attachment`` / ``counts_as_attendance`` / ``ot_kind``)
แทนการเทียบชื่อภาษาไทยแบบ hardcode เหมือน PHP เดิม
"""
import logging
import math
from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

import pytz

from odoo import models, fields, api

_logger = logging.getLogger(__name__)

THAI_TZ = pytz.timezone('Asia/Bangkok')


def float_to_time(value):
    """7.5 → time(7, 30) — ฟิลด์กะใน hr.work.schedule เก็บเป็น Float ชั่วโมง"""
    value = float(value or 0.0)
    hours = int(value)
    minutes = int(round((value - hours) * 60))
    if minutes >= 60:
        hours, minutes = hours + 1, minutes - 60
    return time(min(hours, 23), min(minutes, 59))


def overlap_minutes(a_start, a_end, b_start, b_end):
    """นาทีที่ช่วง A ทับกับช่วง B"""
    if not all([a_start, a_end, b_start, b_end]):
        return 0.0
    start, end = max(a_start, b_start), min(a_end, b_end)
    return (end - start).total_seconds() / 60.0 if start < end else 0.0


def round_half_up(value):
    """ปัดครึ่งขึ้น — ตรงกับกฎ สปส. และพฤติกรรมของ PHP เดิม

    Python ``round()`` ใช้ banker's rounding (2.5 → 2) ซึ่งทำให้ยอดเพี้ยน
    """
    return float(Decimal(str(value or 0.0)).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP))


def apply_rounding(minutes, mode):
    """ปัดเศษนาทีตามโหมดที่นโยบายกำหนด"""
    minutes = round(minutes, 6)
    if minutes <= 0:
        return 0.0
    if mode == 'floor':
        return float(math.floor(minutes))
    if mode == 'ceil':
        return float(math.ceil(minutes))
    return minutes


class PayrollAttendanceEngine(models.AbstractModel):
    """AbstractModel เพื่อให้เรียกใช้/ทดสอบได้โดยไม่ต้องมีสลิปจริง"""
    _name = 'payroll.attendance.engine'
    _description = 'เครื่องคำนวณสาย/ขาด/ลา/OT'

    # ==================================================================
    # Helper
    # ==================================================================
    @api.model
    def _to_thai_naive(self, utc_dt):
        """Datetime ที่ Odoo เก็บเป็น UTC → เวลาไทยแบบไม่มี tzinfo"""
        if not utc_dt:
            return None
        return pytz.utc.localize(utc_dt).astimezone(THAI_TZ).replace(tzinfo=None)

    @api.model
    def _lunch_overlap(self, policy, start_dt, end_dt):
        if not policy.lunch_enabled or not start_dt or not end_dt or end_dt <= start_dt:
            return 0.0
        day = start_dt.date()
        return overlap_minutes(
            start_dt, end_dt,
            datetime.combine(day, float_to_time(policy.lunch_start)),
            datetime.combine(day, float_to_time(policy.lunch_end)))

    @api.model
    def _shift_bounds(self, schedule, work_date):
        """(is_workday, shift_start_dt, shift_end_dt) ของวันนั้นตามตารางงาน"""
        if not schedule:
            return False, None, None
        is_workday, start_f, end_f = schedule._shift_for_weekday(work_date.isoweekday())
        if not is_workday:
            return False, None, None
        return (True,
                datetime.combine(work_date, float_to_time(start_f)),
                datetime.combine(work_date, float_to_time(end_f)))

    @api.model
    def _average_shift_hours(self, policy, schedule):
        """ชั่วโมงทำงานเฉลี่ยต่อวันจากตารางงาน (หักพักเที่ยงถ้ากะยาวถึงเกณฑ์)"""
        if not schedule or not policy.use_schedule_hours_for_deduction:
            return policy.ot_hours_per_day or 8.0
        from odoo.addons.npd_hrms_base.models.hr_work_schedule import DAYS
        total_hours, workdays = 0.0, 0
        for code, _label, _iso in DAYS:
            if not schedule[f'work_{code}']:
                continue
            hours = schedule[f'{code}_shift_end'] - schedule[f'{code}_shift_start']
            if hours <= 0:
                continue
            if policy.lunch_enabled and hours >= (policy.lunch_min_shift_hours or 8.0):
                hours -= (policy.lunch_end - policy.lunch_start) or 1.0
            total_hours += hours
            workdays += 1
        return (total_hours / workdays) if workdays else (policy.ot_hours_per_day or 8.0)

    @api.model
    def _rates(self, policy, base_salary, schedule):
        """(ค่าจ้างต่อวัน, ต่อชั่วโมง, ต่อนาที) สำหรับคิดยอดหัก"""
        per_day = (base_salary or 0.0) / (policy.salary_days_divisor or 30.0)
        avg_hours = self._average_shift_hours(policy, schedule) or 8.0
        per_hour = per_day / avg_hours if avg_hours else 0.0
        return per_day, per_hour, per_hour / 60.0

    @api.model
    def _parse_time(self, value, default=None):
        """'08:30' หรือ '08:30:00' → time (ฟิลด์เวลาเก็บเป็น Char)"""
        if not value:
            return default
        text = str(value).strip()
        for fmt in ('%H:%M:%S', '%H:%M'):
            try:
                return datetime.strptime(text, fmt).time()
            except ValueError:
                continue
        return default

    # ==================================================================
    # สาย / ขาด / ลา
    # ==================================================================
    @api.model
    def compute_attendance_deductions(self, employee, date_from, date_to, policy,
                                      grace_period=15, base_salary=None,
                                      holidays=None):
        """คำนวณสาย/ออกก่อนเวลา/ขาดงาน/หักลา ในช่วง [date_from, date_to]"""
        schedule = self.env['hr.work.schedule'].sudo().search(
            [('employee_id', '=', employee.id)], limit=1)
        result = {
            'late_minutes': 0.0, 'early_minutes': 0.0, 'missed_days': 0,
            'total_lateness_minutes': 0.0, 'working_days': 0, 'holiday_days': 0,
            'present_days': 0, 'leave_deduction_total': 0.0,
            'late_log': [], 'early_log': [], 'leave_log': [], 'missed_log': [],
            'has_schedule': bool(schedule),
            'late_deduction': 0.0, 'early_deduction': 0.0,
            'absent_deduction': 0.0, 'absent_deduction_total': 0.0,
            'rate_per_day': 0.0, 'rate_per_hour': 0.0, 'rate_per_minute': 0.0,
        }
        if not schedule:
            _logger.warning('[LATENESS] ไม่พบตารางงานของ %s', employee.employee_code)
            return result

        base_salary = base_salary if base_salary is not None else employee.salary
        per_day, per_hour, per_minute = self._rates(policy, base_salary, schedule)

        if holidays is None:
            holidays = self.env['payroll.holiday'].sudo().get_holiday_dates(
                date_to.year, (employee.company_id or self.env.company).id)
        holidays = set(holidays or ())

        today = fields.Date.context_today(self)
        start_work, resign_date = employee.start_date, employee.resign_date

        # สูตรคิดสายที่ตั้งไว้ — โหลดครั้งเดียวแล้วเลือกรายวันในหน่วยความจำ
        # (รอบหนึ่งวนหลายสิบวัน ถ้าค้นใหม่ทุกวันจะยิง search ซ้ำเป็นร้อยครั้ง)
        lateness_rules = self.env['payroll.lateness.rule'].rules_for_engine(
            employee.branch_id, employee.company_id or self.env.company)

        leaves = self.env['hr.attendance.branch.leave'].sudo().search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'อนุมัติ'),
            ('leave_start_date', '<=', date_to),
            ('leave_end_date', '>=', date_from),
        ])
        attendances = self.env['hr.attendance.branch'].sudo().search([
            ('employee_id', '=', employee.id),
            ('work_date', '>=', date_from), ('work_date', '<=', date_to),
        ], order='checked_at asc')
        manual_present = self.env['hr.manual.time.log'].sudo().search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'อนุมัติ'),
            ('reason_type_id.counts_as_attendance', '=', True),
            ('work_date', '>=', date_from), ('work_date', '<=', date_to),
        ])

        attendance_by_day, manual_by_day = {}, {}
        for log in attendances:
            attendance_by_day.setdefault(log.work_date, []).append(log)
        for log in manual_present:
            manual_by_day.setdefault(log.work_date, []).append(log)

        cursor = date_from
        while cursor <= date_to:
            day, cursor = cursor, cursor + timedelta(days=1)

            # ยังมาไม่ถึง / ก่อนเริ่มงาน / หลังลาออก → ไม่นับ
            if day >= today:
                continue
            if start_work and day < start_work:
                continue
            if resign_date and day > resign_date:
                continue

            is_workday, shift_start, shift_end = self._shift_bounds(schedule, day)
            if not is_workday:
                continue
            if day in holidays:
                result['holiday_days'] += 1
                continue
            result['working_days'] += 1

            # ---------- ใบลาของวันนี้ ----------
            day_leaves = leaves.filtered(
                lambda lv: lv.leave_start_date <= day <= lv.leave_end_date)
            leave_intervals, fully_on_leave, counted_present = [], False, False

            for leave in day_leaves:
                leave_start = datetime.combine(
                    day, self._parse_time(leave.start_time, time(8, 0)))
                leave_end = datetime.combine(
                    day, self._parse_time(leave.end_time, time(17, 0)))
                leave_intervals.append((leave_start, leave_end))

                leave_type = leave.leave_type_id
                # ได้รับค่าจ้าง = ถือว่ามาทำงาน ไม่หัก
                # ไม่ได้รับค่าจ้าง = หักตามเวลาที่ลา
                # ประเภทที่ต้องแนบเอกสารแต่ไม่แนบ = หัก แม้จะเป็นประเภทได้รับค่าจ้าง
                should_deduct = not leave_type.is_paid
                if leave_type.is_paid and leave_type.requires_attachment \
                        and not leave.attachment:
                    should_deduct = True

                if should_deduct:
                    amount = self._leave_deduction(
                        policy, per_day, shift_start, shift_end,
                        leave_start, leave_end)
                    if amount > 0:
                        result['leave_deduction_total'] += amount
                        result['leave_log'].append({
                            'date': day.isoformat(),
                            'type': leave_type.name or '',
                            'deduction': amount,
                            'start': leave_start.strftime('%H:%M'),
                            'end': leave_end.strftime('%H:%M'),
                        })
                else:
                    counted_present = True

                if leave_start <= shift_start and leave_end >= shift_end:
                    fully_on_leave = True

            if fully_on_leave:
                if counted_present:
                    result['present_days'] += 1
                continue

            # ---------- เวลาเข้า-ออก ----------
            checkin = checkout = None
            logs = attendance_by_day.get(day) or []
            ins = [log for log in logs if log.check_type == 'in']
            outs = [log for log in logs if log.check_type == 'out']
            if ins:
                checkin = self._to_thai_naive(ins[0].checked_at)
            if outs:
                checkout = self._to_thai_naive(outs[-1].checked_at)

            # คำขอเพิ่มเวลาที่ "ถือว่ามาทำงานจริง" → ทับค่าจากการลงเวลา
            manual_logs = manual_by_day.get(day) or []
            if manual_logs:
                starts = [t for t in (self._parse_time(m.checkin_time)
                                      for m in manual_logs) if t]
                ends = [t for t in (self._parse_time(m.checkout_time)
                                    for m in manual_logs) if t]
                if starts:
                    checkin = datetime.combine(day, min(starts))
                if ends:
                    checkout = datetime.combine(day, max(ends))

            if not (checkin and checkout):
                # ไม่มีเวลาเข้า-ออกครบ — วันที่มีใบลาบางช่วงไม่นับเป็นขาด
                if not day_leaves:
                    result['missed_log'].append(day.isoformat())
                continue

            result['present_days'] += 1

            # ---------- เข้าสาย ----------
            if checkin > shift_start:
                raw = (checkin - shift_start).total_seconds() / 60.0
                raw -= self._lunch_overlap(policy, shift_start, checkin)
                if policy.exclude_leave_overlap:
                    for iv_start, iv_end in leave_intervals:
                        raw -= overlap_minutes(shift_start, checkin, iv_start, iv_end)
                late_min = apply_rounding(max(0.0, raw), policy.late_rounding)
                is_first_workday = bool(start_work and day == start_work)
                skip = is_first_workday and policy.skip_late_on_first_workday

                # สูตรของวันนี้ — ยังไม่มีสูตรครอบคลุมก็ใช้ค่าผ่อนผันเดิมของสลิป
                # จึงไม่กระทบยอดของวันก่อนวันเริ่มใช้สูตรใหม่
                day_grace, deadline_hour = self.env[
                    'payroll.lateness.rule'].resolve_for_day(
                        lateness_rules, day, grace_period)
                if deadline_hour is not None:
                    # แบบกำหนดเวลาเข้างานล่าสุด: เลยเวลานั้นถือว่าสายทันที
                    # แต่ยังนับนาทีจากเวลาเข้ากะเหมือนเดิม เพื่อให้ยอดหักคิดฐานเดียวกัน
                    deadline_at = datetime.combine(day, time(0)) + timedelta(
                        hours=deadline_hour)
                    is_late = checkin > deadline_at
                else:
                    is_late = late_min > day_grace

                if not skip and is_late and late_min > 0:
                    result['late_minutes'] += late_min
                    result['total_lateness_minutes'] += late_min
                    result['late_log'].append({
                        'date': day.isoformat(), 'minutes': late_min,
                        'checkin': checkin.strftime('%H:%M'),
                        'shift_start': shift_start.strftime('%H:%M'),
                    })

            # ---------- ออกก่อนเวลา ----------
            if checkout < shift_end:
                raw = (shift_end - checkout).total_seconds() / 60.0
                raw -= self._lunch_overlap(policy, checkout, shift_end)
                if policy.exclude_leave_overlap:
                    for iv_start, iv_end in leave_intervals:
                        raw -= overlap_minutes(checkout, shift_end, iv_start, iv_end)
                early_min = apply_rounding(max(0.0, raw), policy.early_rounding)
                if early_min > 0:
                    result['early_minutes'] += early_min
                    result['total_lateness_minutes'] += early_min
                    result['early_log'].append({
                        'date': day.isoformat(), 'minutes': early_min,
                        'checkout': checkout.strftime('%H:%M'),
                        'shift_end': shift_end.strftime('%H:%M'),
                    })

        result['missed_days'] = len(result['missed_log'])
        result['leave_deduction_total'] = round(result['leave_deduction_total'], 2)
        result['late_deduction'] = round_half_up(result['late_minutes'] * per_minute)
        result['early_deduction'] = round_half_up(result['early_minutes'] * per_minute)
        result['absent_deduction'] = round_half_up(result['missed_days'] * per_day)
        result['absent_deduction_total'] = round_half_up(
            result['absent_deduction']
            + (result['early_deduction'] if policy.absent_includes_early else 0.0))
        result['rate_per_day'] = per_day
        result['rate_per_hour'] = per_hour
        result['rate_per_minute'] = per_minute
        return result

    @api.model
    def _leave_deduction(self, policy, per_day, shift_start, shift_end,
                         leave_start, leave_end):
        """เงินหักจากการลาหนึ่งใบ

        ลาคลุมทั้งกะ → หักเต็มวัน (ถ้านโยบายเปิดไว้)
        ลาบางช่วง → คิดตามนาทีจริง หักพักเที่ยงออก ไม่ปัดขึ้นเป็นชั่วโมง
        """
        working_hours = (shift_end - shift_start).total_seconds() / 3600.0
        working_hours -= self._lunch_overlap(policy, shift_start, shift_end) / 60.0
        if working_hours <= 0:
            working_hours = policy.ot_hours_per_day or 8.0

        if policy.leave_full_shift_as_full_day \
                and leave_start <= shift_start and leave_end >= shift_end:
            return round(per_day, 2)

        minutes = (leave_end - leave_start).total_seconds() / 60.0
        minutes -= self._lunch_overlap(policy, leave_start, leave_end)
        minutes = max(0.0, minutes)
        minute_rate = (per_day / working_hours) / 60.0
        return round(minute_rate * minutes, 2)

    # ==================================================================
    # วันที่ "ไม่ได้สแกนเข้างาน" — ใช้ออกใบเตือน (คนละตัวกับยอดหักขาดงาน)
    # ==================================================================
    @api.model
    def missed_no_checkin_days(self, employee, date_from, date_to,
                               include_pending_excuse=True, holidays=None):
        """วันทำงานที่พนักงานไม่ได้สแกนเข้างานเอง ในช่วง [date_from, date_to]

        แยกจาก ``missed_log`` ของการคิดเงินโดยตั้งใจ เพราะเกณฑ์ต่างกัน

        * ลืมกดเข้างาน (มาขอเพิ่มเวลาประเภท "ลืมลงเวลา" ทีหลัง) → **นับ**
          เพราะนี่คือสิ่งที่ใบเตือนเตือนโดยตรง จะอนุมัติแล้วหรือยังก็ตาม
        * เข้างานแล้วลืมกดออกงาน                                → ไม่นับ
        * ทำงานนอกสถานที่ / ระบบมีปัญหา                          → ไม่นับ
        * มีใบลาอนุมัติแล้วคาบวันนั้น                            → ไม่นับ

        ยอดหักเงินยังใช้ ``missed_log`` ตัวเดิม ปรับเกณฑ์ใบเตือนได้
        โดยไม่กระทบสลิปเงินเดือน

        :param include_pending_excuse: ยกประโยชน์ให้พนักงานสำหรับคำขอประเภท
            "ทำงานนอกสถานที่"/"ระบบมีปัญหา" ที่ยังไม่มีใครกดอนุมัติ
        :return: list ของ ``date`` เรียงจากน้อยไปมาก
                 หรือ ``None`` ถ้าไม่มีตารางกะ (= ข้ามคนนี้ ไม่เดา)
        """
        schedule = self.env['hr.work.schedule'].sudo().search(
            [('employee_id', '=', employee.id)], limit=1)
        if not schedule:
            return None

        # รอบหนึ่งคาบ 2 เดือน และคาบข้ามปีได้ (รอบ ม.ค. = 25/12 ถึง 24/01)
        # ถ้าดึงวันหยุดปีเดียว วันหยุดฝั่ง ธ.ค. จะหายแล้วนับเป็นวันทำงานหมด
        if holidays is None:
            Holiday = self.env['payroll.holiday'].sudo()
            company_id = (employee.company_id or self.env.company).id
            holidays = set()
            for year in {date_from.year, date_to.year}:
                holidays |= Holiday.get_holiday_dates(year, company_id)
        holidays = set(holidays or ())

        today = fields.Date.context_today(self)
        start_work, resign_date = employee.start_date, employee.resign_date

        leaves = self.env['hr.attendance.branch.leave'].sudo().search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'อนุมัติ'),
            ('leave_start_date', '<=', date_to),
            ('leave_end_date', '>=', date_from),
        ])
        checkins = self.env['hr.attendance.branch'].sudo().search([
            ('employee_id', '=', employee.id),
            ('check_type', '=', 'in'),
            ('work_date', '>=', date_from), ('work_date', '<=', date_to),
        ])
        checkin_days = set(checkins.mapped('work_date'))

        # คำขอเพิ่มเวลาที่ "มีเหตุยกเว้น" — ตัดประเภทลืมลงเวลาออก
        # เทียบด้วย code ไม่ใช่ชื่อไทย บริษัทที่เช่าระบบเปลี่ยนชื่อได้โดยไม่พัง
        excuse_states = ['อนุมัติ']
        if include_pending_excuse:
            excuse_states.append('รออนุมัติ')
        excuses = self.env['hr.manual.time.log'].sudo().search([
            ('employee_id', '=', employee.id),
            ('state', 'in', excuse_states),
            ('reason_type_id.counts_as_attendance', '=', True),
            ('reason_type_id.code', '!=', 'forgot_checkin'),
            ('work_date', '>=', date_from), ('work_date', '<=', date_to),
        ])
        excuse_days = set(excuses.mapped('work_date'))

        missed, cursor = [], date_from
        while cursor <= date_to:
            day, cursor = cursor, cursor + timedelta(days=1)

            if day >= today:
                continue
            if start_work and day < start_work:
                continue
            if resign_date and day > resign_date:
                continue
            is_workday = self._shift_bounds(schedule, day)[0]
            if not is_workday or day in holidays:
                continue
            if day in checkin_days or day in excuse_days:
                continue
            if leaves.filtered(
                    lambda lv: lv.leave_start_date <= day <= lv.leave_end_date):
                continue
            missed.append(day)
        return missed

    # ==================================================================
    # OT
    # ==================================================================
    @api.model
    def compute_overtime(self, employee, date_from, date_to, policy,
                         base_salary=None, rounding='round_down', holidays=None):
        """คำนวณ OT จากคำขอเพิ่มเวลาที่อนุมัติแล้ว

        แหล่งข้อมูลเดียวกับ get_ot_data.php เดิม (manual_time_logs) แต่แยกอัตราด้วย
        ``ot_kind`` บนข้อมูลหลัก แทนการเทียบชื่อภาษาไทย
        """
        schedule = self.env['hr.work.schedule'].sudo().search(
            [('employee_id', '=', employee.id)], limit=1)
        base_salary = base_salary if base_salary is not None else employee.salary

        # อัตราต่อชั่วโมงของ OT ใช้ฐานชั่วโมงต่อวันตามนโยบาย (ไม่ใช่กะจริง)
        hourly_rate = round_half_up(
            (base_salary or 0.0)
            / (policy.salary_days_divisor or 30.0)
            / (policy.ot_hours_per_day or 8.0))

        logs = self.env['hr.manual.time.log'].sudo().search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'อนุมัติ'),
            ('reason_type_id.is_overtime', '=', True),
            ('work_date', '>=', date_from), ('work_date', '<=', date_to),
        ], order='work_date asc')

        lines = []
        totals = {'weekday': 0.0, 'holiday': 0.0, 'sunday': 0.0}
        seen_holiday_dates = set()

        for log in logs:
            start_t = self._parse_time(log.checkin_time)
            end_t = self._parse_time(log.checkout_time)
            if not start_t or not end_t:
                continue
            start_dt = datetime.combine(log.work_date, start_t)
            end_dt = datetime.combine(log.work_date, end_t)
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)

            if (log.reason_type_id.ot_kind or 'request') == 'holiday':
                # ทำงานวันหยุด — อัตราวันหยุดเสมอ ไม่ว่าจะเป็นวันไหน
                if log.work_date in seen_holiday_dates:
                    continue
                seen_holiday_dates.add(log.work_date)
                hours = (end_dt - start_dt).total_seconds() / 3600.0
                hours -= self._lunch_overlap(policy, start_dt, end_dt) / 60.0
                hours = max(0.0, hours)
                ot_type, multiplier = 'holiday', policy.ot_rate_holiday or 2.0
            else:
                hours = (end_dt - start_dt).total_seconds() / 3600.0
                if rounding == 'round_down':
                    minimum = policy.ot_min_hours or 1.0
                    hours = 0.0 if hours < minimum else minimum + max(0.0, hours - minimum)
                is_workday, shift_start, shift_end = self._shift_bounds(
                    schedule, log.work_date)
                if self._is_outside_shift(start_dt, end_dt, is_workday,
                                          shift_start, shift_end):
                    ot_type, multiplier = 'weekday', policy.ot_rate_weekday or 1.5
                    if is_workday and shift_start and shift_end:
                        hours = self._hours_outside_shift(
                            start_dt, end_dt, shift_start, shift_end)
                else:
                    ot_type, multiplier = 'sunday', policy.ot_rate_sunday or 1.0
                    hours -= self._lunch_overlap(policy, start_dt, end_dt) / 60.0
                    hours = max(0.0, hours)

            amount = hours * hourly_rate * multiplier
            totals[ot_type] += amount
            lines.append({
                'date': log.work_date, 'manual_log_id': log.id,
                'start_time_text': log.checkin_time or '',
                'end_time_text': log.checkout_time or '',
                'ot_hours': hours, 'ot_amount': amount,
                'ot_type': ot_type, 'rate': multiplier,
            })

        return {
            'lines': lines,
            'total_weekday': totals['weekday'],
            'total_holiday': totals['holiday'],
            'total_sunday': totals['sunday'],
            'total': sum(totals.values()),
            'hourly_rate': hourly_rate,
        }

    @api.model
    def _is_outside_shift(self, start_dt, end_dt, is_workday, shift_start, shift_end):
        """OT อยู่นอกกะไหม — ไม่ใช่วันทำงาน = อยู่ในวันหยุดประจำสัปดาห์"""
        if not is_workday or not shift_start or not shift_end:
            return False
        return start_dt < shift_start or end_dt > shift_end

    @api.model
    def _hours_outside_shift(self, start_dt, end_dt, shift_start, shift_end):
        """ชั่วโมงเฉพาะส่วนที่อยู่นอกกะ (ก่อนเข้ากะ + หลังเลิกกะ)"""
        before = max(0.0, (min(end_dt, shift_start) - start_dt).total_seconds() / 3600.0)
        after = max(0.0, (end_dt - max(start_dt, shift_end)).total_seconds() / 3600.0)
        return max(0.0, before + after)
