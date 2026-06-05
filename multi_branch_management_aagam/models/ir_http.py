# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models
from odoo.http import request


class Http(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        # Always start from the standard Odoo session payload.
        res = super().session_info()

        try:
            user = request.env.user
            if not user or not user.id:
                return res

            # Only offer branches that belong to one of the companies the user
            # currently has active (the company switcher). During the initial
            # page bootstrap the request context does NOT yet carry
            # allowed_company_ids (the JS company service only sends it on later
            # RPCs), so request.env.companies would fall back to ALL the user's
            # companies. Read the active selection straight from the 'cids'
            # cookie instead.
            allowed_company_ids = set(user.company_ids.ids)
            active_company_ids = set()
            cids = request.httprequest.cookies.get('cids') if request.httprequest else None
            if cids:
                for part in cids.replace(',', '-').split('-'):
                    part = part.strip()
                    if part.isdigit():
                        active_company_ids.add(int(part))
            active_company_ids &= allowed_company_ids
            if not active_company_ids:
                active_company_ids = {user.company_id.id} if user.company_id else allowed_company_ids

            # A branch with no company set is treated as shared and always shown.
            visible_branches = user.branch_ids.filtered(
                lambda b: (not b.company_ids) or (set(b.company_ids.ids) & active_company_ids)
            )

            # Branches the user is allowed to work in, restricted to the active
            # company/companies (static permission ∩ current company).
            allowed_branches = [
                {'id': b.id, 'name': b.name}
                for b in visible_branches
            ]
            visible_ids = visible_branches.ids
            # Branches currently active in the navbar switcher (dynamic
            # selection), kept consistent with what is actually shown.
            current_branch_ids = [b for b in user.multi_branch_id.ids if b in visible_ids]
            if not current_branch_ids:
                # No stored selection for this company -> everything in the
                # current company is shown (matches the record-rule fallback).
                current_branch_ids = visible_ids

            res.update({
                'branch_id': user.branch_id.id or False,
                'default_branch': user.branch_id.id or False,
                'allowed_branches': allowed_branches,
                'allowed_branch_ids': visible_ids,
                'current_branch_ids': current_branch_ids,
                # The navbar switcher only shows for users in the Multi Branch
                # group who actually have more than one branch to choose from.
                'display_switch_branch_menu': (
                    user.has_group('multi_branch_management_aagam.group_multi_branch')
                    and len(user.branch_ids) > 1
                ),
            })
        except Exception as e:
            # Never break login if anything goes wrong while computing branches.
            import logging
            logging.getLogger(__name__).warning(
                "multi_branch_management_aagam: failed to enrich session_info: %s", e
            )

        return res
