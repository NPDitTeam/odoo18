# -*- coding: utf-8 -*-
import logging
from odoo import models, api

_logger = logging.getLogger(__name__)


class TransportOrder(models.Model):
    _inherit = 'transport.order'
    
    @api.model
    def _search(self, domain, offset=0, limit=None, order=None):
        """Override search เพื่อกรองตาม branch ของ user"""
        user = self.env.user
        
        # ✅ กรองตาม "สาขาที่ user มีสิทธิ์" — ใช้ multi_branch_id (สาขาที่เลือกบน navbar)
        #    ถ้าว่าง fallback ใช้ branch_ids (Allowed Branches)
        #    ❗ ห้ามใช้ branch_id ตัวเดียว เพราะ navbar switcher เขียนทับ branch_id ตลอด
        if not user.show_all_transport_booking_branches:
            allowed_branch_ids = user.multi_branch_id.ids or user.branch_ids.ids
            if allowed_branch_ids:
                branch_domain = ['|', ('branch_id', '=', False),
                                 ('branch_id', 'in', allowed_branch_ids)]
                domain = (domain or []) + branch_domain
                _logger.info("✅ [transport.order] Filtering by branches: %s", allowed_branch_ids)

        return super()._search(domain, offset=offset, limit=limit, order=order)
