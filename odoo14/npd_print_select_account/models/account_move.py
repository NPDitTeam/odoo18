# -*- coding: utf-8 -*-
"""ปุ่ม "อัพเดท" บนใบแจ้งหนี้ — ดึงรายการแตกหักเสียหายมาเป็นบรรทัดในใบ

พอร์ตจาก Odoo 14 ``npd_print_select_account`` โดยแก้จุดที่ o18 ต่างออกไป
และรวมการแก้บั๊ก "ดึงสินค้ามาทั้งฐาน" ที่เจอบน o14 เข้ามาด้วย
"""
import logging

from odoo import api, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# ประเภทสินค้า -> (รหัสบัญชีรายได้, ชื่อบัญชีวิเคราะห์, ชื่อสมุดรายวัน)
PENALTY_SETUP = {
    'สินค้าหาย': ('4100-03', 'L', 'สมุดรายวันค่าปรับหาย'),
    'สินค้าชำรุด': ('4100-05', 'D', 'สมุดรายวันค่าปรับชำรุด'),
}
RENT_DIFF_REASON = 'ค่าเช่าส่วนต่าง'
RENT_DIFF_PRODUCT = 'PR/01363'
RENT_DIFF_ACCOUNT = '4100-01'
RENT_DIFF_JOURNAL = 'สมุดรายวันเช่า(สาขา)'
UNDUE_VAT_TAX = 'ภาษีขายยังไม่ถึงกำหนด Vat 7%'
# สถานะของรายการแตกหักเสียหายที่ถือว่า "เกิดขึ้นจริงแล้ว"
# ไม่รวม repaired เพราะซ่อมสำเร็จแล้วจะคืนสต๊อก ไม่ต้องเรียกเก็บ
SCRAP_STATES = ('done', 'pending_repair', 'under_repair')


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ------------------------------------------------------------------
    # ตัวช่วยค้นของ "ตามบริษัทของใบนี้"
    # o18 เก็บทุกบริษัทไว้ในฐานเดียว ถ้าค้นด้วยชื่อเฉย ๆ จะได้ของบริษัทอื่นมา
    # ------------------------------------------------------------------
    def _psa_company(self):
        return self.company_id or self.env.company

    def _psa_journal(self, journal_name):
        company = self._psa_company()
        return self.env['account.journal'].search([
            ('name', '=', journal_name),
            ('company_id', '=', company.id),
        ], limit=1)

    def _psa_account(self, code):
        company = self._psa_company()
        return self.env['account.account'].with_company(company).search([
            ('code', '=', code),
            ('company_ids', 'in', company.id),
        ], limit=1)

    def _psa_undue_vat_tax(self):
        company = self._psa_company()
        return self.env['account.tax'].search([
            ('name', '=', UNDUE_VAT_TAX),
            ('type_tax_use', '=', 'sale'),
            ('company_id', '=', company.id),
        ], limit=1)

    def _psa_analytic_distribution(self, analytic_name):
        """o18 ไม่มี analytic tag แล้ว — ถ้ามีบัญชีวิเคราะห์ชื่อนี้ก็ลงให้ 100%
        ถ้ายังไม่ได้ตั้ง (ตอนนี้ยังไม่มีในระบบ) ก็ข้ามไป ไม่ทำให้ปุ่มพัง"""
        if not analytic_name:
            return False
        analytic = self.env['account.analytic.account'].search([
            ('name', '=', analytic_name),
        ], limit=1)
        return {str(analytic.id): 100.0} if analytic else False

    # ------------------------------------------------------------------
    # เลือกประเภทสินค้า -> ตั้งสมุดรายวันให้ตรง
    # ------------------------------------------------------------------
    @api.onchange('reason_code_id')
    def _onchange_reason_code_id(self):
        if self.move_type == 'out_refund' or not self.reason_code_id:
            return
        reason = self.reason_code_id.name
        if reason in PENALTY_SETUP:
            journal_name = PENALTY_SETUP[reason][2]
        elif reason == RENT_DIFF_REASON:
            journal_name = RENT_DIFF_JOURNAL
        else:
            return
        journal = self._psa_journal(journal_name)
        if not journal:
            raise UserError(
                "ไม่พบสมุดรายวัน '%s' ของ%s กรุณาตรวจสอบการตั้งค่าในระบบบัญชี"
                % (journal_name, self._psa_company().display_name)
            )
        self.journal_id = journal.id

    # ------------------------------------------------------------------
    # ปุ่ม "อัพเดท"
    # ------------------------------------------------------------------
    def action_update_fields(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError('ใบนี้ไม่ได้อยู่สถานะร่างแล้ว จึงอัพเดทรายการสินค้าไม่ได้')
        if not self.reason_code_id:
            raise UserError('กรุณาเลือก "ประเภทสินค้า" ก่อนกดอัพเดท')

        reason = self.reason_code_id.name
        if reason == RENT_DIFF_REASON:
            lines = self._psa_rent_diff_lines()
        elif reason in PENALTY_SETUP:
            lines = self._psa_penalty_lines(reason)
        else:
            raise UserError(
                "ประเภทสินค้า '%s' ไม่รองรับการอัพเดทอัตโนมัติ "
                "(รองรับเฉพาะ สินค้าหาย / สินค้าชำรุด / ค่าเช่าส่วนต่าง)" % reason
            )

        # ล้างของเดิมแล้วใส่ชุดใหม่ — o18 คำนวณภาษี/บรรทัดคู่ให้เองตอนเขียน
        self.write({'invoice_line_ids': [(5, 0, 0)]})
        self.write({'invoice_line_ids': lines})
        self._psa_update_partner()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def _psa_rent_diff_lines(self):
        """ค่าเช่าส่วนต่าง — สินค้าตัวเดียว 1 บรรทัด"""
        product = self.env['product.product'].search([
            ('default_code', '=', RENT_DIFF_PRODUCT),
        ], limit=1)
        if not product:
            raise UserError("ไม่พบรหัสสินค้า %s ในระบบ" % RENT_DIFF_PRODUCT)

        account = self._psa_account(RENT_DIFF_ACCOUNT)
        if not account:
            raise UserError(
                "ไม่พบบัญชีรหัส '%s' ของ%s" % (RENT_DIFF_ACCOUNT, self._psa_company().display_name)
            )
        tax = self._psa_undue_vat_tax()
        if not tax:
            raise UserError(
                "ไม่พบภาษี '%s' ของ%s" % (UNDUE_VAT_TAX, self._psa_company().display_name)
            )
        return [(0, 0, {
            'product_id': product.id,
            'name': product.name,
            'quantity': 1.0,
            'price_unit': product.lst_price or 1.0,
            'account_id': account.id,
            'tax_ids': [(6, 0, tax.ids)],
        })]

    def _psa_source_pickings(self):
        """ใบส่งสินค้า + ใบคืน ที่เกี่ยวกับเอกสารต้นทางของใบแจ้งหนี้นี้

        ต้องเก็บ "ทุกใบ" ห้ามใช้ limit=1 — ถ้า SO หนึ่งใบมีใบส่งหลายใบแล้วสุ่มได้
        ใบที่ยังไม่มีใบคืน ตัวแปรจะว่าง ทำให้ไปค้น scrap ด้วย picking_id = False
        ซึ่งแมตช์รายการแตกหักเสียหายที่ไม่มีใบส่งทั้งฐาน (บั๊กที่เจอบน o14)
        """
        Picking = self.env['stock.picking']
        origin_ref = self.invoice_origin
        if not origin_ref:
            raise UserError(
                'ใบนี้ไม่มีเอกสารต้นทาง (Source Document) จึงดึงรายการแตกหักเสียหายไม่ได้'
            )
        pickings = Picking.search([
            '&', ('company_id', '=', self._psa_company().id),
            '|', ('name', '=', origin_ref), ('origin', '=', origin_ref),
        ])
        if pickings:
            return_origins = []
            for pick in pickings:
                return_origins += [
                    'Return of %s' % pick.name,
                    'การส่งคืนของ %s' % pick.name,
                    'Returned from %s' % pick.name,
                ]
            pickings |= Picking.search([('origin', 'in', return_origins)])
        if not pickings:
            raise UserError(
                'ไม่พบใบส่งสินค้า/ใบคืนสินค้าที่อ้างถึงเอกสาร %s '
                'กรุณาตรวจสอบว่ามีการส่งหรือคืนสินค้าของเอกสารนี้แล้วหรือยัง' % origin_ref
            )
        return pickings

    def _psa_penalty_lines(self, reason):
        """สินค้าหาย / สินค้าชำรุด — ดึงจากรายการแตกหักเสียหายของใบส่ง-ใบคืน"""
        account_code, analytic_name, dummy_journal = PENALTY_SETUP[reason]
        account = self._psa_account(account_code)
        if not account:
            raise UserError(
                "ไม่พบบัญชีรหัส '%s' ของ%s กรุณาตรวจสอบผังบัญชี"
                % (account_code, self._psa_company().display_name)
            )

        pickings = self._psa_source_pickings()
        scraps = self.env['stock.scrap'].search([
            ('picking_id', 'in', pickings.ids),
            ('reason_code_id', '=', self.reason_code_id.id),
            ('state', 'in', list(SCRAP_STATES)),
        ])
        if not scraps:
            raise UserError(
                'ไม่พบข้อมูลในรายการแตกหักเสียหายของ %s\n'
                'โปรดตรวจสอบว่าสถานะเป็น "เสร็จสิ้น", "รอดำเนินการแจ้งซ่อม" '
                'หรือ "อยู่ระหว่างการซ่อม" และเลือกประเภทสินค้าเป็น "%s" แล้วหรือยัง'
                % (self.invoice_origin, reason)
            )
        _logger.info('[อัพเดทค่าปรับ] %s: ใบส่ง/ใบคืน %s -> รายการแตกหักเสียหาย %d รายการ',
                     self.display_name, pickings.mapped('name'), len(scraps))

        # รวมจำนวนของสินค้าตัวเดียวกัน
        grouped = {}
        for scrap in scraps:
            if not scrap.product_id:
                raise UserError('มีรายการแตกหักเสียหายที่ไม่ได้ระบุสินค้า กรุณาตรวจสอบ')
            grouped.setdefault(scrap.product_id, 0.0)
            grouped[scrap.product_id] += scrap.scrap_qty

        analytic = self._psa_analytic_distribution(analytic_name)
        tax = self._psa_undue_vat_tax() if reason == 'สินค้าหาย' else False
        if reason == 'สินค้าหาย' and not tax:
            raise UserError(
                "ไม่พบภาษี '%s' ของ%s กรุณาตรวจสอบการตั้งค่าภาษี"
                % (UNDUE_VAT_TAX, self._psa_company().display_name)
            )

        lines = []
        for product, quantity in grouped.items():
            vals = {
                'product_id': product.id,
                'name': product.name,
                'quantity': quantity,
                'price_unit': product.lst_price or 1.0,
                'account_id': account.id,
                'tax_ids': [(6, 0, tax.ids)] if tax else [(5, 0, 0)],
            }
            if analytic:
                vals['analytic_distribution'] = analytic
            lines.append((0, 0, vals))
        return lines

    def _psa_update_partner(self):
        """ใบค่าปรับต้องออกในชื่อผู้รับสินค้า (สาขาที่ทำของหาย/ชำรุด)

        o14 มี commit ซ่อนอยู่ในเมธอดนี้ ทำให้ผู้ใช้กดยกเลิกไม่ได้จริง — ตัดออก
        """
        if self.partner_shipping_id and self.partner_id != self.partner_shipping_id:
            self.partner_id = self.partner_shipping_id.id
