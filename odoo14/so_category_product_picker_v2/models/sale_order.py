from odoo import models, fields


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def open_category_product_popup(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'product.category.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_order_id': self.id,
                'default_pfb_so_type': self.pfb_so_type,
            },
            'name': 'เพิ่มสินค้าตามหมวดหมู่',
        }
