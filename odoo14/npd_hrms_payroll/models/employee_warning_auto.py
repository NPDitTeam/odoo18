# -*- coding: utf-8 -*-
"""ออกใบเตือนอัตโนมัติ เมื่อ "ลงเวลาไม่ครบ" เกินจำนวนครั้งที่กำหนดต่อรอบ

รอบเดือนเริ่มต้นของบริษัทคือ **วันที่ 25 ถึง 24** (วันตัดรอบ = 24)
ตรงกับรอบที่ใช้คิดเงินเดือน ตัวเลขสองฝั่งจึงอ้างอิงช่วงวันเดียวกัน

เกณฑ์ออกใบเตือน = วันทำงานที่ **พนักงานไม่ได้สแกนเข้างานเอง** และไม่มีใบลา
(``payroll.attendance.engine.missed_no_checkin_days``) สรุปเป็นราย ๆ ไป:

- ลืมกดเข้างาน (ขอเพิ่มเวลา "ลืมลงเวลา" ทีหลัง) -> **นับ** คือสิ่งที่ใบเตือนเตือน
- เข้างานแล้ว แค่ลืมกดออกงาน                    -> ไม่นับ
- ทำงานนอกสถานที่ / ระบบมีปัญหา                 -> ไม่นับ (ไม่ใช่ความผิดพนักงาน)
- มีใบลา                                         -> ไม่นับ

หมายเหตุ: การ **หักเงิน** ยังใช้ ``missed_log`` ตัวเดิม (ขาดครบคู่)
คนละตัวกันโดยตั้งใจ — ปรับเกณฑ์ใบเตือนได้โดยไม่กระทบยอดเงินเดือน

**สิทธิหยุดวันเสาร์**: พนักงานบางคนหยุดเสาร์ได้ตามสิทธิ ถ้าไม่ได้ยื่นใบลา
วันนั้นจะกลายเป็น "ลงเวลาไม่ครบ" ทั้งที่มีสิทธิหยุด ระบบจึงยกเว้นวันเสาร์
ให้ตามจำนวนสิทธิที่มี (saturday.leave.config) ก่อนนับเข้าเกณฑ์ออกใบเตือน

พอร์ตจาก Odoo 14 — ของเดิมดึงวันที่ลงเวลาไม่ครบจาก ``calculate_lateness.php``
ฝั่ง PHP ตอนนี้อ่านจากข้อมูลลงเวลาใน Odoo ตรง ๆ ไม่ต้องยิงข้ามเซิร์ฟเวอร์
"""

import base64
import calendar
import logging
from datetime import date, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# ช่วงวันที่ที่ผู้ใช้พิมพ์เองได้สูงสุด (กันเผลอสั่งตรวจยาวเป็นปี)
MAX_TARGET_RANGE_DAYS = 100
DEFAULT_CYCLE_END_DAY = 24      # รอบ 25 -> 24
DEFAULT_THRESHOLD = 3           # เกิน 3 ครั้งต่อรอบ = ออกใบเตือน

THAI_MONTHS = ('มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม',
               'มิถุนายน', 'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม',
               'พฤศจิกายน', 'ธันวาคม')


