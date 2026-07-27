import logging
from itertools import chain

from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# แปลง "ประเภทใบเสนอราคา" (pfb_so_type) เป็นกรณีการออกใบแจ้งหนี้
# ที่ตั้งสมุดรายวันได้ในเมนู npd.invoice.journal.config
SO_TYPE_JOURNAL_USAGE = {
    'sale': 'so_sale',
    'rent': 'so_rent',
}

# ใบค่าปรับมีสมุดรายวันของตัวเอง จึงต้องชนะ pfb_so_type
# ('rental' ไม่อยู่ในนี้ เพราะค่าเช่าใช้สมุดรายวันตามประเภทใบเสนอราคาตามปกติ)
DEBT_TYPE_JOURNAL_USAGE = {
    'lost': 'penalty_lost',
    'damaged': 'penalty_damaged',
}


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    rent_count = fields.Integer(string='Rent Count', readonly=True, compute="_get_rent")
    rent_ids = fields.Many2many(
        "account.move", 'sale_order_rent_ids_rel', 'sale_id', 'move_id',
        string='Rent Invoices', compute="_get_rent", readonly=True, copy=False,
    )
    rent_check = fields.Many2many(
        "account.move", 'sale_order_rent_check_rel', 'sale_id', 'move_id',
        string='Rent Check', readonly=True, copy=False,
    )
    date_order_x = fields.Date(string="Date Order", store=True)

    pfb_so_type = fields.Selection([
        ('sale', 'Sales'),
        ('rent', 'Rent')],
        string="ประเภทใบเสนอราคา",
        index=True, default='sale', required=True)

    pfb_date_of_rent = fields.Integer(string="จำนวนวันเช่า")
    pfb_objective_id = fields.Many2one('sale.objective', string="วัตถุประสงค์")
    pfb_amount_insurance = fields.Float('ค่าประกันสินค้า', compute='_compute_amount_insurance', digits=0)
    pfb_dis_amount_insurance = fields.Float('ส่วนลดค่าประกันสินค้า', digits=0)
    pfb_amount = fields.Float('ค่าประกันสุทธิ', compute='_compute_amount_insurance', digits=0, store=True)
    pfb_insurance_min = fields.Float('ค่าประกันต่ำสุดไม่เกิน', store=True)
    pfb_required_insurance_premium = fields.Float('กรอกจำนวนค่าประกันที่ต้องการ', store=True)
    pfb_amount_insurance_c = fields.Float('ค่าประกันสินค้า สำเนา', store=True)
    pfb_amount_c = fields.Float('ค่าประกันสุทธิ สำเนา', store=True)

    approver_id = fields.Many2one(
        'res.users', string="Approver", readonly=True,
        help="User who approved this order."
    )
    note_approver = fields.Text(string='Approval Note', store=True)

    # Fields from other dependency modules (fallback definitions)
    deposit_ref = fields.Char(string='Deposit Reference', copy=False)
    quotation_state = fields.Selection([
        ('draft', 'Draft'),
        ('confirm', 'Confirmed'),
    ], string='Quotation State', default='draft')
    state_sale = fields.Selection([
        ('draft', 'Draft'),
        ('waiting_to_approve', 'Waiting To Approve'),
        ('approved', 'Approved'),
        ('reject', 'Reject'),
    ], string='Approval State', default='draft')

    npd_so_type = fields.Selection([
        ('sale', 'Sales'),
        ('rent', 'Rent')],
        string="Sale Type",
        index=True, default='sale', required=True)

    total_rental_discount = fields.Float(
        string="- Rental Discount",
        compute="_compute_total_rental_discount",
        store=True
    )

    @api.depends('rent_check')
    def _get_rent(self):
        for rec in self:
            if rec.rent_check:
                rec.rent_ids = rec.rent_check
                rec.rent_count = len(rec.rent_check)
            else:
                rec.rent_ids = False
                rec.rent_count = 0

    def action_view_rent(self):
        invoices = self.rent_check
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_move_out_invoice_type")
        if len(invoices) > 1:
            action['domain'] = [('id', 'in', self.rent_check.ids)]
        elif len(invoices) == 1:
            form_view = [(self.env.ref('account.view_move_form').id, 'form')]
            if 'views' in action:
                action['views'] = form_view + [(state, view) for state, view in action['views'] if view != 'form']
            else:
                action['views'] = form_view
            action['res_id'] = invoices.id
        else:
            action = {'type': 'ir.actions.act_window_close'}

        context = {
            'default_move_type': 'out_invoice',
        }
        if len(self) == 1:
            context.update({
                'default_partner_id': self.partner_id.id,
                'default_partner_shipping_id': self.partner_shipping_id.id,
                'default_invoice_payment_term_id': (
                    self.payment_term_id.id
                    or self.partner_id.property_payment_term_id.id
                    or self.env['account.move'].default_get(['invoice_payment_term_id']).get('invoice_payment_term_id')
                ),
                'default_invoice_origin': self.name,
                'default_user_id': self.user_id.id,
            })
        action['context'] = context
        return action

    @api.onchange('pfb_required_insurance_premium')
    def _onchange_required_insurance_premium(self):
        for record in self:
            if record.state != 'draft' or record.quotation_state == 'draft':
                if not record.deposit_ref:
                    record.pfb_dis_amount_insurance = record.pfb_amount_insurance - record.pfb_required_insurance_premium
            else:
                record.pfb_amount_insurance = record.pfb_amount_insurance_c or 0.0
                record.pfb_amount = record.pfb_amount_c or 0.0

    def action_waiting_to_approve(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Select Approver'),
            'res_model': 'sale.order.approval.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_order_id': self.id,
            },
        }

    def action_update_insurance_amount(self):
        for record in self:
            if not record.deposit_ref:
                raise UserError("No value in deposit_ref field")

            so_list = [x.strip() for x in record.deposit_ref.split(",") if x.strip()]
            if not so_list:
                raise UserError("No valid SO numbers found in deposit_ref")

            source_so_name = so_list[0]
            source_so = self.env['sale.order'].search([('name', '=', source_so_name)], limit=1)
            if not source_so:
                raise UserError(f"Source SO not found: {source_so_name}")

            insurance_value = source_so.pfb_amount_insurance
            amount_value = source_so.pfb_amount

            for so_name in so_list:
                target_so = self.env['sale.order'].search([('name', '=', so_name)], limit=1)
                if target_so:
                    record.pfb_amount_insurance = insurance_value
                    record.pfb_amount = amount_value
                    record.pfb_amount_insurance_c = insurance_value
                    record.pfb_amount_c = amount_value
                    target_so.invalidate_recordset()

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Success',
                    'message': 'Insurance amount updated successfully',
                    'type': 'success',
                    'next': {
                        'type': 'ir.actions.client',
                        'tag': 'reload',
                    },
                }
            }

    @api.depends('order_line.pfb_quantity', 'order_line.pfb_insurance_price',
                 'pfb_dis_amount_insurance', 'pfb_required_insurance_premium')
    def _compute_amount_insurance(self):
        for order in self:
            if order.state != 'draft' or order.quotation_state == 'draft':
                if order.deposit_ref:
                    order.pfb_amount_insurance = order.pfb_amount_insurance_c or 0.0
                    order.pfb_amount = order.pfb_amount_c or 0.0
                else:
                    total = sum(
                        line.pfb_quantity * line.pfb_insurance_price
                        for line in order.order_line
                    )
                    order.pfb_amount_insurance = total
                    order.pfb_amount_insurance_c = total
                    order.pfb_amount = max(0, total - order.pfb_dis_amount_insurance)
                    order.pfb_amount_c = order.pfb_amount
                    order.pfb_insurance_min = total * 0.15 if total else 0.0
            else:
                order.pfb_amount_insurance = order.pfb_amount_insurance_c or 0.0
                order.pfb_amount = order.pfb_amount_c or 0.0

    @api.onchange('pfb_dis_amount_insurance')
    def _check_insurance_minimum(self):
        for record in self:
            if record.pfb_amount >= 0 and record.pfb_amount < record.pfb_insurance_min:
                return {
                    'warning': {
                        'title': _("แจ้งเตือน!"),
                        'message': _(
                            "ค่าประกันต่ำกว่าเกณฑ์ขั้นต่ำ (%.2f บาท) "
                            "กรุณาส่งคำขออนุมัติไปยังผู้จัดการ"
                        ) % record.pfb_insurance_min,
                    }
                }

    def action_confirm(self):
        res = super().action_confirm()
        for order in self:
            if order.picking_ids and order.pfb_so_type == 'rent':
                for pk in order.picking_ids:
                    for sm in pk.move_ids:
                        if sm.sale_line_id:
                            sm.product_uom_qty = sm.sale_line_id.pfb_quantity
        return res

    def _prepare_invoice(self):
        invoice_vals = super()._prepare_invoice()
        invoice_vals['pfb_so_type'] = self.pfb_so_type
        if hasattr(self, 'debt_payment_type'):
            invoice_vals['debt_payment_type'] = self.debt_payment_type
        invoice_vals['pfb_objective_id'] = self.pfb_objective_id.id
        if hasattr(self, 'contact_type') and self.contact_type:
            invoice_vals['contact_type'] = self.contact_type
        if hasattr(self, 'sales_contact') and self.sales_contact:
            invoice_vals['sales_contact'] = self.sales_contact.id
        invoice_vals['pfb_amount_insurance'] = self.pfb_amount_insurance
        invoice_vals['pfb_dis_amount_insurance'] = self.pfb_dis_amount_insurance
        invoice_vals['pfb_amount'] = self.pfb_amount

        # สมุดรายวันเริ่มต้นตามประเภทใบเสนอราคา (Sales / Rent)
        # ถ้าผู้ใช้ระบุสมุดรายวันมาที่ใบสั่งขายเองแล้ว ให้เคารพค่านั้น ไม่ทับ
        if not self.journal_id:
            journal = self._get_invoice_journal_by_so_type()
            if journal:
                invoice_vals['journal_id'] = journal.id

        return invoice_vals

    def _get_invoice_journal_by_so_type(self):
        """คืนสมุดรายวันขายเริ่มต้นของใบสั่งขายนี้ ตามค่า ``pfb_so_type``

        ตั้งค่าได้ที่เมนู การขาย > การกำหนดค่า > สมุดรายวันออกใบแจ้งหนี้

        :return: ``account.journal`` recordset ว่างถ้าหาไม่เจอ
                 (ปล่อยให้ Odoo เลือกสมุดรายวันเริ่มต้นของมันเอง)
        """
        self.ensure_one()
        # ค่าปรับหาย/ค่าปรับชำรุดมีสมุดรายวันเฉพาะ ต้องเช็คก่อนประเภทใบเสนอราคา
        debt_type = getattr(self, 'debt_payment_type', False)
        usage = DEBT_TYPE_JOURNAL_USAGE.get(debt_type or '') \
            or SO_TYPE_JOURNAL_USAGE.get(self.pfb_so_type or '')
        return self.env['npd.invoice.journal.config']._get_journal(self.company_id, usage)

    # deposit_return_status comes from npd_deposit_return_status module (Odoo 14)
    deposit_return_status = fields.Selection([
        ('not_returned', 'ลูกค้ายังไม่คืนสินค้า'),
        ('no_voucher', 'สาขายังไม่สร้างการคืนเงินประกัน'),
        ('waiting_finance', 'รอคืนเงินประกันจากการเงิน'),
        ('done', 'เสร็จสิ้น'),
    ], string='สถานะคืนเงินประกัน', tracking=True)

    # discount_amt_line comes from bi_sale_purchase_discount_with_tax module
    discount_amt_line = fields.Monetary(
        string='- Line Discount',
        store=True,
        compute='_compute_total_rental_discount',
    )

    @api.depends("order_line.discount_type_selection")
    def _compute_total_rental_discount(self):
        for order in self:
            rental_discount = 0.0
            product_discount = 0.0
            for line in order.order_line:
                discount_amount = getattr(line, 'discount_amount', 0.0) or 0.0
                if line.discount_type_selection == 'rental':
                    rental_discount += discount_amount
                elif not line.discount_type_selection or line.discount_type_selection == 'product':
                    product_discount += discount_amount
            order.total_rental_discount = rental_discount
            order.discount_amt_line = product_discount


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    pfb_so_rent_ok = fields.Boolean('Can be Rent', compute="_compute_so_rent_ok", store=True)
    pfb_date_of_rent = fields.Integer(related='order_id.pfb_date_of_rent', store=True)
    pfb_quantity = fields.Integer(string="Quantity Rent")
    pfb_insurance_price = fields.Float(string="Insurance", compute="_compute_insurance_price", store=True)
    pfb_objective_id = fields.Many2one('sale.objective', string="Objective")
    pfb_quantity_readonly = fields.Boolean(compute='_compute_quantity_readonly')
    product_uom_qty_readonly = fields.Boolean(compute='_compute_quantity_readonly')

    discount_type_selection = fields.Selection(
        [
            ('product', 'Product Discount'),
            ('rental', 'Rental Discount')
        ],
        string="Discount Type",
        default='product'
    )
    second_uom_id = fields.Many2one('uom.uom', string="Secondary UOM")
    second_uom_qty = fields.Float('Secondary Qty')

    is_manual_qty = fields.Boolean(
        string="Manual Quantity Set",
        default=False,
        copy=False,
        store=True,
    )

    product_uom_qty_npd = fields.Float(string="Qty NPD")

    def _compute_quantity_readonly(self):
        for line in self:
            line.pfb_quantity_readonly = False
            line.product_uom_qty_readonly = False

    def _prepare_invoice_line(self, **optional_values):
        vals = super()._prepare_invoice_line(**optional_values)
        vals["pfb_quantity"] = self.pfb_quantity
        vals["pfb_date_of_rent"] = self.pfb_date_of_rent
        vals["pfb_insurance_price"] = self.pfb_insurance_price
        vals["pfb_so_rent_ok"] = self.pfb_so_rent_ok
        vals["pfb_objective_id"] = self.pfb_objective_id.id
        vals["discount_type_selection"] = self.discount_type_selection

        # บัญชีรายได้ตามประเภทใบเสนอราคา / ประเภทการรับชำระหนี้
        # ตั้งค่าได้ที่ การขาย > การกำหนดค่า > สมุดรายวันออกใบแจ้งหนี้
        #
        # ต้องกำหนดตรงนี้ ไม่พึ่ง default_account_id ของสมุดรายวันแบบ Odoo 14
        # เพราะ Odoo 18 ให้บัญชีของสินค้า/ประเภทสินค้าชนะบัญชีสมุดรายวันเสมอ
        # (account_move_line._compute_account_id ใช้สมุดรายวันเป็น fallback สุดท้าย)
        order = self.order_id
        usage = DEBT_TYPE_JOURNAL_USAGE.get(getattr(order, 'debt_payment_type', False) or '') \
            or SO_TYPE_JOURNAL_USAGE.get(order.pfb_so_type or '')
        account = self.env['npd.invoice.journal.config']._get_income_account(
            order.company_id, usage,
        )
        if account:
            vals["account_id"] = account.id
        return vals

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.second_uom_qty = self.product_id.weight
        else:
            self.second_uom_qty = 0.0

    def _onchange_discount_amount(self):
        """Only active if bi_sale_purchase_discount_with_tax is installed"""
        for record in self:
            discount_amount = getattr(record, 'discount_amount', 0.0) or 0.0
            if discount_amount and record.discount_type_selection == 'product':
                max_discount = getattr(record, 'price_subtotal_without_discount', 0.0) * 0.5
                if max_discount and discount_amount > max_discount:
                    return {
                        'warning': {
                            'title': _("Warning!"),
                            'message': _(
                                "Discount cannot exceed 50%% of the product total (max {:.2f}).\n"
                                "Please send an approval request to the manager."
                            ).format(max_discount),
                        }
                    }

    @api.onchange('pfb_quantity', 'pfb_date_of_rent')
    def _onchange_rental_fields(self):
        if self.order_id.pfb_so_type == 'rent':
            self.is_manual_qty = False
            if self.pfb_date_of_rent and self.pfb_quantity:
                self.product_uom_qty = self.pfb_date_of_rent * self.pfb_quantity

    @api.onchange('product_uom_qty')
    def _onchange_product_uom_qty_check_manual(self):
        if self.order_id.pfb_so_type == 'rent' and self.pfb_date_of_rent and self.pfb_quantity:
            expected_qty = self.pfb_date_of_rent * self.pfb_quantity
            if abs(self.product_uom_qty - expected_qty) > 0.01:
                self.is_manual_qty = True

    @api.depends('product_uom_qty', 'product_id', 'order_id.pfb_date_of_rent', 'pfb_quantity', 'is_manual_qty')
    def _compute_insurance_price(self):
        for so_line in self:
            if so_line.order_id.pfb_so_type == 'rent':
                if not so_line.is_manual_qty and so_line.pfb_date_of_rent and so_line.pfb_quantity:
                    so_line.product_uom_qty = so_line.pfb_date_of_rent * so_line.pfb_quantity

            if so_line.product_id:
                insurance_price = so_line._compute_insurance_price_rule(
                    [(so_line.product_id, so_line.product_uom_qty, so_line.order_id.partner_id)],
                    date=False, uom_id=False
                )
                import logging
                _logger = logging.getLogger(__name__)
                _logger.info(
                    "[INSURANCE DEBUG] product=%s, qty=%s, pricelist=%s, insurance_price=%s",
                    so_line.product_id.display_name,
                    so_line.product_uom_qty,
                    so_line.order_id.pricelist_id.name if so_line.order_id.pricelist_id else 'NO PRICELIST',
                    insurance_price,
                )
                so_line.pfb_insurance_price = insurance_price or 0
            else:
                so_line.pfb_insurance_price = 0

            current_db = self.env.cr.dbname
            if current_db != 'NPD_Intertrading_New_NonVat':
                # The 7% taxes exist once per company, so the lookup MUST be
                # scoped to the LINE's company -- that is what _check_company
                # compares against. Never fall back to self.env.company: on an
                # unsaved order that is whatever company happens to be first in
                # allowed_company_ids, which yields another company's tax and
                # makes the record impossible to save.
                company = so_line.company_id or so_line.order_id.company_id
                tax_name = {
                    'sale': 'ภาษีขายไม่รวม Vat 7%',
                    'rent': 'ภาษีขายยังไม่ถึงกำหนด Vat 7%',
                }.get(so_line.order_id.pfb_so_type)
                if company and tax_name and so_line.product_id:
                    so_line.tax_id = self.env['account.tax'].search([
                        ('name', '=', tax_name),
                        ('company_id', '=', company.id),
                    ], limit=1)

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        for line in lines:
            if line.order_id.pfb_so_type == 'rent' and line.pfb_quantity and line.pfb_date_of_rent:
                computed_qty = line.pfb_date_of_rent * line.pfb_quantity
                line.write({
                    'product_uom_qty': computed_qty,
                    'is_manual_qty': False
                })
        return lines

    def write(self, vals):
        if 'product_uom_qty' in vals and 'is_manual_qty' not in vals:
            for line in self:
                if line.order_id.pfb_so_type == 'rent' and line.pfb_date_of_rent and line.pfb_quantity:
                    expected_qty = line.pfb_date_of_rent * line.pfb_quantity
                    if abs(vals['product_uom_qty'] - expected_qty) > 0.01:
                        vals['is_manual_qty'] = True

        if 'pfb_quantity' in vals or 'pfb_date_of_rent' in vals:
            vals['is_manual_qty'] = False

        return super().write(vals)

    @api.onchange('tax_id')
    def _onchange_tax_id_block(self):
        current_db = self.env.cr.dbname
        if current_db == 'NPD_Intertrading_New_NonVat':
            return
        for line in self:
            # ดู comment เรื่อง company ใน _compute_insurance_price -- ห้าม fallback
            # ไป self.env.company เพราะจะได้ภาษีของบริษัทอื่นบนเอกสารที่ยังไม่บันทึก
            company = line.company_id or line.order_id.company_id
            if not company:
                continue
            if line.order_id.pfb_so_type == 'sale' and line.product_id:
                expected_tax = self.env['account.tax'].search([
                    ('name', '=', 'ภาษีขายไม่รวม Vat 7%'),
                    ('company_id', '=', company.id),
                ], limit=1)
                if expected_tax and set(line.tax_id.ids) != {expected_tax.id}:
                    line.tax_id = [(6, 0, [expected_tax.id])]
                    return {
                        'warning': {
                            'title': "Cannot change tax",
                            'message': "Only 'ภาษีขายไม่รวม Vat 7%' is allowed for sales orders",
                            'type': 'warning'
                        }
                    }
            if line.order_id.pfb_so_type == 'rent' and line.product_id:
                expected_tax = self.env['account.tax'].search([
                    ('name', '=', 'ภาษีขายยังไม่ถึงกำหนด Vat 7%'),
                    ('company_id', '=', company.id),
                ], limit=1)
                if expected_tax and set(line.tax_id.ids) != {expected_tax.id}:
                    line.tax_id = [(6, 0, [expected_tax.id])]
                    return {
                        'warning': {
                            'title': "Cannot change tax",
                            'message': "Only 'ภาษีขายยังไม่ถึงกำหนด Vat 7%' is allowed for rental orders",
                            'type': 'warning'
                        }
                    }

    def _compute_insurance_price_rule(self, products_qty_partner, date=False, uom_id=False):
        self.ensure_one()
        if not date:
            date = self._context.get('date') or fields.Datetime.now()
        if not uom_id and self._context.get('uom'):
            uom_id = self._context['uom']

        if uom_id:
            products = [item[0].with_context(uom=uom_id) for item in products_qty_partner]
            products_qty_partner = [
                (products[index], data_struct[1], data_struct[2])
                for index, data_struct in enumerate(products_qty_partner)
            ]
        else:
            products = [item[0] for item in products_qty_partner]

        if not products:
            return 0.0

        categ_ids = {}
        for p in products:
            categ = p.categ_id
            while categ:
                categ_ids[categ.id] = True
                categ = categ.parent_id
        categ_ids = list(categ_ids)

        is_product_template = products[0]._name == "product.template"
        if is_product_template:
            prod_tmpl_ids = [tmpl.id for tmpl in products]
            prod_ids = [p.id for p in chain.from_iterable([t.product_variant_ids for t in products])]
        else:
            prod_ids = [product.id for product in products]
            prod_tmpl_ids = [product.product_tmpl_id.id for product in products]

        items = self._compute_price_rule_get_items(
            products_qty_partner, date, uom_id, prod_tmpl_ids, prod_ids, categ_ids
        )

        insurance_price = 0.0
        for product, qty, partner in products_qty_partner:
            qty_in_product_uom = qty

            for rule in items:
                if rule.min_quantity and qty_in_product_uom < rule.min_quantity:
                    continue
                if is_product_template:
                    if rule.product_tmpl_id and product.id != rule.product_tmpl_id.id:
                        continue
                    if rule.product_id and not (
                        product.product_variant_count == 1
                        and product.product_variant_id.id == rule.product_id.id
                    ):
                        continue
                else:
                    if rule.product_tmpl_id and product.product_tmpl_id.id != rule.product_tmpl_id.id:
                        continue
                    if rule.product_id and product.id != rule.product_id.id:
                        continue

                if rule.categ_id:
                    cat = product.categ_id
                    while cat:
                        if cat.id == rule.categ_id.id:
                            break
                        cat = cat.parent_id
                    if not cat:
                        continue

                # ใช้ pfb_insurance_price ถ้ามีค่า ถ้าไม่มีให้ fallback ไป npd_insurance_price
                insurance_price = rule.pfb_insurance_price or getattr(rule, 'npd_insurance_price', 0.0) or 0.0

        return insurance_price

    def _compute_price_rule_get_items(self, products_qty_partner, date, uom_id, prod_tmpl_ids, prod_ids, categ_ids):
        # Odoo 18: product.pricelist.item no longer has 'active' field
        flush_fields = ['price', 'currency_id', 'company_id']
        pricelist_item_fields = self.env['product.pricelist.item']._fields
        flush_fields = [f for f in flush_fields if f in pricelist_item_fields]
        if flush_fields:
            self.env['product.pricelist.item'].flush_model(flush_fields)
        pricelist_id = self.order_id.pricelist_id.id if self.order_id.pricelist_id else False
        if not pricelist_id:
            return self.env['product.pricelist.item']

        self.env.cr.execute(
            """
            SELECT item.id
            FROM product_pricelist_item AS item
            LEFT JOIN product_category AS categ ON item.categ_id = categ.id
            WHERE
                (item.product_tmpl_id IS NULL OR item.product_tmpl_id = any(%s))
                AND (item.product_id IS NULL OR item.product_id = any(%s))
                AND (item.categ_id IS NULL OR item.categ_id = any(%s))
                AND (item.pricelist_id = %s)
                AND (item.date_start IS NULL OR item.date_start <= %s)
                AND (item.date_end IS NULL OR item.date_end >= %s)
            ORDER BY
                item.applied_on, item.min_quantity desc, categ.complete_name desc, item.id desc
            """,
            (prod_tmpl_ids, prod_ids, categ_ids, pricelist_id, date, date)
        )
        item_ids = [x[0] for x in self.env.cr.fetchall()]
        import logging
        _logger = logging.getLogger(__name__)
        items = self.env['product.pricelist.item'].browse(item_ids)
        for it in items:
            _logger.info(
                "[INSURANCE SQL DEBUG] item_id=%s, product=%s, pfb_insurance_price=%s, min_qty=%s",
                it.id, it.product_tmpl_id.name or it.categ_id.name or 'ALL',
                it.pfb_insurance_price, it.min_quantity,
            )
        return items

    @api.depends('order_id', 'order_id.pfb_so_type')
    def _compute_so_rent_ok(self):
        for so_line in self:
            so_line.pfb_so_rent_ok = so_line.order_id.pfb_so_type == 'rent'
