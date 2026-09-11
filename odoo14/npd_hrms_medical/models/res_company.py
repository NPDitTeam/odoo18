# -*- coding: utf-8 -*-
"""ค่าตั้งต้นของค่ารักษาพยาบาลรายบริษัท

Odoo 14 เก็บค่าพวกนี้ในตาราง medical.expense.voucher.config ที่อ้าง id ข้าม DB
(คนละ DB ต่อบริษัท) — Odoo 18 อยู่ DB เดียว จึงเป็นฟิลด์ Many2one ธรรมดาบน
res.company อยู่แท็บ "นโยบายระบบบุคคล" รวมกับนโยบาย HR อื่น ๆ
"""
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)

MEDICAL_REASON_CODE = 'medical_expense'
MEDICAL_REASON_NAME = 'ค่ารักษาพยาบาล'
MEDICAL_SEQUENCE_CODE = 'hrms.medical.voucher'
DEFAULT_ANNUAL_LIMIT = 10000.0


class ResCompany(models.Model):
    _inherit = 'res.company'

    hrms_medical_annual_limit = fields.Float(
        string='วงเงินค่ารักษาพยาบาลต่อปี (บาท)', default=DEFAULT_ANNUAL_LIMIT,
        help='วงเงินมาตรฐานของพนักงานทุกคนในบริษัทนี้ นับใหม่ทุกปีตามปีของวันที่ในคำขอ\n'
             'ตั้งเฉพาะรายคนได้ที่ ระบบบุคคล > ค่ารักษาพยาบาล > วงเงินรายบุคคล')

    # ---- ใบสำคัญจ่ายที่สร้างตอนอนุมัติ ----
    hrms_medical_account_id = fields.Many2one(
        'account.account', string='บัญชีค่ารักษาพยาบาล',
        help='ขาเดบิตของรายการบัญชี เช่น 5310-11 ค่าสวัสดิการรักษาพยาบาล')
    hrms_medical_payment_method_id = fields.Many2one(
        'custom.payment.method', string='วิธีจ่ายเงิน (Payment Method)',
        help='บัญชีธนาคารที่โอนเงินให้พนักงาน — ขาเครดิตของรายการบัญชี')
    hrms_medical_journal_id = fields.Many2one(
        'account.journal', string='สมุดรายวันใบสำคัญจ่าย',
        help='เว้นว่าง = ใช้เล่มเริ่มต้นของใบสำคัญจ่าย '
             '(ตั้งที่ การขาย > การกำหนดค่า > สมุดรายวันออกใบแจ้งหนี้)')
    hrms_medical_sequence_id = fields.Many2one(
        'ir.sequence', string='เลขที่ใบสำคัญจ่าย',
        help='เว้นว่าง = ใช้เลขชุดของโมดูลใบสำคัญ (PA… "คืนเงินประกันค่าเช่า" ใช้ร่วมทุกบริษัท)')
    hrms_medical_branch_id = fields.Many2one(
        'res.branch', string='สาขาเริ่มต้น',
        help='ใช้เมื่อพนักงานไม่มีสาขา — ปกติใบสำคัญจ่ายลงสาขาของพนักงาน')
    hrms_medical_analytic_id = fields.Many2one(
        'account.analytic.account', string='บัญชีวิเคราะห์',
        help='ฝ่ายบัญชีให้ลงสำนักงานใหญ่ที่เดียว เพราะเป็นสวัสดิการระดับบริษัท — เว้นว่างได้')
    hrms_medical_product_id = fields.Many2one(
        'product.product', string='สินค้า/บริการในบรรทัด', help='ไม่บังคับ')
    hrms_medical_reference = fields.Char(
        string='Bill Reference', default='เบิกค่ารักษาพยาบาล')
    hrms_medical_line_label = fields.Char(
        string='ชื่อรายการในบรรทัด', default='ค่าสวัสดิการรักษาพยาบาล')

    # ------------------------------------------------------------------
    # ตั้งค่าอัตโนมัติ
    # ------------------------------------------------------------------
    def action_hrms_medical_autoconfigure(self):
        self._hrms_medical_setup()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': 'ตั้งค่าค่ารักษาพยาบาลแล้ว',
                'message': 'เติมเฉพาะช่องที่ยังว่าง — ตรวจทานบัญชีและวิธีจ่ายเงินอีกครั้ง',
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def _hrms_medical_setup(self):
        """ประเภทคำขอ + ค่าตั้งต้นของใบสำคัญจ่าย — เติมเฉพาะที่ยังว่าง รันซ้ำได้"""
        Reason = self.env['hrms.manual.time.reason'].sudo().with_context(active_test=False)
        for company in self.sudo():
            reasons = Reason.search([
                ('company_id', '=', company.id),
                '|', ('code', '=', MEDICAL_REASON_CODE), ('name', '=', MEDICAL_REASON_NAME),
            ])
            if reasons:
                # จ่ายผ่านใบสำคัญจ่ายแล้ว ต้องเลิกส่งยอดเข้าสลิป ไม่งั้นได้เงินสองรอบ
                reasons.write({'hrms_is_medical': True, 'payroll_income_field': False})
            else:
                Reason.create({
                    'name': MEDICAL_REASON_NAME,
                    'code': MEDICAL_REASON_CODE,
                    'sequence': 70,
                    'company_id': company.id,
                    'requires_amount': True,
                    'requires_attachment': True,
                    'hrms_is_medical': True,
                })

            vals = {}
            if not company.hrms_medical_account_id:
                account = company._hrms_medical_guess_account()
                if account:
                    vals['hrms_medical_account_id'] = account.id
            if not company.hrms_medical_payment_method_id:
                method = company._hrms_medical_guess_payment_method()
                if method:
                    vals['hrms_medical_payment_method_id'] = method.id
            if not company.hrms_medical_branch_id:
                branch = company._hrms_medical_guess_branch()
                if branch:
                    vals['hrms_medical_branch_id'] = branch.id
            if not company.hrms_medical_sequence_id:
                vals['hrms_medical_sequence_id'] = company._hrms_medical_get_sequence().id
            if vals:
                company.write(vals)
            _logger.info('HRMS medical setup [%s]: เติม %s', company.name, sorted(vals))
            if not (company.hrms_medical_account_id and company.hrms_medical_payment_method_id):
                _logger.warning('HRMS medical setup [%s]: ยังขาดบัญชีหรือวิธีจ่ายเงิน '
                                '— ต้องตั้งเองที่หน้าบริษัท', company.name)

    def _hrms_medical_guess_account(self):
        """บัญชี 5310-xx ที่ชื่อมีคำว่า "รักษาพยาบาล" เลขน้อยสุด

        ผังบัญชีที่ย้ายมาจาก Odoo 14 ส่วนใหญ่เป็น 5310-11 แต่เอส กรุ๊ปเป็น 5310-17
        จึงหาจากชื่อแทนการ fix เลข
        """
        self.ensure_one()
        accounts = self.env['account.account'].sudo().with_company(self).search([
            ('company_ids', 'in', self.id),
            ('deprecated', '=', False),
        ])
        matches = accounts.filtered(
            lambda a: (a.code or '').startswith('5310-')
            and 'รักษาพยาบาล' in (a.with_context(lang='th_TH').name or a.name or ''))
        return matches.sorted(lambda a: a.code)[:1]

    def _hrms_medical_guess_payment_method(self):
        """โอนผ่าน KBANK ตัวแรกของบริษัท — ตรงกับที่ฝ่ายบัญชีใช้เบิกค่ารักษาใน Odoo 14"""
        self.ensure_one()
        return self.env['custom.payment.method'].sudo().search([
            ('company_id', '=', self.id),
            ('type', '=', 'bank'),
            ('name', 'ilike', 'KBANK'),
            ('is_active', '=', True),
        ], order='id', limit=1)

    def _hrms_medical_guess_branch(self):
        self.ensure_one()
        Branch = self.env['res.branch'].sudo().with_context(bypass_branch_company_filter=True)
        return (
            Branch.search([('hr_is_head_office', '=', True),
                           ('company_ids', 'in', self.id)], limit=1)
            or Branch.search([('name', '=', 'สำนักงานใหญ่'),
                              ('company_ids', 'in', self.id)], limit=1)
        )

    def _hrms_medical_get_sequence(self):
        """เลขที่ใบสำคัญจ่ายค่ารักษาพยาบาล รูปแบบเดียวกับ Odoo 14 (CP-260811-0004)

        Odoo 18 มีลำดับ purchase.receipt ตัวเดียว (PA… ชื่อ "คืนเงินประกันค่าเช่า")
        ใช้ร่วมทุกบริษัท — ถ้าไม่แยก ใบค่ารักษาพยาบาลจะได้เลขชุดคืนเงินประกัน
        """
        self.ensure_one()
        Sequence = self.env['ir.sequence'].sudo()
        sequence = Sequence.search([
            ('code', '=', MEDICAL_SEQUENCE_CODE), ('company_id', '=', self.id)], limit=1)
        if not sequence:
            sequence = Sequence.create({
                'name': 'ใบสำคัญจ่ายค่ารักษาพยาบาล - %s' % self.name,
                'code': MEDICAL_SEQUENCE_CODE,
                'prefix': 'CP-%(y)s%(month)s%(day)s-',
                'padding': 4,
                'company_id': self.id,
            })
        return sequence
