# -*- coding: utf-8 -*-
"""ล็อกไม่ให้ยกเลิกเอกสารของเดือนก่อนหน้า (พอร์ตจาก Odoo 14)

กติกา
    วันตัดงวด (cutoff) ถูกตั้งโดย Scheduled Action ทุกวันที่ 15 (เวลาประเทศไทย)
    = วันที่ 1 ของเดือนนั้น
    เอกสารที่ "วันที่เอกสาร < วันตัดงวด" -> ไม่สามารถยกเลิกได้ โปรดติดต่อฝ่ายการเงิน

    ตัวอย่าง วันนี้ 17/09/2026 (cron รันไปแล้วเมื่อ 15/09) วันตัดงวด = 01/09/2026
    ใบแจ้งหนี้ลงวันที่ 14/07/2026 หรือ 31/08/2026 -> ยกเลิกไม่ได้
    ใบแจ้งหนี้ลงวันที่ 01/09/2026 เป็นต้นไป    -> ยกเลิกได้

ทำไมต้องคิดเวลาประเทศไทยเอง
    Odoo เก็บเวลาใน DB เป็น UTC (ช้ากว่าไทย 7 ชม.) วันที่จึงเพี้ยนกันได้ช่วง 00:00-07:00
    ที่นี่จึงอ่านเวลา UTC แบบระบุ timezone แล้วแปลงเป็น Asia/Bangkok ทุกครั้ง
"""
from datetime import datetime

import pytz
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

THAI_TZ = pytz.timezone('Asia/Bangkok')
LOCK_MESSAGE = 'ไม่สามารถยกเลิกได้ โปรดติดต่อฝ่ายการเงิน'
BYPASS_GROUP = 'npd_cancel_period_lock.group_cancel_lock_bypass'
PARAM_CUTOFF = 'npd_cancel_period_lock.cutoff_date'
PARAM_LOCK_DAY = 'npd_cancel_period_lock.lock_day'
DEFAULT_LOCK_DAY = 15


def thai_now():
    """เวลาปัจจุบันของประเทศไทย ไม่ขึ้นกับ timezone ของเครื่องหรือฐานข้อมูล"""
    return datetime.now(pytz.utc).astimezone(THAI_TZ)


def get_lock_day(env):
    """วันที่ของเดือนที่ล็อกเดือนก่อนหน้า (ค่าเริ่มต้น 15) ปรับได้ใน System Parameters"""
    value = env['ir.config_parameter'].sudo().get_param(PARAM_LOCK_DAY)
    try:
        day = int(value) if value else DEFAULT_LOCK_DAY
    except ValueError:
        day = DEFAULT_LOCK_DAY
    return min(max(day, 1), 28)


def compute_cutoff(today, lock_day=DEFAULT_LOCK_DAY):
    """วันตัดงวด: ถึงวันล็อกแล้ว = วันที่ 1 เดือนนี้, ยังไม่ถึง = วันที่ 1 เดือนก่อน"""
    cutoff = today.replace(day=1)
    if today.day < lock_day:
        cutoff -= relativedelta(months=1)
    return cutoff


def next_cron_call(now_th, lock_day=DEFAULT_LOCK_DAY):
    """รอบถัดไปของ cron (วันล็อก 00:05 น. เวลาไทย) คืนค่าเป็น UTC แบบไม่มี tz ตามที่ Odoo เก็บ"""
    candidate = THAI_TZ.localize(datetime(now_th.year, now_th.month, lock_day, 0, 5))
    if candidate <= now_th:
        candidate = THAI_TZ.localize(candidate.replace(tzinfo=None) + relativedelta(months=1))
    return candidate.astimezone(pytz.utc).replace(tzinfo=None)


