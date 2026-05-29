from . import models


def post_init_hook(env):
    """Force update payment sequences to correct prefix format"""
    # Customer Payment: CUST.IN-YYMMDD-XXXX
    seq = env['ir.sequence'].search([('code', '=', 'customer.payment')], limit=1)
    if seq:
        seq.write({
            'prefix': 'CUST.IN-%(y)s%(month)s%(day)s-',
            'padding': 4,
            'use_date_range': True,
        })

    # Supplier Payment: CUST.OUT-YYMMDD-XXXX
    seq = env['ir.sequence'].search([('code', '=', 'supplier.payment')], limit=1)
    if seq:
        seq.write({
            'prefix': 'CUST.OUT-%(y)s%(month)s%(day)s-',
            'padding': 4,
            'use_date_range': True,
        })
