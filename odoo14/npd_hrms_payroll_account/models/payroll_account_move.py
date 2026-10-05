# -*- coding: utf-8 -*-
"""ประวัติการลงบัญชีเงินเดือน — 1 แถวต่อ (รอบ, บริษัทของสลิป)

เป็นตัวกันลงซ้ำ (unique index เฉพาะแถวที่ยังไม่กลับรายการ) และเก็บยอด ณ
วันที่ลงบัญชีไว้เทียบ เพราะสลิปยังถูกตัวซิงก์ o14 เขียนทับได้หลังลงบัญชีแล้ว
"""
import hashlib

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


def _r2(value):
    # + 0.0 แปลง -0.0 เป็น 0.0 ไม่งั้นลายนิ้วมือเปลี่ยนทั้งที่ยอดไม่เปลี่ยน
    return '%.2f' % (round(value or 0.0, 2) + 0.0)


def slip_fingerprint(slips):
    """ลายนิ้วมือของสลิปชุดหนึ่ง: id + เงินสุทธิ + บรรทัดทั้งหมด

    ใช้บอกว่าสลิปถูกแก้หลังลงบัญชีหรือไม่ — ไม่บล็อกการซิงก์
    แต่ให้ฝ่ายบัญชีเห็นแล้วกลับรายการ/ลงใหม่เอง
    """
    rows = []
    for slip in slips.sorted('id'):
        lines = sorted(
            (line.type or '', (line.name or '').strip(), _r2(line.amount))
            for line in slip.line_ids)
        rows.append((slip.id, _r2(slip.net_salary), tuple(lines)))
    return hashlib.sha1(repr(rows).encode('utf-8')).hexdigest()


