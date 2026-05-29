# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class ProductCategoryWizard(models.TransientModel):
    _name = 'product.category.wizard'
    _description = 'Wizard: Select Product Category and Add to SO'

    sale_order_id = fields.Many2one('sale.order', string='Sale Order', required=True)
    pfb_so_type = fields.Selection(
        related='sale_order_id.pfb_so_type',
        string='ประเภทการรับชำระหนี้',
        store=True,
    )
    category_id = fields.Many2one('product.category', string='หมวดหมู่สินค้า')
    line_ids = fields.One2many('product.category.wizard.line', 'wizard_id', string='รายการสินค้า')

    @api.onchange('category_id')
    def _onchange_category_id(self):
        self.line_ids = False
        if not self.category_id:
            return

        # Find internal location (branch-aware if available)
        location_domain = [('usage', '=', 'internal')]
        if hasattr(self.env.user, 'branch_id') and self.env.user.branch_id:
            location_domain.append(('branch_id', '=', self.env.user.branch_id.id))
        location = self.env['stock.location'].search(location_domain, limit=1)

        products = self.env['product.product'].search([
            ('categ_id', '=', self.category_id.id),
            ('sale_ok', '=', True),
        ])

        lines = []
        for product in products:
            qty_onhand = 0.0
            if location:
                qty_onhand = self.env['stock.quant']._get_available_quantity(product, location)
            lines.append((0, 0, {
                'product_id': product.id,
                'product_code': product.default_code,
                'pfb_quantity': 0.0,
                'product_qty_available': qty_onhand,
                'product_weight': product.weight or 0.0,
                'selected': False,
            }))
        self.line_ids = lines

    @api.onchange('sale_order_id')
    def _onchange_sale_order_id(self):
        if self.sale_order_id.pfb_so_type == 'rent':
            return {'domain': {'category_id': [('parent_id.name', '=', 'สินค้าให้เช่า')]}}
        elif self.sale_order_id.pfb_so_type == 'sale':
            return {'domain': {'category_id': [('parent_id.name', '=', 'สินค้าขาย')]}}
        return {}

    def action_add_selected_products(self):
        error_products = self.line_ids.filtered(
            lambda l: l.selected and (not l.pfb_quantity or l.pfb_quantity <= 0)
        )
        if error_products:
            names = ', '.join(error_products.mapped('product_name'))
            raise UserError(
                "ไม่สามารถเพิ่มสินค้าได้ เนื่องจากยังไม่ได้ระบุจำนวนในสินค้าเหล่านี้:\n%s" % names
            )

        lines = []
        for line in self.line_ids.filtered(lambda l: l.selected and l.product_id):
            lines.append((0, 0, {
                'product_id': line.product_id.id,
                'name': line.product_id.name,
                'product_uom_qty': line.pfb_quantity or 1.0,
                'pfb_quantity': line.pfb_quantity or 0.0,
                'second_uom_qty': line.product_weight or line.product_id.weight or 0.0,
            }))
        self.sale_order_id.write({'order_line': lines})
        return {'type': 'ir.actions.act_window_close'}


class ProductCategoryWizardLine(models.TransientModel):
    _name = 'product.category.wizard.line'
    _description = 'Wizard Line'

    wizard_id = fields.Many2one('product.category.wizard', string='Wizard')
    product_id = fields.Many2one('product.product', string='สินค้า', required=True)
    bk_reference_code = fields.Char(
        string='รหัสสินค้า',
        related='product_id.product_tmpl_id.bk_reference_code',
        store=False,
        readonly=True,
    )
    product_name = fields.Char(string='ชื่อสินค้า', related='product_id.name', store=False)
    product_code = fields.Char(string='อ้างอิงภายใน')
    pfb_quantity = fields.Float(string='จำนวนที่ใช้')
    product_qty_available = fields.Float(string='ปริมาณในมือ')
    product_weight = fields.Float(string='น้ำหนักต่อหน่วย (กก.)')
    selected = fields.Boolean(string='เลือก')
