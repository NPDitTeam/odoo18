# -*- coding: utf-8 -*-
from . import models


def post_init_hook(env):
    """Mark every already-numbered move as "sequence generated".

    Without this, the first recompute of ``name`` on a legacy move (changing its
    date, for instance) would see ``sequence_generated = False`` on a posted move
    and draw a brand new number from the journal sequence, overwriting the number
    that was already printed on the document.
    """
    env.cr.execute("""
        UPDATE account_move
           SET sequence_generated = TRUE
         WHERE name IS NOT NULL
           AND name != '/'
           AND sequence_generated IS NOT TRUE
    """)
