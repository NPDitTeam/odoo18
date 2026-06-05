# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """res.branch.company_id (Many2one) became company_ids (Many2many).

    The old single-company column is left orphaned in the table after the
    schema update; copy its values into the new many2many relation so existing
    branches keep their company link.
    """
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'res_branch' AND column_name = 'company_id'
    """)
    if not cr.fetchone():
        _logger.info("multi_branch: no legacy res_branch.company_id column, nothing to migrate")
        return

    cr.execute("""
        INSERT INTO res_branch_res_company_rel (res_branch_id, res_company_id)
        SELECT id, company_id FROM res_branch WHERE company_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)
    _logger.info("multi_branch: migrated %s branch company links to company_ids", cr.rowcount)