class EmployeeWarningAutoConfig(models.Model):
    _name = 'employee.warning.auto.config'
    _description = 'ตั้งค่าออกใบเตือนอัตโนมัติ (ลงเวลาไม่ครบ)'
    _rec_name = 'display_name'

    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True,
        default=lambda self: self.env.company)

    auto_enabled = fields.Boolean(
        string='ออกใบเตือนอัตโนมัติ',
        default=False,
        help='ติ๊ก = พอจบรอบระบบจะออกใบเตือนให้เองและส่งเข้าแอปพนักงาน\n'
             'ไม่ติ๊ก = ยังกดออกเองแบบแมนนวลได้จากปุ่มในหน้านี้',
    )
    cycle_start_day = fields.Integer(
        string='รอบเริ่มวันที่',
        compute='_compute_cycle_start_day', readonly=False,
        help='วันแรกของรอบ (ของเดือนก่อน)\n'
             'แก้ช่องนี้หรือช่องวันตัดรอบก็ได้ อีกช่องจะขยับตามเอง\n'
             'เพราะรอบเดือนต่อกันพอดี วันเริ่ม = วันตัดรอบ + 1 เสมอ',
    )
    cycle_end_day = fields.Integer(
        string='ถึงวันที่ (วันตัดรอบ)',
        default=DEFAULT_CYCLE_END_DAY,
        required=True,
        help='วันสุดท้ายของรอบ — ค่าเริ่มต้น 24 หมายถึงรอบ 25 ถึง 24',
    )
    cycle_rule_display = fields.Char(
        string='รอบที่ใช้', compute='_compute_cycle_rule_display',
        help='ช่วงของรอบที่ได้จากวันตัดรอบ — ระบบคำนวณให้ ไม่ต้องกรอกวันเริ่ม')
    threshold = fields.Integer(
        string='ลงเวลาไม่ครบเกินกี่ครั้ง จึงออกใบเตือน',
        default=DEFAULT_THRESHOLD,
        required=True,
        help='นับต่อ 1 รอบ — ค่าเริ่มต้น 3 ครั้ง (เกิน 3 คือ 4 ครั้งขึ้นไป)',
    )
    ignore_pending_addtime = fields.Boolean(
        string='ไม่นับวันที่ยื่นคำขอเพิ่มเวลาไว้ (รออนุมัติ)',
        default=True,
        help=('ใช้กับคำขอประเภท "ทำงานนอกสถานที่" และ "ระบบมีปัญหา" '
              'ที่ยังไม่มีใครกดอนุมัติ\n'
              'ติ๊กไว้ = ให้ประโยชน์แก่พนักงานไว้ก่อน ถือว่ามีเหตุยกเว้น ไม่นับ\n'
              '(ที่อนุมัติแล้ว ไม่นับให้อยู่แล้ว)\n'
              '\n'
              'หมายเหตุ: ประเภท "ลืมลงเวลา" ที่เป็นการลืมกดเข้างาน ยังนับเสมอ '
              'ไม่ว่าจะอนุมัติแล้วหรือไม่ '
              'เพราะการลืมกดเข้างานคือสิ่งที่ใบเตือนนี้เตือนโดยตรง'),
    )
    run_day = fields.Integer(
        string='ให้ระบบรันวันที่',
        compute='_compute_run_day',
        help=(
            'ระบบตั้งให้เองเป็น "วันถัดจากวันตัดรอบ" ไม่ต้องแก้\n'
            'เช่น วันตัดรอบ 24 -> รันวันที่ 25\n'
            '\n'
            'ทำไมต้องเป็นวันถัดไป: จะรู้ว่าใครลงเวลาครบไหมในวันที่ 24 ได้\n'
            'ก็ต่อเมื่อวันที่ 24 ผ่านไปแล้ว ถ้ารันวันที่ 24 ตอนเช้า\n'
            'วันนั้นยังไม่จบ ระบบจะนับไม่ได้ และวันที่ 24 จะตกหล่นทุกเดือน\n'
            '\n'
            'รอบที่ตรวจยังเป็น 25 ถึง 24 ครบเต็มรอบเหมือนเดิม\n'
            'แค่ออกใบเตือนตอนเช้าของวันถัดไป'
        ),
    )
    respect_saturday_quota = fields.Boolean(
        string='ยกเว้นวันเสาร์ตามสิทธิหยุดวันเสาร์',
        default=True,
        help='พนักงานที่มีสิทธิหยุดวันเสาร์ ถ้าไม่ได้ยื่นใบลา วันนั้นจะถูกนับเป็น\n'
             '"ลงเวลาไม่ครบ" ทั้งที่มีสิทธิหยุด ติ๊กไว้เพื่อยกเว้นให้ตามจำนวนสิทธิ\n'
             'จะได้ไม่ออกใบเตือนมั่ว',
    )
    warning_type = fields.Selection(
        [
            ('verbal', 'ตักเตือนด้วยวาจา'),
            ('written', 'ตักเตือนเป็นหนังสือ'),
        ],
        string='ประเภทใบเตือนที่ออก',
        default='written',
        required=True,
    )
    subject = fields.Char(
        string='เรื่องที่โดนเตือน',
        default='การลงเวลาปฏิบัติงานไม่ครบถ้วนตามระเบียบบริษัท',
        required=True,
    )
    issuer_name = fields.Char(
        string='ออกโดย', default='สำนักงานส่วนกลาง', required=True)
    rule_clauses = fields.Text(
        string='ข้อบังคับที่อ้างถึงในใบเตือน',
        default=('หมวดที่ 9 วินัยและโทษทางวินัย\n'
                 '(โปรดแก้เลขข้อให้ตรงกับระเบียบข้อบังคับการทำงานของบริษัท)'),
        help=('ข้อความนี้จะถูกพิมพ์ลงในใบเตือนตรง ๆ\n'
              'ระบบไม่เดาเลขข้อระเบียบให้ เพราะเป็นเอกสารทางวินัย '
              'ต้องอ้างเลขข้อให้ตรงกับข้อบังคับจริงของบริษัท'),
    )
    branch_manager_name = fields.Char(string='ผู้จัดการฝ่ายบริหารสาขา')
    hr_manager_name = fields.Char(string='ผู้จัดการฝ่ายทรัพยากรบุคคล')

    # ---- เลือกรอบที่จะตรวจตอนกดปุ่มเอง (cron ไม่ใช้ ใช้รอบปัจจุบันเสมอ) ----
    target_month = fields.Selection(
        [(str(m), n) for m, n in enumerate(THAI_MONTHS, 1)],
        string='ตรวจรอบที่จบเดือน',
        default=lambda self: str(fields.Date.today().month),
        help='ใช้เฉพาะตอนกดปุ่มเอง — เลือกได้ว่าจะตรวจรอบไหน\n'
             'ออกใบเตือนย้อนหลังได้ ไม่ต้องรอ cron',
    )
    target_year = fields.Integer(
        string='ปี (ค.ศ.)',
        default=lambda self: fields.Date.today().year,
    )
    # แยกเป็น 2 ช่องวันที่ ให้เห็นชัดว่ารอบเริ่มวันไหน จบวันไหน
    # ระบบเติมให้เองจาก "วันตัดรอบ" + เดือน/ปีที่เลือก แต่ "พิมพ์ทับเองได้"
    # (store=True + readonly=False คือสูตรของ Odoo ที่ทำให้ช่องคำนวณแก้เองได้)
    target_cycle_start = fields.Date(
        string='รอบเริ่มวันที่', compute='_compute_target_cycle_dates',
        store=True, readonly=False,
        help='วันแรกของรอบที่จะตรวจ — '
             'ปกติระบบเติมให้จากวันตัดรอบ แต่พิมพ์เองได้ถ้าอยากตรวจช่วงอื่น')
    target_cycle_end = fields.Date(
        string='ถึงวันที่', compute='_compute_target_cycle_dates',
        store=True, readonly=False,
        help='วันสุดท้ายของรอบที่จะตรวจ (พิมพ์เองได้)')
    target_cycle_display = fields.Char(
        string='รอบที่จะตรวจ', compute='_compute_target_cycle_display',
        help='ช่วงวันที่จริงของรอบที่เลือก — ดูก่อนกดปุ่มว่าตรงกับที่ต้องการไหม')

    display_name = fields.Char(compute='_compute_display_name')

    @api.depends('cycle_end_day', 'run_day')
    def _compute_cycle_rule_display(self):
        """อธิบายรอบเป็นภาษาคน — ผู้ใช้จะได้ไม่ต้องเดาว่ารอบเริ่มวันไหน"""
        for rec in self:
            end_day = int(rec.cycle_end_day or DEFAULT_CYCLE_END_DAY)
            if 1 <= end_day <= 27:
                start_txt = _('วันที่ %s ของเดือนก่อน') % (end_day + 1)
            else:
                start_txt = _('วันที่ 1 ของเดือน')
            rec.cycle_rule_display = _(
                '%(start)s ถึง วันที่ %(end)s — ออกใบเตือนเช้าวันที่ %(run)s'
            ) % {'start': start_txt, 'end': end_day, 'run': rec.run_day or '-'}

    @api.depends('cycle_end_day')
    def _compute_run_day(self):
        """วันรัน = วันถัดจากวันตัดรอบ

        ต้องรอให้วันสุดท้ายของรอบผ่านไปก่อน ถึงจะรู้ว่าวันนั้นลงเวลาครบไหม
        (วันตัดรอบ 28-31 ไม่มีครบทุกเดือน จึงเลื่อนไปรันวันที่ 1 ของเดือนถัดไป)
        """
        for rec in self:
            end_day = int(rec.cycle_end_day or DEFAULT_CYCLE_END_DAY)
            rec.run_day = end_day + 1 if 1 <= end_day <= 27 else 1

    @api.depends('cycle_end_day')
    def _compute_cycle_start_day(self):
        """วันเริ่มรอบ = วันตัดรอบ + 1 (รอบเดือนต่อกันพอดี ไม่มีวันว่างคั่น)"""
        for rec in self:
            end_day = int(rec.cycle_end_day or DEFAULT_CYCLE_END_DAY)
            rec.cycle_start_day = end_day + 1 if 1 <= end_day <= 27 else 1

    @api.onchange('cycle_start_day')
    def _onchange_cycle_start_day(self):
        """กรอกวันเริ่มรอบเองได้ แล้ววันตัดรอบขยับตามให้"""
        for rec in self:
            start = int(rec.cycle_start_day or 0)
            if not (2 <= start <= 28):
                return {'warning': {
                    'title': _('วันเริ่มรอบไม่ถูกต้อง'),
                    'message': _(
                        'กรอกได้ระหว่างวันที่ 2 ถึง 28\n'
                        'เพราะวันตัดรอบต้องเป็นวันก่อนหน้า และบางเดือน'
                        'ไม่มีวันที่ 29-31 ถ้าใช้จะมีเดือนที่ระบบไม่รันเลย'),
                }}
            rec.cycle_end_day = start - 1

    @api.constrains('cycle_end_day')
    def _check_cycle_end_day(self):
        for rec in self:
            if not (1 <= rec.cycle_end_day <= 27):
                raise ValidationError(_(
                    'วันตัดรอบต้องอยู่ระหว่าง 1 ถึง 27 (รอบเริ่ม 2 ถึง 28)\n'
                    'เกินจากนี้จะมีเดือนที่ไม่มีวันดังกล่าว '
                    'แล้วระบบจะไม่ออกใบเตือนเลยทั้งเดือน'))

    @api.depends('target_month', 'target_year', 'cycle_end_day')
    def _compute_target_cycle_dates(self):
        """เติมช่วงวันที่ให้อัตโนมัติเมื่อเปลี่ยนเดือน/ปี/วันตัดรอบ

        ถ้าผู้ใช้พิมพ์วันที่เองแล้ว ค่าที่พิมพ์จะอยู่จนกว่าจะไปแตะ
        เดือน/ปี/วันตัดรอบอีกครั้ง (แล้วระบบจะเติมทับให้เป็นรอบมาตรฐาน)
        """
        Warning_ = self.env['employee.warning']
        for rec in self:
            try:
                start, end = Warning_._cycle_bounds(
                    rec.cycle_end_day, int(rec.target_month or 0),
                    int(rec.target_year or 0))
                rec.target_cycle_start = start
                rec.target_cycle_end = end
            except Exception:
                rec.target_cycle_start = False
                rec.target_cycle_end = False

    @api.depends('target_cycle_start', 'target_cycle_end')
    def _compute_target_cycle_display(self):
        for rec in self:
            if rec.target_cycle_start and rec.target_cycle_end:
                rec.target_cycle_display = '%s ถึง %s' % (
                    rec.target_cycle_start.strftime('%d/%m/%Y'),
                    rec.target_cycle_end.strftime('%d/%m/%Y'))
            else:
                rec.target_cycle_display = ''

    @api.constrains('target_cycle_start', 'target_cycle_end')
    def _check_target_cycle(self):
        for rec in self:
            start, end = rec.target_cycle_start, rec.target_cycle_end
            if not (start and end):
                continue
            if start > end:
                raise ValidationError(_(
                    'ช่วงวันที่ไม่ถูกต้อง: "รอบเริ่มวันที่" (%(s)s) '
                    'อยู่หลัง "ถึงวันที่" (%(e)s)') % {
                        's': start.strftime('%d/%m/%Y'),
                        'e': end.strftime('%d/%m/%Y')})
            # กันเผลอพิมพ์ช่วงยาวเป็นปี แล้วระบบไล่สแกนรายคนนับร้อยรอบ
            if (end - start).days + 1 > MAX_TARGET_RANGE_DAYS:
                raise ValidationError(_(
                    'ช่วงที่เลือกยาว %(d)s วัน เกินที่ระบบตรวจได้ '
                    '(สูงสุด %(m)s วัน) '
                    'ถ้าต้องการตรวจหลายรอบ ให้ออกใบเตือนทีละรอบ') % {
                        'd': (end - start).days + 1,
                        'm': MAX_TARGET_RANGE_DAYS})

    @api.depends('cycle_end_day', 'threshold', 'auto_enabled')
    def _compute_display_name(self):
        for rec in self:
            mode = _('อัตโนมัติ') if rec.auto_enabled else _('แมนนวล')
            rec.display_name = _('รอบ %s ถึง %s | เกิน %s ครั้ง | %s') % (
                (rec.cycle_end_day or 0) + 1, rec.cycle_end_day,
                rec.threshold, mode)

    # ------------------------------------------------------------------
    @api.model
    def _get_config(self):
        """ค่าตั้งค่าของบริษัทที่กำลังใช้งาน (สร้างให้อัตโนมัติถ้ายังไม่มี)

        แยกตามบริษัท เพราะบริษัทที่เช่าระบบไปตั้งเกณฑ์/ชื่อผู้ลงนามของตัวเอง
        """
        company = self.env.company
        config = self.sudo().search([('company_id', '=', company.id)], limit=1)
        if not config:
            config = self.sudo().create({'company_id': company.id})
        return config

    @api.model
    def action_open_config(self):
        config = self._get_config()
        # รีเซ็ต "รอบที่จะตรวจ" เป็นรอบปัจจุบันทุกครั้งที่เปิดเมนู
        # ค่า default ของฟิลด์ใช้แค่ตอนสร้าง record ครั้งแรกเท่านั้น
        # ถ้าไม่รีเซ็ต พอขึ้นปีใหม่ช่องปีจะค้างอยู่ที่ปีเก่า แล้วกดออกใบเตือน
        # จะไปตรวจรอบของปีที่แล้วโดยไม่รู้ตัว
        month, year = self.env['employee.warning']._current_cycle(config)
        config.sudo().write({'target_month': str(month), 'target_year': year})
        return {
            'type': 'ir.actions.act_window',
            'name': _('ตั้งค่าออกใบเตือนอัตโนมัติ'),
            'res_model': self._name,
            'view_mode': 'form',
            'res_id': config.id,
            'target': 'new',
        }

    def action_close(self):
        return {'type': 'ir.actions.act_window_close'}

    def _target_cycle(self):
        """เดือน/ปีของรอบที่ผู้ใช้เลือกไว้ (ไม่ได้เลือก = รอบปัจจุบัน)"""
        self.ensure_one()
        month = int(self.target_month or 0)
        year = int(self.target_year or 0)
        if not (1 <= month <= 12) or year < 2000:
            return self.env['employee.warning']._current_cycle(self)
        return month, year

    def _target_range(self):
        """ช่วงวันที่ที่จะตรวจ = สิ่งที่ผู้ใช้เห็นอยู่บนจอจริง ๆ

        ถ้าพิมพ์วันที่เองไว้ ใช้ตามนั้น ไม่งั้นคำนวณจากเดือน/ปี + วันตัดรอบ
        """
        self.ensure_one()
        start, end = self.target_cycle_start, self.target_cycle_end
        if start and end and start <= end:
            return start, end
        month, year = self._target_cycle()
        return self.env['employee.warning']._cycle_bounds(
            self.cycle_end_day, month, year)

    def action_preview_cycle(self):
        """ดูผลก่อนออกจริง — ไม่สร้างใบเตือน"""
        self.ensure_one()
        start, end = self._target_range()
        Warning_ = self.env['employee.warning']
        result = Warning_._scan_missed_checkin(
            config=self, cycle_start=start, cycle_end=end, dry_run=True)
        return Warning_._scan_result_action(result, dry_run=True)

    def action_issue_now(self):
        """ออกใบเตือนแบบแมนนวลเดี๋ยวนี้ (ใช้เกณฑ์เดียวกับอัตโนมัติ)"""
        self.ensure_one()
        start, end = self._target_range()
        Warning_ = self.env['employee.warning']
        result = Warning_._scan_missed_checkin(
            config=self, cycle_start=start, cycle_end=end, dry_run=False)
        return Warning_._scan_result_action(result, dry_run=False)


