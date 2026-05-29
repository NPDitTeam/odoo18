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
        
        _logger.debug(
            f"🔍 TransportOrder._search | User: {user.name} | "
            f"Branch: {user.branch_id.name if user.branch_id else 'None'} | "
            f"show_all: {user.show_all_transport_booking_branches}"
        )

        # ✅ ถ้า user ไม่เลือก "แสดงทุกสาขา" AND มี branch กำหนด → กรองเฉพาะ branch นั้น
        if not user.show_all_transport_booking_branches and user.branch_id:
            branch_domain = [('branch_id', '=', user.branch_id.id)]
            domain = (domain or []) + branch_domain
            _logger.info(f"✅ TransportOrder filtered by branch: {user.branch_id.name}")
        else:
            _logger.info(
                f"🌍 TransportOrder showing all branches - "
                f"show_all_transport_booking_branches={user.show_all_transport_booking_branches}, "
                f"has_branch={bool(user.branch_id)}"
            )

        return super()._search(domain, offset=offset, limit=limit, order=order)
