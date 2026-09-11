# -*- coding: utf-8 -*-
import logging

from odoo import fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class EmployeeSalary(models.Model):
    _inherit = 'employee.salary'

    hrms_partner_id = fields.Many2one(
        'res.partner', string='ผู้รับเงินในใบสำคัญจ่าย', copy=False,
        help='ผู้จำหน่ายที่ใช้ในใบสำคัญจ่ายค่ารักษาพยาบาล\n'
             'ระบบหา/สร้างให้เองตอนอนุมัติครั้งแรก (จากเลขบัตรประชาชน แล้วค่อยชื่อ-นามสกุล)\n'
             'แก้ได้ถ้าผูกผิดคน เช่น ฝ่ายบัญชีเคยสร้างไว้ด้วยชื่อสะกดต่างกัน')

    def _hrms_name_with_prefix(self):
        """ชื่อเต็มพร้อมคำนำหน้า เช่น "นางสาว ปรียดา ฤทธิ์ดี" — ใช้เป็นชื่อบัญชีธนาคาร"""
        self.ensure_one()
        prefix = ''
        if self.prefix_th:
            labels = dict(self._fields['prefix_th']._description_selection(self.env))
            prefix = labels.get(self.prefix_th) or self.prefix_th
        parts = (prefix, (self.firstname or '').strip(), (self.lastname or '').strip())
        return ' '.join(part for part in parts if part)

    def _hrms_get_payee_partner(self):
        """ผู้รับเงินของพนักงานคนนี้ ไม่เจอก็สร้างใหม่ แล้วจำไว้ที่ hrms_partner_id

        ลำดับการหา:
          1) ที่ผูกไว้แล้ว
          2) เลขผู้เสียภาษี = เลขบัตรประชาชน (กันสร้างซ้ำกับลูกค้าที่เป็นคนเดียวกัน
             — l10n_th_partner ห้าม vat+สาขาซ้ำอยู่แล้ว)
          3) ชื่อ "ชื่อ นามสกุล" ไม่มีคำนำหน้า (รูปแบบที่ฝ่ายบัญชีใช้) แล้วค่อยแบบมีคำนำหน้า
        """
        self.ensure_one()
        if self.hrms_partner_id:
            return self.hrms_partner_id
        Partner = self.env['res.partner'].sudo()
        bare_name = ' '.join(p for p in (
            (self.firstname or '').strip(), (self.lastname or '').strip()) if p)
        full_name = self._hrms_name_with_prefix()
        vat = (self.id_card_number or '').strip()

        partner = Partner.browse()
        if vat:
            partner = Partner.search([('vat', '=', vat)], limit=1)
        for name in (bare_name, full_name):
            if partner or not name:
                continue
            partner = (Partner.search([('name', '=', name), ('supplier_rank', '>', 0)], limit=1)
                       or Partner.search([('name', '=', name)], limit=1))

        if not partner:
            name = bare_name or full_name
            if not name:
                raise UserError('ไม่ทราบชื่อพนักงาน จึงระบุผู้รับเงินในใบสำคัญจ่ายไม่ได้')
            vals = {
                'name': name,
                'is_company': False,
                'supplier_rank': 1,
                'phone': (self.phone_number or '').strip() or False,
                'email': (self.email or '').strip() or False,
                'vat': vat or False,
            }
            try:
                with self.env.cr.savepoint():
                    partner = Partner.create(vals)
            except Exception as exc:
                raise UserError(
                    'สร้างผู้รับเงิน "%s" ไม่สำเร็จ: %s\n\n'
                    'เลือกผู้จำหน่ายที่ถูกต้องให้พนักงานคนนี้ที่ช่อง "ผู้รับเงินในใบสำคัญจ่าย" '
                    'ในทะเบียนพนักงาน (แท็บค่าจ้างและสิทธิประโยชน์) แล้วกดอนุมัติอีกครั้ง'
                    % (name, exc)) from exc
            _logger.info('HRMS medical: สร้างผู้รับเงินใหม่ %s (id=%s)', name, partner.id)

        self.sudo().write({'hrms_partner_id': partner.id})
        return partner