class CancelLockMixin(models.AbstractModel):
    _name = 'npd.cancel.lock.mixin'
    _description = 'NPD Cancel Period Lock Mixin'

    # กำหนดในโมเดลลูก: ฟิลด์วันที่ที่ใช้ตัดสิน, ชื่อที่จะขึ้นในข้อความเตือน,
    # และสถานะที่ถือว่ายกเลิกไปแล้ว (Odoo 18: ใบแจ้งหนี้ = cancel, ใบรับชำระ = canceled/rejected)
    _cancel_lock_date_field = None
    _cancel_lock_date_label = None
    _cancel_lock_done_states = ('cancel',)

    cancel_lock_state = fields.Selection(
        [('unlocked', 'ยกเลิกได้'), ('locked', LOCK_MESSAGE)],
        string='สถานะการยกเลิก',
        compute='_compute_cancel_lock_state',
        store=True,
        index=True,
        readonly=True,
        copy=False,
        help='เอกสารของเดือนก่อนหน้าจะยกเลิก / รีเซ็ตเป็นแบบร่างไม่ได้ '
             'หลังวันที่ 15 ของเดือน (อัปเดตโดย Scheduled Action) '
             'ยกเว้นผู้ใช้ที่มีสิทธิ์ฝ่ายการเงิน',
    )

    # ------------------------------------------------------------------
    # ส่วนที่โมเดลลูกต้องกำหนด
    # ------------------------------------------------------------------
    @api.model
    def _cancel_lock_scope_domain(self):
        raise NotImplementedError()

    def _cancel_lock_in_scope(self):
        raise NotImplementedError()

    # ------------------------------------------------------------------
    @api.model
    def _cancel_lock_cutoff(self):
        value = self.env['ir.config_parameter'].sudo().get_param(PARAM_CUTOFF)
        return fields.Date.to_date(value) if value else False

    def _cancel_lock_is_locked(self, cutoff):
        self.ensure_one()
        doc_date = self[self._cancel_lock_date_field]
        return bool(
            cutoff and doc_date and self.state not in self._cancel_lock_done_states
            and self._cancel_lock_in_scope() and doc_date < cutoff
        )

    def _compute_cancel_lock_state(self):
        cutoff = self._cancel_lock_cutoff()
        for rec in self:
            if (not rec._cancel_lock_in_scope() or rec.state in rec._cancel_lock_done_states
                    or not rec[rec._cancel_lock_date_field]):
                rec.cancel_lock_state = False
            elif rec._cancel_lock_is_locked(cutoff):
                rec.cancel_lock_state = 'locked'
            else:
                rec.cancel_lock_state = 'unlocked'

    def _check_cancel_lock(self):
        """เรียกก่อนยกเลิก / รีเซ็ตเป็นแบบร่าง

        ตัดสินจากวันตัดงวดปัจจุบัน ณ ตอนกด (ค่าเดียวกับที่ใช้คำนวณฟิลด์สถานะ)
        งานเบื้องหลังที่จำเป็นต้องข้ามจริง ๆ ให้ส่ง context npd_skip_cancel_lock=True
        """
        if not self or self.env.context.get('npd_skip_cancel_lock'):
            return
        if self.env.user.has_group(BYPASS_GROUP):
            return
        cutoff = self._cancel_lock_cutoff()
        if not cutoff:
            return
        blocked = self.filtered(lambda r: r._cancel_lock_is_locked(cutoff))
        if not blocked:
            return
        lines = [
            '- %s (%s %s)' % (
                rec.display_name,
                self._cancel_lock_date_label,
                rec[self._cancel_lock_date_field].strftime('%d/%m/%Y'),
            )
            for rec in blocked[:10]
        ]
        if len(blocked) > 10:
            lines.append('... และอีก %s ใบ' % (len(blocked) - 10))
        raise UserError('%s\n\nเอกสารที่มี%sก่อนวันที่ %s ถูกปิดงวดแล้ว\n%s' % (
            LOCK_MESSAGE,
            self._cancel_lock_date_label,
            cutoff.strftime('%d/%m/%Y'),
            '\n'.join(lines),
        ))

    @api.model
    def _cancel_lock_refresh(self, cutoff):
        """คำนวณสถานะใหม่เฉพาะใบที่ค่าในฐานข้อมูลไม่ตรงกับวันตัดงวดล่าสุด"""
        date_field = self._cancel_lock_date_field
        base = self._cancel_lock_scope_domain() + [
            ('state', 'not in', list(self._cancel_lock_done_states)),
            (date_field, '!=', False),
        ]
        records = self.search(base + [
            (date_field, '<', cutoff), ('cancel_lock_state', '!=', 'locked'),
        ])
        records |= self.search(base + [
            (date_field, '>=', cutoff), ('cancel_lock_state', '!=', 'unlocked'),
        ])
        if records:
            self.env.add_to_compute(self._fields['cancel_lock_state'], records)
            records.flush_recordset(['cancel_lock_state'])
        return len(records)
