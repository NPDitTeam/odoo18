# -*- coding: utf-8 -*-
"""ห้ามยืนยันใบรับชำระที่เลยกำหนด

กติกา
    วันที่อ้างอิง = วันที่ที่เก่ากว่าระหว่าง วันที่จากสลิป กับ วันที่รับชำระในเอกสาร
    กำหนด        = วันที่ 10 ของเดือนถัดจากเดือนของวันที่อ้างอิง
    วันนี้ (เวลาไทย) > กำหนด -> ยืนยันไม่ได้ ต้องติดต่อฝ่ายการเงิน

ทำไมเอาวันที่ที่เก่ากว่า
    * วันที่จากสลิปเก่า    = เงินเข้าในเดือนที่ยื่นภาษีไปแล้ว
    * วันที่ในเอกสารเก่า  = ใบนี้จะไปลงบัญชีในเดือนที่ยื่นภาษีไปแล้ว
    อย่างใดอย่างหนึ่งก็ทำให้ยอดของเดือนที่ยื่นไปแล้วเปลี่ยน และกันกรณีอ่านสลิปแล้ว
    ไปแก้วันที่ในเอกสารเป็นวันนี้เพื่อเลี่ยงด่าน

ไม่ดูวันที่ใบแจ้งหนี้
    ลูกค้าจ่ายหนี้เก่าเดือนนี้ = เงินเข้าเดือนนี้ ลงบัญชีเดือนนี้ ไม่กระทบงวดที่ยื่นไปแล้ว
"""
from datetime import datetime

import pytz
from dateutil.relativedelta import relativedelta

from odoo import _, models
from odoo.exceptions import UserError

THAI_TZ = pytz.timezone('Asia/Bangkok')
BYPASS_GROUP = 'npd_payment_late_post_lock.group_late_post_bypass'
PARAM_LOCK_DAY = 'npd_payment_late_post_lock.lock_day'
DEFAULT_LOCK_DAY = 10


def thai_today():
    """วันที่ปัจจุบันของประเทศไทย ไม่ขึ้นกับ timezone ของเครื่องหรือฐานข้อมูล"""
    return datetime.now(pytz.utc).astimezone(THAI_TZ).date()


def post_deadline(ref_date, lock_day=DEFAULT_LOCK_DAY):
    """วันสุดท้ายที่ยังยืนยันได้ = วันที่ lock_day ของเดือนถัดจาก ref_date"""
    return ref_date + relativedelta(months=1, day=lock_day)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def _late_post_lock_day(self):
        value = self.env['ir.config_parameter'].sudo().get_param(PARAM_LOCK_DAY)
        try:
            day = int(value) if value else DEFAULT_LOCK_DAY
        except ValueError:
            day = DEFAULT_LOCK_DAY
        return min(max(day, 1), 28)

    def _late_post_reference(self):
        """คืน (วันที่อ้างอิง, ชื่อของวันที่นั้น) หรือ (False, '') ถ้าไม่มีวันที่ให้ตรวจ"""
        self.ensure_one()
        candidates = []
        slip_date = self._parse_slip_date(self.slip_date_extracted) \
            if self.slip_date_extracted else None
        if slip_date:
            candidates.append((slip_date, _('วันที่โอนตามสลิป')))
        if self.date:
            candidates.append((self.date, _('วันที่รับชำระในเอกสาร')))
        if not candidates:
            return False, ''
        return min(candidates, key=lambda c: c[0])

    def _late_post_in_scope(self):
        """เฉพาะเงินที่ลูกค้าจ่ายให้เราจริง
        ไม่รวม หักเงินประกันค่าเช่า / สมุดรายวันรับชำระลดหนี้ (ตัดหนี้ในระบบ ไม่มีเงินเข้า)
        """
        self.ensure_one()
        if self.payment_type != 'inbound':
            return False
        if self.payment_method_one_id.name == 'หักเงินประกันค่าเช่า':
            return False
        if 'ลดหนี้' in (self.journal_id.name or ''):
            return False
        return True

    def _check_late_post_lock(self):
        # skip_slip_date_check = ใบที่ระบบสร้างเองจากการหักเงินประกัน (account_voucher_npd)
        if self.env.context.get('skip_late_post_lock') \
                or self.env.context.get('skip_slip_date_check') \
                or self.env.su or self.env.user.has_group(BYPASS_GROUP):
            return
        today = thai_today()
        lock_day = self._late_post_lock_day()
        for payment in self.filtered(lambda p: p._late_post_in_scope()):
            ref_date, label = payment._late_post_reference()
            if not ref_date:
                continue
            deadline = post_deadline(ref_date, lock_day)
            if today > deadline:
                raise UserError(_(
                    "ไม่สามารถรับชำระเงินย้อนหลังได้ เนื่องจากเกินกำหนด "
                    "ต้องติดต่อฝ่ายการเงิน\n\n"
                    "ลูกค้า: %(partner)s\n"
                    "%(label)s: %(ref)s\n"
                    "ต้องยืนยันภายในวันที่: %(deadline)s"
                ) % {
                    'partner': payment.partner_id.display_name or '-',
                    'label': label,
                    'ref': ref_date.strftime('%d/%m/%Y'),
                    'deadline': deadline.strftime('%d/%m/%Y'),
                })

    def action_post(self):
        self._check_late_post_lock()
        return super(AccountPayment, self).action_post()
