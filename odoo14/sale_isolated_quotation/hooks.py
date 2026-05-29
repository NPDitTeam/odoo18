# © 2017 Ecosoft (ecosoft.co.th).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import ast

from odoo import SUPERUSER_ID, api

ACTIONS = (
    "sale.action_quotations_with_onboarding",
    "sale.action_orders",
)


def post_init_hook(env):
    """ Set value for order_sequence on old records + force update sequences """
    env.cr.execute(
        """
        update sale_order
        set order_sequence = true
        where state not in ('draft', 'cancel')
    """
    )

    # Force update/create Quotation sequence
    qt_seq = env['ir.sequence'].search([('code', '=', 'sale.quotation')], limit=1)
    qt_vals = {
        'name': 'Quotation',
        'code': 'sale.quotation',
        'prefix': 'QT-%(y)s%(month)s%(day)s-',
        'padding': 4,
        'use_date_range': True,
        'company_id': False,
    }
    if qt_seq:
        qt_seq.write(qt_vals)
    else:
        env['ir.sequence'].create(qt_vals)

    # Force update/create Sales Order sequence
    so_seq = env['ir.sequence'].search([('code', '=', 'sale.order')], limit=1)
    so_vals = {
        'name': 'Sales Order',
        'code': 'sale.order',
        'prefix': 'SO-%(y)s%(month)s%(day)s-',
        'padding': 4,
        'use_date_range': True,
        'company_id': False,
    }
    if so_seq:
        so_seq.write(so_vals)
    else:
        env['ir.sequence'].create(so_vals)


def uninstall_hook(env):
    """ Restore sale.order action, remove context value """
    for action_id in ACTIONS:
        action = env.ref(action_id)
        ctx = ast.literal_eval(action.context)
        _cleanup_ctx(ctx)
        dom = ast.literal_eval(action.domain or "{}")
        dom = [x for x in dom if x[0] != "order_sequence"]
        if action_id == "sale.action_orders":
            dom.append(("state", "not in", ("draft", "sent", "cancel")))
        else:
            ctx["search_default_my_quotation"] = True
        dom = list(set(dom))
        action.write({"context": ctx, "domain": dom})


def _cleanup_ctx(ctx):
    if "order_sequence" in ctx:
        del ctx["order_sequence"]
    if "default_order_sequence" in ctx:
        del ctx["default_order_sequence"]
