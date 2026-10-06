from odoo import api, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    @api.model
    def npd_tax_branch_missing(self, partner_id):
        """ใบสั่งขายเรียกตอนเลือกลูกค้า: ต้องเด้งให้กรอกรหัสสาขาไหม

        เช็คที่บริษัทแม่ (commercial partner) เพราะใบกำกับภาษีออกในนามบริษัทแม่
        แม้จะเลือกผู้ติดต่อย่อยมาก็ตาม
        """
        partner = self.browse(partner_id).exists().commercial_partner_id
        if not partner or not partner.is_company:
            return False
        return not (partner.branch or '').strip()