class EmployeeWarningLine(models.Model):
    _inherit = 'employee.warning.line'

    source = fields.Selection(
        [('manual', 'ออกเอง'), ('auto', 'ระบบออกอัตโนมัติ')],
        string='ที่มา', default='manual', readonly=True)
    cycle_start = fields.Date(string='รอบตั้งแต่', readonly=True)
    cycle_end = fields.Date(string='ถึง', readonly=True)
    cycle_display = fields.Char(
        string='รอบใบเตือน', compute='_compute_cycle_display', store=True,
        help='ช่วงวันที่ที่ใช้ตรวจการลงเวลาของใบเตือนใบนี้')
    missed_count = fields.Integer(string='ลงเวลาไม่ครบ (ครั้ง)', readonly=True)
    threshold_applied = fields.Integer(
        string='เกณฑ์ที่ใช้ (ครั้ง/รอบ)', readonly=True,
        help='เกณฑ์ ณ ตอนที่ออกใบเตือนใบนี้\n'
             'เก็บไว้กับใบเตือนเลย เพราะถ้าวันหลังไปแก้เกณฑ์ในหน้าตั้งค่า '
             'ใบเก่าต้องยังอธิบายตัวเองได้ว่าตอนนั้นใช้เกณฑ์เท่าไหร่')
    missed_detail = fields.Text(string='วันที่ลงเวลาไม่ครบ', readonly=True)

    _sql_constraints = [
        ('auto_cycle_uniq',
         'unique(warning_id, cycle_start, cycle_end, source)',
         'รอบนี้ออกใบเตือนอัตโนมัติให้พนักงานคนนี้ไปแล้ว'),
    ]

    @api.depends('cycle_start', 'cycle_end')
    def _compute_cycle_display(self):
        for line in self:
            if line.cycle_start and line.cycle_end:
                line.cycle_display = '%s - %s' % (
                    line.cycle_start.strftime('%d/%m/%Y'),
                    line.cycle_end.strftime('%d/%m/%Y'))
            else:
                line.cycle_display = ''

    # ------------------------------------------------------------------
    # ออกไฟล์ใบเตือนจากระบบ แล้วแนบให้เลย (แอปพนักงานอ่านจากไฟล์แนบนี้)
    # ------------------------------------------------------------------
    def report_thai_date(self):
        """วันที่แบบไทย พ.ศ. เช่น '22 มกราคม 2569'"""
        self.ensure_one()
        d = self.warning_date
        if not d:
            return ''
        return '%d %s %d' % (d.day, THAI_MONTHS[d.month - 1], d.year + 543)

    def report_company_info(self):
        """ชื่อ+ที่อยู่บริษัทตามสังกัดพนักงาน

        ใช้ที่อยู่ชุดเดียวกับหัวสลิปเงินเดือน ย้ายออฟฟิศแก้ที่เดียว
        ใบเตือนเปลี่ยนตามเอง
        """
        self.ensure_one()
        company = (self.warning_id.employee_id.company_id
                   or self.company_id or self.env.company)
        partner = company.partner_id
        parts = [partner.street, partner.street2, partner.city,
                 partner.state_id.name, partner.zip]
        address = ' '.join(p for p in parts if p)
        if partner.phone:
            address = ('%s  โทร. %s' % (address, partner.phone)).strip()
        return {
            'company': company,
            'name': company.name or '',
            'address': address,
        }

    def report_config(self):
        self.ensure_one()
        company = (self.warning_id.employee_id.company_id
                   or self.company_id or self.env.company)
        return self.env['employee.warning.auto.config'].sudo().with_company(
            company)._get_config()

    def action_generate_pdf(self):
        """ปุ่มในฟอร์ม — สร้าง/สร้างใหม่ไฟล์ใบเตือนแล้วแนบทับของเดิม"""
        self._attach_warning_pdf()
        return True

    def _attach_warning_pdf(self):
        """เรนเดอร์ใบเตือนเป็น PDF แล้วใส่ลงฟิลด์ 'ไฟล์แนบใบเตือน'

        ทำให้ทั้งใบเตือนที่ระบบออกอัตโนมัติและที่ออกเอง มีไฟล์แนบเหมือนกัน
        พนักงานเปิดดูในแอปได้ทันทีโดยไม่ต้องให้ HR ไปแนบไฟล์เอง
        """
        report = self.env.ref(
            'npd_hrms_payroll.action_report_employee_warning',
            raise_if_not_found=False)
        if not report:
            _logger.warning('[WARN-AUTO] ยังไม่มีเทมเพลตใบเตือน ข้ามการแนบไฟล์')
            return False
        for line in self:
            try:
                pdf, _ftype = report.sudo()._render_qweb_pdf(
                    report.report_name, line.ids)
            except Exception as exc:
                _logger.warning('[WARN-AUTO] สร้าง PDF ใบเตือน id=%s ไม่สำเร็จ: %s',
                                line.id, exc)
                continue
            employee = line.warning_id.employee_id
            # ใช้ "ชื่อพนักงาน" ในชื่อไฟล์ อ่านรู้เรื่องกว่ารหัส
            # (ไม่มีชื่อค่อยตกไปใช้รหัส)
            name = ('%s %s' % (employee.firstname or '',
                               employee.lastname or '')).strip()
            name = name or employee.employee_code or '-'
            # ตัดอักขระที่ใช้ในชื่อไฟล์ไม่ได้ออก กันไฟล์เสียตอนดาวน์โหลด
            for bad in '\\/:*?"<>|\r\n\t':
                name = name.replace(bad, ' ')
            name = ' '.join(name.split())
            filename = 'ใบเตือน_%s_ครั้งที่%s.pdf' % (
                name, line.warning_number or 1)
            line.sudo().write({
                'attachment': base64.b64encode(pdf),
                'attachment_filename': filename,
            })
        return True


