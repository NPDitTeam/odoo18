import copy

from odoo import api, models
from odoo.http import request

from .sale_order import NPD_LOGISTICS_REGISTRY

# โลจิสติกส์เปิดแค่ SO สำหรับงานขนส่ง (สร้างจากเมนูใบกำกับการเช่าได้เลย)
# เมนูใบเสนอราคาทำให้พนักงานสับสน จึงซ่อนทั้งกลุ่มเมื่อบริษัทที่เลือกอยู่คือโลจิสติกส์
LOGISTICS_HIDDEN_MENUS = ('pfb_npd_all_customs.sale_quotations',)


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def _npd_current_company(self):
        """บริษัทที่เลือกอยู่บนแถบสลับบริษัท (ตัวแรกในคุกกี้ cids)

        load_menus ถูกเรียกตอนเปิดหน้าเว็บ ซึ่งบริบทยังไม่มี allowed_company_ids
        จึงอ่านจากคุกกี้แบบเดียวกับ multi_branch_management_aagam
        """
        user = self.env.user
        cids = request.httprequest.cookies.get('cids') if request and request.httprequest else None
        for part in (cids or '').replace(',', '-').split('-'):
            part = part.strip()
            if part.isdigit() and int(part) in user.company_ids.ids:
                return self.env['res.company'].sudo().browse(int(part))
        return user.company_id

    @api.model
    def load_menus(self, debug):
        menus = super().load_menus(debug)
        if not request or self._npd_current_company().company_registry != NPD_LOGISTICS_REGISTRY:
            return menus

        hidden = set()
        for xmlid in LOGISTICS_HIDDEN_MENUS:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                hidden.update(self.sudo().search([('id', 'child_of', menu.id)]).ids)
        if not hidden & set(menus):
            return menus

        # ผลของ super ถูกแคชไว้ต่อผู้ใช้ ห้ามแก้ตัวเดิม ไม่งั้นบริษัทอื่นจะหายเมนูไปด้วย
        menus = copy.deepcopy(menus)
        for menu_id in hidden:
            menus.pop(menu_id, None)
        for menu in menus.values():
            if menu.get('children'):
                menu['children'] = [c for c in menu['children'] if c not in hidden]
        return menus
