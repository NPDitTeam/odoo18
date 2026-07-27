# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleAdvanceRentInv(models.TransientModel):
    _name = "sale.advance.rent.inv"
    _description = "Sales Advance Rent Invoice"

    advance_payment_method = fields.Selection([
        ('fixed', 'Down payment (fixed amount)'),
        ('percentage', 'Down payment (percentage)')
    ], string='Create Invoice', default='fixed', required=True, readonly=True)

    sale_order_id = fields.Many2one(
        comodel_name='sale.order',
        string='Sale Order',
        required=True
    )

    amount = fields.Float('Down Payment Amount', compute='_compute_down_payment_amount')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self._context.get('active_id')
        if active_id:
            res['sale_order_id'] = active_id
        else:
            res['sale_order_id'] = self.env['sale.order'].search([], limit=1).id
        return res

    @api.depends('advance_payment_method')
    def _compute_down_payment_amount(self):
        active_ids = self._context.get('active_ids', [])
        if active_ids:
            sale_orders = self.env['sale.order'].browse(active_ids)
            for order in sale_orders:
                self.amount = order.pfb_amount
        else:
            raise UserError("No active_ids found in context.")

    def create_invoices(self):
        sale_orders = self.env['sale.order'].browse(self._context.get('active_ids', []))
        amount = 0
        name = _('รับเงินประกัน')

        company = sale_orders.company_id[:1] or self.env.company

        # สินค้าเงินประกัน ตั้งค่าได้ที่
        # การขาย > การกำหนดค่า > สมุดรายวันออกใบแจ้งหนี้ (กรณี "ใบแจ้งหนี้รับเงินประกัน")
        Config = self.env['npd.invoice.journal.config']
        product = Config._get_insurance_product(company)
        if not product:
            raise UserError(_(
                "ยังไม่ได้ตั้งสินค้าเงินประกันของบริษัท %(company)s\n\n"
                "กรุณาตั้งค่าที่เมนู การขาย > การกำหนดค่า > สมุดรายวันออกใบแจ้งหนี้\n"
                "เลือกแถวกรณี \"ใบแจ้งหนี้รับเงินประกัน\" แล้วระบุช่อง \"สินค้าเงินประกัน\"",
                company=company.display_name,
            ))

        tax = False
        if self.advance_payment_method == 'percentage':
            if product.taxes_id:
                tax = [(6, 0, product.taxes_id.ids)]
                if product.taxes_id.price_include:
                    amount = sale_orders.amount_total * self.amount / 100
                    name = _("รับเงินประกัน %s%%") % self.amount
                else:
                    amount = sale_orders.amount_untaxed * self.amount / 100
                    name = _("รับเงินประกัน %s%%") % self.amount
            else:
                amount = sale_orders.amount_total * self.amount / 100
                name = _("รับเงินประกัน %s%%") % self.amount
        else:
            amount = self.amount
            if product.taxes_id:
                tax = [(6, 0, product.taxes_id.ids)]

        # สมุดรายวันของใบรับเงินประกัน ตั้งค่าที่เมนูเดียวกับสินค้าเงินประกัน
        insurance_journal = Config._get_journal(company, 'insurance')
        if not insurance_journal:
            raise UserError(_(
                "ยังไม่ได้ตั้งสมุดรายวันสำหรับใบแจ้งหนี้รับเงินประกันของบริษัท %(company)s\n"
                "กรุณาตั้งค่าที่เมนู การขาย > การกำหนดค่า > สมุดรายวันออกใบแจ้งหนี้",
                company=company.display_name,
            ))

        invoice_vals = {
            'ref': sale_orders.client_order_ref,
            'move_type': 'out_invoice',
            # ต้องระบุบริษัทของใบสั่งขาย ไม่ใช่ปล่อยให้ default เป็นบริษัทที่ active อยู่
            # ไม่งั้นสมุดรายวันที่ล็อกตามบริษัทข้างบนจะไม่ตรงกับใบแจ้งหนี้ แล้วตายที่ _check_company
            'company_id': company.id,
            'invoice_origin': sale_orders.name,
            'invoice_user_id': sale_orders.user_id.id,
            'narration': sale_orders.note,
            'partner_id': sale_orders.partner_invoice_id.id,
            'fiscal_position_id': (
                sale_orders.fiscal_position_id
                or sale_orders.fiscal_position_id._get_fiscal_position(sale_orders.partner_id)
            ).id,
            'partner_shipping_id': sale_orders.partner_shipping_id.id,
            'currency_id': sale_orders.pricelist_id.currency_id.id,
            'payment_reference': sale_orders.reference,
            'invoice_payment_term_id': sale_orders.payment_term_id.id,
            'partner_bank_id': sale_orders.company_id.partner_id.bank_ids[:1].id,
            'team_id': sale_orders.team_id.id,
            'campaign_id': sale_orders.campaign_id.id,
            'medium_id': sale_orders.medium_id.id,
            'source_id': sale_orders.source_id.id,
            'journal_id': insurance_journal.id,
            'invoice_line_ids': [(0, 0, {
                'name': name,
                'price_unit': amount,
                'quantity': 1.0,
                'product_id': product.id,
                'product_uom_id': product.uom_id.id,
                'tax_ids': tax,
            })],
        }
        new_invoice = self.env['account.move'].create(invoice_vals)
        sale_orders.sudo().write({'rent_check': [(4, new_invoice.id)]})

        if self._context.get('open_invoices', False):
            return sale_orders.action_view_rent()

        return {'type': 'ir.actions.act_window_close'}