class EmployeeWarning(models.Model):
    _inherit = 'employee.warning'

    # ------------------------------------------------------------------
    # ตรรกะนับ "ลงเวลาไม่ครบ" ต่อรอบ
    # ------------------------------------------------------------------
    @api.model
    def _cycle_bounds(self, end_day, month, year):
        """คืน (วันเริ่มรอบ, วันจบรอบ) ของรอบที่จบในเดือน/ปีที่ระบุ"""
        end_day = min(max(int(end_day or DEFAULT_CYCLE_END_DAY), 1),
                      calendar.monthrange(year, month)[1])
        cycle_end = date(year, month, end_day)
        prev_month = month - 1 or 12
        prev_year = year if month > 1 else year - 1
        prev_day = min(end_day, calendar.monthrange(prev_year, prev_month)[1])
        cycle_start = date(prev_year, prev_month, prev_day) + timedelta(days=1)
        return cycle_start, cycle_end

    @api.model
    def _cycle_of(self, end_day, day):
        """รอบ (เดือน, ปี) ที่ครอบวันนี้อยู่"""
        month, year = day.month, day.year
        cycle_start, cycle_end = self._cycle_bounds(end_day, month, year)
        if day > cycle_end:
            month += 1
            if month > 12:
                month, year = 1, year + 1
        elif day < cycle_start:
            month -= 1
            if month < 1:
                month, year = 12, year - 1
        return month, year

    @api.model
    def _server_today(self):
        """วันที่ตาม "เวลาเซิร์ฟเวอร์" ไม่ใช่ timezone ของผู้ใช้

        cron ทำงานภายใต้ OdooBot ซึ่งไม่ได้ตั้ง timezone ไว้ ถ้าใช้
        context_today แล้ววันหนึ่งมีคนไปตั้ง tz ให้ OdooBot วันที่จะเลื่อน
        และ cron อาจไม่ทำงานในวันที่ตั้งไว้ จึงล็อกให้อิงเวลาเซิร์ฟเวอร์ตรง ๆ
        """
        return fields.Date.today()

    @api.model
    def _cron_target_cycle(self, config):
        """รอบที่ cron ต้องตรวจ = **รอบล่าสุดที่จบไปแล้ว** ณ วันที่รัน

        ไล่จากรอบของเดือนนี้ ถ้ายังไม่จบก็ถอยไปรอบก่อนหน้า
        ทำให้ตั้งวันรันเป็นวันไหนก็ได้ผลถูกเสมอ รวมทั้งกรณีวันตัดรอบ
        เป็นสิ้นเดือนแล้วเลื่อนไปรันวันที่ 1 ของเดือนถัดไป
        """
        today = self._server_today()
        month, year = today.month, today.year
        _cycle_start, cycle_end = self._cycle_bounds(
            config.cycle_end_day, month, year)
        if cycle_end >= today:
            # รอบนี้ยังไม่จบ (วันสุดท้ายคือวันนี้หรือยังมาไม่ถึง) -> ถอยไปรอบก่อน
            month -= 1
            if month < 1:
                month, year = 12, year - 1
        return month, year

    @api.model
    def _current_cycle(self, config):
        """เดือน/ปีของ "รอบที่กำลังเดินอยู่ตอนนี้"

        รอบ 25 -> 24 : วันนี้ 1 ก.ย. อยู่ในรอบ 25 ส.ค. - 24 ก.ย. (จบเดือน 9)
                       วันนี้ 26 ก.ย. อยู่ในรอบ 25 ก.ย. - 24 ต.ค. (จบเดือน 10)
        """
        today = fields.Date.context_today(self)
        if today.day > config.cycle_end_day:
            month = today.month + 1
            year = today.year
            if month > 12:
                month, year = 1, year + 1
            return month, year
        return today.month, today.year

    @api.model
    def _excuse_saturdays(self, missed_days, employee, cycle_start, cycle_end):
        """ยกเว้นวันเสาร์ตามสิทธิหยุดวันเสาร์

        สิทธิเป็น "ครั้งต่อเดือน" รอบหนึ่งคาบ 2 เดือนปฏิทิน จึงให้สิทธิตามเดือน
        ของวันเสาร์นั้น ๆ (เดือนไหนใช้สิทธิเดือนนั้น)

        สิทธิดึงจากเมนู "สิทธิหยุดวันเสาร์" (saturday.leave.config) รายคน
        ลำดับความสำคัญ: ตั้งรายบุคคล -> ค่าของสาขา -> ค่าเริ่มต้นตามชนิดสาขา
        แต่ละคนจึงไม่เท่ากัน ระบบเรียกทีละคนอยู่แล้ว

        คืน (วันที่เหลือหลังยกเว้น, จำนวนวันเสาร์ที่ยกเว้นไป, สิทธิต่อเดือนของคนนั้น)
        """
        quota = self.env['saturday.leave.config'].sudo().api_get_saturday_quota(
            employee.employee_code)
        try:
            quota = int(quota or 0)
        except (TypeError, ValueError):
            quota = 0
        if quota <= 0:
            return list(missed_days), 0, quota

        remaining = {}
        kept, excused = [], 0
        for day in sorted(missed_days):
            if day.weekday() != 5:  # ไม่ใช่วันเสาร์
                kept.append(day)
                continue
            key = (day.year, day.month)
            if key not in remaining:
                remaining[key] = quota
            if remaining[key] > 0:
                remaining[key] -= 1
                excused += 1
            else:
                kept.append(day)
        return kept, excused, quota

    # ------------------------------------------------------------------
    # สแกน + ออกใบเตือน
    # ------------------------------------------------------------------
    @api.model
    def _scan_missed_checkin(self, config=None, month=None, year=None,
                             dry_run=False, employee_ids=None,
                             cycle_start=None, cycle_end=None):
        """ไล่ตรวจพนักงานทุกคนในรอบที่กำหนด แล้วออกใบเตือนให้คนที่เกินเกณฑ์

        :param cycle_start/cycle_end: ระบุช่วงวันที่เองได้ (ที่ผู้ใช้พิมพ์บนจอ)
                                      ถ้าไม่ระบุ = คำนวณจาก month/year ตามปกติ
        :param dry_run: True = ดูผลอย่างเดียว ไม่สร้างใบเตือน
        :return: dict สรุปผล
        """
        Config = self.env['employee.warning.auto.config']
        config = config or Config._get_config()

        if cycle_start and cycle_end:
            cycle_start = fields.Date.to_date(cycle_start)
            cycle_end = fields.Date.to_date(cycle_end)
            # เดือน/ปีในผลสรุปใช้รอบที่วันจบตกอยู่ ไว้อ้างอิงเฉย ๆ
            month, year = self._cycle_of(config.cycle_end_day, cycle_end)
        else:
            if not month or not year:
                month, year = self._current_cycle(config)
            cycle_start, cycle_end = self._cycle_bounds(
                config.cycle_end_day, month, year)

        company = config.company_id or self.env.company
        Employee = self.env['employee.salary'].sudo()
        domain = [('employee_code', '!=', False),
                  ('company_id', '=', company.id)]
        if employee_ids:
            domain.append(('id', 'in', employee_ids))
        candidates = Employee.search(domain)

        # คัดคนที่ "เข้ารอบนี้" ด้วยเกณฑ์เดียวกับที่รอบเงินเดือนใช้เป๊ะ ๆ
        # จะได้ไม่ออกใบเตือนให้คนที่ลาออกไปแล้ว หรือยังไม่เริ่มงาน
        Period = self.env['payroll.period'].sudo()
        employees = candidates.filtered(
            lambda emp: Period._is_eligible_employee(emp, cycle_start, cycle_end))
        skipped_not_eligible = len(candidates) - len(employees)

        # ดึงวันหยุดครั้งเดียวแล้วส่งต่อ — รอบหนึ่งวนพนักงานหลายร้อยคน
        Holiday = self.env['payroll.holiday'].sudo()
        holidays = set()
        for holiday_year in {cycle_start.year, cycle_end.year}:
            holidays |= Holiday.get_holiday_dates(holiday_year, company.id)

        Engine = self.env['payroll.attendance.engine']
        issued, over, skipped, details = 0, [], 0, []
        for employee in employees:
            missed = Engine.missed_no_checkin_days(
                employee, cycle_start, cycle_end,
                include_pending_excuse=config.ignore_pending_addtime,
                holidays=holidays)
            if missed is None:
                skipped += 1     # ไม่มีตารางกะ = ไม่รู้ว่าวันไหนต้องมาทำงาน
                continue
            if config.respect_saturday_quota:
                missed, excused, sat_quota = self._excuse_saturdays(
                    missed, employee, cycle_start, cycle_end)
            else:
                excused, sat_quota = 0, 0
            count = len(missed)
            if count <= config.threshold:
                continue

            over.append(employee)
            details.append({
                'employee': employee,
                'count': count,
                'days': sorted(missed),
                'excused_sat': excused,
                'sat_quota': sat_quota,
            })

        if not dry_run:
            for item in details:
                if self._issue_warning(item, config, cycle_start, cycle_end):
                    issued += 1

        return {
            'month': month,
            'year': year,
            'cycle_start': cycle_start,
            'cycle_end': cycle_end,
            'threshold': config.threshold,
            'scanned': len(employees),
            'skipped_not_eligible': skipped_not_eligible,
            'skipped_no_schedule': skipped,
            'over_threshold': len(over),
            'issued': issued,
            'details': details,
        }

    @api.model
    def _issue_warning(self, item, config, cycle_start, cycle_end):
        """สร้างใบเตือน 1 ใบให้พนักงานคนนั้น (ข้ามถ้ารอบนี้ออกไปแล้ว)"""
        employee = item['employee']
        warning = self.sudo().search([('employee_id', '=', employee.id)], limit=1)
        if not warning:
            warning = self.sudo().create({'employee_id': employee.id})

        Line = self.env['employee.warning.line'].sudo()
        existing = Line.search([
            ('warning_id', '=', warning.id),
            ('cycle_start', '=', cycle_start),
            ('cycle_end', '=', cycle_end),
            ('source', '=', 'auto'),
        ], limit=1)
        if existing:
            return False   # รอบนี้ออกไปแล้ว ไม่ออกซ้ำ

        # ในใบเตือน: ไล่วันที่ต่อกันเป็นย่อหน้าเดียว จะได้ไม่กินพื้นที่จนล้นหน้า
        # (ถ้าขึ้นบรรทัดละวัน คนที่ขาด 15 วันจะดันเนื้อหาตกไปหน้าที่สอง)
        days_inline = ', '.join(d.strftime('%d/%m/%Y') for d in item['days'])
        # ในหน้าจอ Odoo: เก็บแบบบรรทัดละวัน อ่านง่ายกว่าตอนตรวจสอบ
        days_text = '\n'.join('- %s' % d.strftime('%d/%m/%Y')
                              for d in item['days'])
        description = _(
            'ตรวจสอบประวัติการลงเวลาระหว่างวันที่ %(start)s ถึง %(end)s '
            'พบว่าท่านไม่ได้ลงเวลาเข้าปฏิบัติงานจำนวน %(count)s ครั้ง '
            'ซึ่งเกินเกณฑ์ที่บริษัทกำหนดไว้ (ไม่เกิน %(threshold)s ครั้งต่อรอบ) '
            'ได้แก่วันที่ %(days)s'
        ) % {
            'start': cycle_start.strftime('%d/%m/%Y'),
            'end': cycle_end.strftime('%d/%m/%Y'),
            'count': item['count'],
            'threshold': config.threshold,
            'days': days_inline,
        }
        if item.get('excused_sat'):
            # ระบุสิทธิของพนักงานคนนั้นด้วย เพราะแต่ละคนไม่เท่ากัน
            # (ตั้งรายบุคคล/รายสาขาได้ที่เมนู "สิทธิหยุดวันเสาร์")
            description += _(
                '\n(ยกเว้นวันเสาร์ให้แล้ว %(n)s วัน '
                'ตามสิทธิหยุดวันเสาร์ของท่าน %(quota)s ครั้ง/เดือน)'
            ) % {'n': item['excused_sat'], 'quota': item.get('sat_quota') or 0}

        line = Line.create({
            'warning_id': warning.id,
            'warning_date': fields.Date.context_today(self),
            'subject': config.subject,
            'warning_type': config.warning_type,
            'source': 'auto',
            'cycle_start': cycle_start,
            'cycle_end': cycle_end,
            'missed_count': item['count'],
            'threshold_applied': config.threshold,
            'missed_detail': days_text,
            'description': description,
        })
        line._attach_warning_pdf()
        _logger.info('[WARN-AUTO] ออกใบเตือน %s (%s ครั้ง) รอบ %s-%s',
                     employee.employee_code, item['count'], cycle_start, cycle_end)
        return True

    @api.model
    def _scan_result_action(self, result, dry_run):
        """แสดงผลสรุปให้ผู้ใช้เห็นหลังกดปุ่ม"""
        lines = [
            _('รอบ %s ถึง %s') % (result['cycle_start'].strftime('%d/%m/%Y'),
                                  result['cycle_end'].strftime('%d/%m/%Y')),
            _('ตรวจพนักงาน %s คน') % result['scanned'],
            _('เกินเกณฑ์ (>%s ครั้ง) %s คน') % (result['threshold'],
                                                result['over_threshold']),
        ]
        if result.get('skipped_not_eligible'):
            lines.append(_('ข้าม %s คน (ลาออกก่อนรอบนี้ / ยังไม่เริ่มงาน)')
                         % result['skipped_not_eligible'])
        if result['skipped_no_schedule']:
            lines.append(_('ข้าม %s คน (ยังไม่ได้ตั้งตารางกะ)')
                         % result['skipped_no_schedule'])
        if dry_run:
            lines.append(_('— ดูผลอย่างเดียว ยังไม่ได้ออกใบเตือน —'))
            for item in result['details'][:20]:
                lines.append('  • %s %s : %s ครั้ง' % (
                    item['employee'].employee_code,
                    item['employee'].firstname or '',
                    item['count']))
        else:
            lines.append(_('ออกใบเตือนแล้ว %s ใบ') % result['issued'])
            if result['over_threshold'] and not result['issued']:
                lines.append(_('(รอบนี้เคยออกใบเตือนไปแล้ว จึงไม่ออกซ้ำ)'))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('ผลการตรวจการลงเวลา'),
                'message': '\n'.join(lines),
                'sticky': True,
                'type': 'success' if not dry_run else 'info',
            },
        }

    # ------------------------------------------------------------------
    @api.model
    def cron_issue_missed_checkin_warnings(self):
        """cron รายวัน — ออกใบเตือนอัตโนมัติเมื่อรอบปิดแล้ว (ถ้าเปิดใช้งานไว้)

        วนทุกบริษัทที่ตั้งค่าไว้ เพราะบริษัทที่เช่าระบบตั้งวันตัดรอบ/เกณฑ์
        ของตัวเองได้ วันรันจึงไม่จำเป็นต้องตรงกัน
        """
        Config = self.env['employee.warning.auto.config'].sudo()
        today = self._server_today()
        for config in Config.search([('auto_enabled', '=', True)]):
            run_day = config.run_day or config.cycle_end_day or DEFAULT_CYCLE_END_DAY
            if today.day != run_day:
                _logger.info('[WARN-AUTO] %s: วันนี้ %s ไม่ใช่วันที่ตั้งให้รัน (%s) ข้าม',
                             config.company_id.name, today, run_day)
                continue
            month, year = self._cron_target_cycle(config)
            result = self.with_company(config.company_id)._scan_missed_checkin(
                config=config, month=month, year=year, dry_run=False)
            _logger.info('[WARN-AUTO] %s: ออกใบเตือน %s ใบ จากที่เกินเกณฑ์ %s คน',
                         config.company_id.name, result['issued'],
                         result['over_threshold'])
        return True
