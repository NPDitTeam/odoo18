# -*- coding: utf-8 -*-

from . import models
from . import controllers
from . import wizard
from . import report
from odoo import api, fields, models, _


from odoo.api import Environment, SUPERUSER_ID


def post_init_hook(env):
    # with api.Environment.manage():
    # env = api.Environment(cr, SUPERUSER_ID, {})

    # Reference the main branch
    main_branch_id = env.ref('multi_branch_management_aagam.main_branch')

    # Search for all res.users records
    res_user_ids = env['res.users'].search([])

    # Update branch information for all users
    for res_user_id in res_user_ids:
        res_user_id.write({
            'branch_id': main_branch_id.id,
            'branch_ids': [(6, 0, [main_branch_id.id])],  # Write list with single main_branch_id
            'multi_branch_id': [(6, 0, [main_branch_id.id])],  # Same here
        })

