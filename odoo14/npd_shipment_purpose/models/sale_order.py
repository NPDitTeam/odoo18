# -*- coding: utf-8 -*-
"""ประเภทการจัดส่งสินค้า + หมายเหตุ (ให้ AI ตรวจ) บนใบสั่งขาย — ฝั่ง Odoo 18

ตัวเดียวกับโมดูล npd_shipment_purpose ของ Odoo 14 แต่ปรับให้เข้ากับ o18
* o18 ใช้ source_company_id (บริษัทต้นทางในฐานเดียวกัน) แทน database_selection ของ o14
* วิว o18 ใช้ readonly/required/invisible ตรง ๆ ไม่ใช่ attrs
* ใบโยกสินค้า (stock.api.transfer) อยู่ฐานเดียวกัน จับคู่ด้วย source_company_id
"""
import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

PURPOSE_NEED_SO = ('to_customer', 'from_customer')
PURPOSE_NO_REF = ('help_branch',)

PURPOSE_LABELS = {
    'to_customer': 'จัดส่งสินค้าไปยังลูกค้า',
    'from_customer': 'รับสินค้าจากลูกค้ามายังสาขา',
    'branch_transfer': 'โยกสินค้าจากสาขา ไปสาขา',
    'help_branch': 'ส่งรถไปช่วยขนส่งอีกสาขา',
}