class NpdPayrollAccountMove(models.Model):
    _name = 'npd.payroll.account.move'
    _description = 'ประวัติการลงบัญชีเงินเดือน'
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(
        string='รายการ', compute='_compute_name', store=True)
    # ไม่ใส่ check_company: รอบที่ซิงก์จาก o14 เป็นของบริษัท 1
    # แต่มีสลิปของทุกบริษัท ลิงก์จึงเป็นของบริษัทสลิป ไม่ใช่บริษัทของรอบ
    period_id = fields.Many2one(
        'payroll.period', string='รอบเงินเดือน', required=True, index=True,
        ondelete='restrict')
    company_id = fields.Many2one(
        'res.company', string='บริษัท', required=True, index=True)
    move_id = fields.Many2one(
        'account.move', string='รายการบัญชี', required=True, ondelete='restrict',
        check_company=True)
    move_state = fields.Selection(
        related='move_id.state', string='สถานะรายการบัญชี')
    journal_id = fields.Many2one(
        related='move_id.journal_id', string='สมุดรายวัน')
    reversal_move_id = fields.Many2one(
        'account.move', string='รายการกลับรายการ', check_company=True)
    state = fields.Selection([
        ('posted', 'ลงบัญชีแล้ว'),
        ('reversed', 'กลับรายการแล้ว'),
    ], string='สถานะ', default='posted', required=True, index=True)
    date = fields.Date(string='วันที่ลงบัญชี')

    slip_count = fields.Integer(string='จำนวนสลิป')
    amount_gross = fields.Float(string='รวมรายได้', digits=(16, 2))
    amount_deduction = fields.Float(string='รวมรายการหัก', digits=(16, 2))
    amount_net = fields.Float(string='รวมเงินสุทธิ', digits=(16, 2))
    amount_employer_sso = fields.Float(
        string='ประกันสังคมส่วนนายจ้าง', digits=(16, 2))
    rounding_residue = fields.Float(
        string='เศษสตางค์ที่ปรับเข้าเงินเดือนค้างจ่าย', digits=(16, 2))
    fingerprint = fields.Char(string='ลายนิ้วมือสลิป', readonly=True)
    is_outdated = fields.Boolean(
        string='สลิปเปลี่ยนหลังลงบัญชี', compute='_compute_is_outdated')

    reversed_date = fields.Date(string='วันที่กลับรายการ')
    reversed_uid = fields.Many2one('res.users', string='ผู้กลับรายการ')
    reverse_reason = fields.Char(string='เหตุผลที่กลับรายการ')

    def init(self):
        # กันลงซ้ำระดับฐานข้อมูล: กดพร้อมกันสองคนก็ได้รายการเดียว
        # เฉพาะแถว posted เพื่อให้กลับรายการแล้วลงใหม่ได้
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS npd_payroll_account_move_posted_uniq
            ON npd_payroll_account_move (period_id, company_id)
            WHERE state = 'posted'
        """)

    @api.depends('period_id.month', 'period_id.year', 'company_id.name')
    def _compute_name(self):
        for rec in self:
            period = rec.period_id.sudo()
            rec.name = 'เงินเดือน %s — %s' % (
                period.display_name or '', rec.company_id.sudo().name or '')

    @api.depends('fingerprint', 'state', 'period_id', 'company_id')
    def _compute_is_outdated(self):
        Salary = self.env['payroll.salary'].sudo()
        for rec in self:
            if rec.state != 'posted' or not rec.period_id or not rec.fingerprint:
                rec.is_outdated = False
                continue
            slips = Salary.search([
                ('period_id', '=', rec.period_id.id),
                ('company_id', '=', rec.company_id.id),
            ])
            rec.is_outdated = slip_fingerprint(slips) != rec.fingerprint

    @api.ondelete(at_uninstall=False)
    def _unlink_never(self):
        # ประวัติคือหลักฐานว่าใครลงบัญชีอะไรเมื่อไร ลบแล้วจะลงซ้ำได้โดยไม่มีใครรู้
        raise UserError('ลบประวัติการลงบัญชีเงินเดือนไม่ได้ ให้ใช้กลับรายการ')

    # ------------------------------------------------------------------
    def _npd_check_company_access(self):
        allowed = self.env['npd.payroll.account.config']._npd_allowed_companies()
        for rec in self.sudo():
            if rec.company_id not in allowed:
                raise AccessError('คุณไม่มีสิทธิ์บริษัท %s' % rec.company_id.name)

    def action_open_move(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'รายการบัญชีเงินเดือน',
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'context': {'create': False},
        }

    def action_open_reverse_wizard(self):
        self.ensure_one()
        self.env['npd.payroll.account.config']._npd_check_poster()
        self._npd_check_company_access()
        if self.state != 'posted':
            raise UserError('รายการนี้กลับรายการไปแล้ว')
        return {
            'type': 'ir.actions.act_window',
            'name': 'กลับรายการบัญชีเงินเดือน',
            'res_model': 'npd.payroll.account.reverse.wizard',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'default_link_id': self.id},
        }

    def _npd_reverse(self, date, reason=None):
        """กลับรายการเงินเดือน แล้วปลดล็อกให้ลงใหม่ได้"""
        self.ensure_one()
        Config = self.env['npd.payroll.account.config']
        Config._npd_check_poster()
        self._npd_check_company_access()
        date = fields.Date.to_date(date)
        if not date:
            raise UserError('ต้องระบุวันที่กลับรายการ')
        # ล็อกแถวก่อนอ่านสถานะ: กดซ้ำ/สองคนพร้อมกันจะไม่ได้รายการกลับสองใบ
        self.env.cr.execute(
            'SELECT id FROM npd_payroll_account_move WHERE id = %s FOR UPDATE',
            [self.id])
        self.invalidate_recordset()
        link = self.sudo()
        if link.state != 'posted':
            raise UserError('รายการนี้กลับรายการไปแล้ว')
        move = link.move_id.sudo().with_company(link.company_id)
        reversal = self.env['account.move']
        # ฝ่ายบัญชีกด "กลับรายการ" มาตรฐานของ Odoo ไปเองแล้ว รายการนั้นถูกจับคู่กับ
        # ใบกลับรายการจนเช็คข้างล่างเข้าใจผิดว่าถูกจ่ายเงินแล้ว ถ้าไม่รับรู้ตรงนี้
        # งวดนี้จะค้างลงใหม่ไม่ได้ตลอดไป จึงผูกใบกลับที่มีอยู่แทนการกลับซ้ำ
        existing_rev = move.reversal_move_ids.filtered(lambda m: m.state == 'posted')[:1]
        if move.state == 'posted' and existing_rev:
            reversal = existing_rev
        elif move.state == 'posted':
            matched = move.line_ids.filtered(
                lambda line: line.matched_debit_ids or line.matched_credit_ids)
            if matched:
                raise UserError(
                    'เงินเดือนค้างจ่ายถูกจับคู่กับรายการจ่ายเงินแล้ว '
                    'ต้องยกเลิกการจับคู่ก่อน (รายการ %s)' % move.name)
            lock_message = Config._npd_lock_message(
                link.company_id, date, action='กลับรายการเงินเดือน')
            if lock_message:
                raise UserError(lock_message)
            ref = 'กลับรายการ %s: %s' % (move.name, reason or '')
            reversal = move._reverse_moves(
                [{'date': date, 'ref': ref.strip()}], cancel=True)
        elif move.state == 'draft':
            # มีคนดึงรายการกลับเป็นร่างเองแล้ว ไม่มีอะไรให้กลับ แค่ยกเลิกทิ้ง
            move.button_cancel()
        link.write({
            'state': 'reversed',
            'reversal_move_id': reversal[:1].id or False,
            'reversed_date': date,
            'reversed_uid': self.env.uid,
            'reverse_reason': reason or False,
        })
        link.period_id.sudo()._message_log(body=(
            'กลับรายการบัญชีเงินเดือนบริษัท %s (%s) วันที่ %s%s' % (
                link.company_id.name, move.name or '',
                date.strftime('%d/%m/%Y'),
                (' เหตุผล: %s' % reason) if reason else '')))
        return reversal
