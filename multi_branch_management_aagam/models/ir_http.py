# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
import hashlib
import json

from odoo import api, models
from odoo.http import request

class Http(models.AbstractModel):
    _inherit = 'ir.http'


    def session_info(self):
        # ✅ Call parent first
        res = super(Http, self).session_info()
        
        # ✅ Check if user exists (might be None during auth)
        try:
            user = request.env.user
            
            # ✅ Only proceed if user is valid
            if not user or not user.id:
                # Return parent result if no user
                return res
            
            # ✅ Get branch info safely
            branch_id = user.branch_id.id if hasattr(user, 'branch_id') and user.branch_id else None
            branch_ids = [b.id for b in user.branch_ids] if hasattr(user, 'branch_ids') else []
            
            # ✅ Build user context safely
            user_context = dict(request.env.context) if request.session.uid else {}
            user_context['allowed_branch_ids'] = [branch.id for branch in user.branch_ids if branch.id == branch_id]
            user_context['allowed_branches'] = [(b.id, b.name) for b in user.branch_ids]
            user_context['default_branch'] = branch_id
            
            # ✅ Update response safely
            res.update({
                'branch_id': branch_id,
                "user_branches": {
                    'current_branch': (branch_id, user.branch_id.name) if branch_id else (None, None),
                    'allowed_branches': [(b.id, b.name) for b in user.branch_ids]
                },
                "show_effect": True,
                "allowed_branch_ids": branch_ids,
                "default_branch": branch_id,
                'allowed_branches': [(b.id, b.name) for b in user.branch_ids],
                "display_switch_branch_menu": (
                    user.has_group('multi_branch_management_axis.group_multi_branch') 
                    and len(user.branch_ids) > 1
                ),
            })
            res['user_context'] = user_context
            
        except Exception as e:
            # ✅ Fail gracefully - return parent result
            print(f"⚠️  Error in session_info: {e}")
            # Don't update, just return parent response
            pass
        
        return res