PURPOSE_TO_DELIVERY_TYPE = {
    'to_customer': 'customer',
    'from_customer': 'branch',
    'branch_transfer': 'branch_transfer',
    'help_branch': 'help_branch',
}


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # ทั้งหมดนี้เป็นงานของฝ่ายขนส่ง จึงบังคับเฉพาะใบของบริษัท เอ็นพีดี โลจิสติกส์
    # (ใช้ธงเดียวกับปุ่ม "ดึงข้อมูลการเช่า" / "ส่งไปยังระบบขนส่ง")
    def _sp_is_logistics(self):
        self.ensure_one()
        if 'is_npd_logistics_company' in self._fields:
            return bool(self.is_npd_logistics_company)
        if 'tr_is_npd_logistics' in self._fields:
            return bool(self.tr_is_npd_logistics)
        return True

    shipment_purpose = fields.Selection(
        selection=[
            ('to_customer', 'จัดส่งสินค้าไปยังลูกค้า'),
            ('from_customer', 'รับสินค้าจากลูกค้ามายังสาขา'),
            ('branch_transfer', 'โยกสินค้าจากสาขา ไปสาขา'),
            ('help_branch', 'ส่งรถไปช่วยขนส่งอีกสาขา'),
        ],
        string='ประเภทการจัดส่งสินค้า',
        tracking=True,
        copy=False,
    )

    delivery_type = fields.Selection(
        selection_add=[
            ('branch_transfer', 'โยกสินค้าจากสาขา ไปสาขา'),
            ('help_branch', 'ส่งรถไปช่วยขนส่งอีกสาขา'),
        ],
        ondelete={'branch_transfer': 'set default', 'help_branch': 'set default'},
    )

    transfer_ref_id = fields.Many2one(
        'stock.api.transfer',
        string='เลขโยกสินค้า',
        copy=False,
        index=True,
        help='เลือกได้เฉพาะใบโยกที่ "ยืนยันแล้ว" ของบริษัทต้นทางที่เลือกไว้ และยังไม่ถูกใบสั่งขายอื่นใช้',
    )
    used_transfer_ids = fields.Many2many(
        'stock.api.transfer',
        string='ใบโยกที่ถูกใช้ไปแล้ว',
        compute='_compute_used_transfer_ids',
    )
    transfer_product_summary = fields.Text(
        string='สินค้าที่โยก', compute='_compute_transfer_product_summary',
    )

    shipment_note = fields.Text(string='หมายเหตุ', copy=False)
    shipment_note_ai_state = fields.Selection([
        ('pending', 'ยังไม่ผ่านการตรวจ'),
        ('ok', 'AI ตรวจแล้ว ตรงกัน'),
        ('skipped', 'ข้ามการตรวจ (AI ไม่พร้อมใช้งาน)'),
    ], string='ผลตรวจหมายเหตุ', readonly=True, copy=False)
    shipment_note_ai_feedback = fields.Text(string='ความเห็นของ AI', readonly=True, copy=False)

    # ------------------------------------------------------------------
    @api.depends('transfer_ref_id')
    def _compute_used_transfer_ids(self):
        used = self.sudo().search([
            ('transfer_ref_id', '!=', False),
            ('state', '!=', 'cancel'),
        ])
        for order in self:
            others = used.filtered(lambda o, cur=order: o.id != cur.id and o._origin.id != cur._origin.id)
            order.used_transfer_ids = others.mapped('transfer_ref_id')

    @api.depends('transfer_ref_id')
    def _compute_transfer_product_summary(self):
        for order in self:
            lines = order.transfer_ref_id.line_ids if order.transfer_ref_id else False
            if not lines:
                order.transfer_product_summary = ''
                continue
            order.transfer_product_summary = '\n'.join(
                '• %s  จำนวนขอตัด %s' % (line.product_id.display_name or '-', line.request_qty)
                for line in lines
            )

    # ------------------------------------------------------------------
    @api.onchange('shipment_purpose')
    def _onchange_shipment_purpose(self):
        for order in self:
            purpose = order.shipment_purpose
            if not purpose:
                continue
            order.delivery_type = PURPOSE_TO_DELIVERY_TYPE.get(purpose, order.delivery_type)
            if purpose in PURPOSE_NO_REF:
                order.so_number = False
                order.transfer_ref_id = False
                if 'source_company_id' in order._fields:
                    order.source_company_id = False
            elif purpose == 'branch_transfer':
                order.so_number = order.transfer_ref_id.name or False
            else:
                order.transfer_ref_id = False

    @api.onchange('transfer_ref_id')
    def _onchange_transfer_ref_id(self):
        for order in self:
            if order.shipment_purpose == 'branch_transfer':
                order.so_number = order.transfer_ref_id.name or False

    def _sync_shipment_purpose_fields(self, vals):
        purpose = vals.get('shipment_purpose')
        if not purpose:
            return vals
        vals = dict(vals)
        vals['delivery_type'] = PURPOSE_TO_DELIVERY_TYPE.get(purpose, vals.get('delivery_type'))
        if purpose in PURPOSE_NO_REF:
            vals.update({'so_number': False, 'transfer_ref_id': False})
            if 'source_company_id' in self._fields:
                vals['source_company_id'] = False
        return vals

    # ------------------------------------------------------------------
    @api.constrains('shipment_purpose', 'so_number', 'transfer_ref_id')
    def _check_shipment_purpose_refs(self):
        for order in self:
            if not order._sp_is_logistics():
                continue
            purpose = order.shipment_purpose
            if not purpose:
                continue
            source_company = order.source_company_id if 'source_company_id' in order._fields else False
            if purpose in PURPOSE_NEED_SO:
                missing = []
                if 'source_company_id' in order._fields and not source_company:
                    missing.append('ดึงข้อมูลการเช่าจาก บ.อื่น')
                if not order.so_number:
                    missing.append('เลขเอกสาร SO')
                if missing:
                    raise ValidationError(_(
                        'ประเภทการจัดส่งสินค้า "%s" ต้องระบุ: %s'
                    ) % (PURPOSE_LABELS[purpose], ' และ '.join(missing)))
            elif purpose == 'branch_transfer':
                if not order.transfer_ref_id:
                    raise ValidationError(_(
                        'ประเภทการจัดส่งสินค้า "%s" ต้องเลือกเลขโยกสินค้า '
                        '(เฉพาะใบที่สถานะ "ยืนยันแล้ว")'
                    ) % PURPOSE_LABELS[purpose])
                if order.transfer_ref_id.state != 'confirmed':
                    raise ValidationError(_(
                        'ใบโยกสินค้า %s ยังไม่อยู่สถานะ "ยืนยันแล้ว"'
                    ) % order.transfer_ref_id.name)

    @api.constrains('transfer_ref_id')
    def _check_transfer_ref_unique(self):
        """เลขโยกสินค้าหนึ่งใบ ใช้ได้กับใบสั่งขายเดียวเท่านั้น"""
        for order in self.filtered('transfer_ref_id'):
            if not order._sp_is_logistics():
                continue
            other = self.sudo().search([
                ('id', '!=', order.id),
                ('transfer_ref_id', '=', order.transfer_ref_id.id),
                ('state', '!=', 'cancel'),
            ], limit=1)
            if other:
                raise ValidationError(_(
                    'เลขโยกสินค้า %s ถูกใช้ไปแล้วในใบสั่งขาย %s'
                ) % (order.transfer_ref_id.name, other.name))

    def action_confirm(self):
        for order in self:
            if not order._sp_is_logistics():
                continue
            if not order.shipment_purpose:
                raise ValidationError(_('กรุณาเลือก "ประเภทการจัดส่งสินค้า" ก่อนยืนยันใบสั่งขาย'))
            if not (order.shipment_note or '').strip():
                raise ValidationError(_('กรุณากรอก "หมายเหตุ" ให้สอดคล้องกับประเภทการจัดส่งสินค้า'))
        return super().action_confirm()

    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._sync_shipment_purpose_fields(vals) for vals in vals_list]
        orders = super().create(vals_list)
        orders._run_shipment_note_ai_check()
        return orders

    def write(self, vals):
        vals = self._sync_shipment_purpose_fields(vals)
        res = super().write(vals)
        if 'shipment_note' in vals or 'shipment_purpose' in vals:
            self._run_shipment_note_ai_check()
        return res

    def _run_shipment_note_ai_check(self):
        """AI อ่านหมายเหตุเทียบกับประเภทที่เลือก — ไม่ตรง/คลุมเครือ = บันทึกไม่ผ่าน
        ถ้า AI ใช้งานไม่ได้จะไม่บล็อก (งานขนส่งต้องเดินต่อได้)"""
        gemini = self.env['npd.ai.it.gemini']
        for order in self:
            if not order._sp_is_logistics():
                continue
            purpose = order.shipment_purpose
            note = (order.shipment_note or '').strip()
            if not purpose or not note:
                continue
            if not gemini.is_available():
                order._write_ai_result('skipped', 'ยังไม่ได้ตั้งค่า Gemini API key จึงข้ามการตรวจ')
                continue

            result = gemini.extract_json(order._build_note_ai_prompt(purpose, note), max_output_tokens=512)
            if not result or 'match' not in result:
                order._write_ai_result('skipped', 'เรียก AI ไม่สำเร็จ จึงข้ามการตรวจรอบนี้')
                continue

            reason = (result.get('reason') or '').strip()
            if result.get('match') and result.get('clear', True):
                order._write_ai_result('ok', reason or 'หมายเหตุสอดคล้องกับประเภทการจัดส่งสินค้า')
                continue

            order._write_ai_result('pending', reason)
            raise ValidationError(_(
                'หมายเหตุไม่สอดคล้องกับประเภทการจัดส่งสินค้าที่เลือก\n\n'
                'ประเภทที่เลือก: %s\n'
                'หมายเหตุที่กรอก: %s\n\n'
                'AI ตรวจแล้วพบว่า: %s\n\n'
                'กรุณาแก้หมายเหตุให้ตรงกับงานที่จะทำจริง แล้วบันทึกอีกครั้ง'
            ) % (PURPOSE_LABELS.get(purpose, purpose), note,
                 reason or 'เนื้อความไม่ตรงกับประเภทที่เลือก หรืออ่านแล้วไม่ชัดเจน'))

    def _write_ai_result(self, state, feedback):
        self.ensure_one()
        self.env.cr.execute(
            'UPDATE sale_order SET shipment_note_ai_state = %s, shipment_note_ai_feedback = %s WHERE id = %s',
            (state, feedback or None, self.id),
        )
        self.invalidate_recordset(['shipment_note_ai_state', 'shipment_note_ai_feedback'])

    def _build_note_ai_prompt(self, purpose, note):
        return (
            'คุณคือผู้ตรวจเอกสารงานขนส่งของบริษัทให้เช่าอุปกรณ์ก่อสร้าง\n'
            'พนักงานเลือก "ประเภทการจัดส่งสินค้า" ไว้ แล้วพิมพ์ "หมายเหตุ" อธิบายงาน\n'
            'ให้ตรวจว่าหมายเหตุอธิบายงานแบบเดียวกับประเภทที่เลือกหรือไม่ และอ่านแล้วเข้าใจหรือไม่\n\n'
            'ความหมายของแต่ละประเภท\n'
            '- จัดส่งสินค้าไปยังลูกค้า: เอาของจากสาขาไปส่งให้ลูกค้า\n'
            '- รับสินค้าจากลูกค้ามายังสาขา: ไปรับของคืนจากลูกค้ากลับเข้าสาขา\n'
            '- โยกสินค้าจากสาขา ไปสาขา: ย้ายของระหว่างสาขาของบริษัทเอง ไม่เกี่ยวกับลูกค้า\n'
            '- ส่งรถไปช่วยขนส่งอีกสาขา: ให้ยืมรถ/คนขับไปช่วยงานของสาขาอื่น\n\n'
            'ประเภทที่เลือก: %s\n'
            'หมายเหตุของพนักงาน: %s\n\n'
            'ตอบกลับเป็น JSON เท่านั้น รูปแบบ\n'
            '{"match": true, "clear": true, "reason": "เหตุผลสั้น ๆ ภาษาไทย ไม่เกิน 2 บรรทัด"}\n'
            'match = หมายเหตุไปทางเดียวกับประเภทที่เลือก\n'
            'clear = อ่านแล้วเข้าใจว่าจะไปทำอะไร ที่ไหน (ไม่ใช่ข้อความมั่ว เช่น "-", "ทดสอบ", "asdf")\n'
            'ถ้า match เป็น false ให้บอกในเหตุผลว่าหมายเหตุดูเหมือนงานประเภทใดมากกว่า'
        ) % (PURPOSE_LABELS.get(purpose, purpose), note)
