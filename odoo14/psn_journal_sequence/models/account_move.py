# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    sequence_generated = fields.Boolean(
        string="Sequence Generated",
        copy=False,
        help="Technical field. True once this entry has drawn its number from the "
             "ir.sequence configured on its journal, so it never draws a second one.",
    )
    use_journal_sequence = fields.Boolean(
        string="Numbered by Journal Sequence",
        compute='_compute_use_journal_sequence',
        help="Technical field used in views: True when the journal of this entry "
             "carries a dedicated ir.sequence, in which case the number is assigned "
             "by the system and cannot be edited.",
    )

    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------

    def _has_journal_sequence(self):
        """Whether the journal of this move is numbered by a custom ir.sequence.

        Deliberately checks *both* sequences: as soon as a journal is configured
        with one of them, the whole journal opts out of the Odoo 18 automatic
        numbering, so that invoices and credit notes cannot end up numbered by
        two different mechanisms.
        """
        return bool(self.journal_id.sequence_id or self.journal_id.refund_sequence_id)

    def _get_journal_sequence(self):
        """Return the ir.sequence to use when numbering the current move.

        :return: an ``ir.sequence`` recordset, empty if the journal is misconfigured.
        """
        self.ensure_one()
        journal = self.journal_id
        if journal.refund_sequence and self.move_type in ('out_refund', 'in_refund'):
            return journal.refund_sequence_id
        return journal.sequence_id

    @api.depends('journal_id.sequence_id', 'journal_id.refund_sequence_id')
    def _compute_use_journal_sequence(self):
        for move in self:
            move.use_journal_sequence = move._has_journal_sequence()

    # -------------------------------------------------------------------------
    # NUMBERING
    # -------------------------------------------------------------------------

    # Keep the exact dependencies of the standard compute: the override replaces
    # the method in the MRO, so the field would otherwise lose all its triggers.
    @api.depends('posted_before', 'state', 'journal_id', 'date', 'move_type',
                 'origin_payment_id')
    def _compute_name(self):
        custom = self.filtered(lambda m: m._has_journal_sequence())
        standard = self - custom
        if standard:
            super(AccountMove, standard)._compute_name()
        if not custom:
            return

        for move in custom:
            if move.state == 'cancel' or move.sequence_generated:
                continue

            has_name = move.name and move.name != '/'
            if move.state == 'draft':
                if not has_name:
                    move.name = '/'
                continue
            if has_name:
                # Already numbered: either a legacy entry posted before this
                # module was installed, or a number forced by hand. Adopt it
                # instead of burning a fresh number on top of it.
                move.sequence_generated = True
                continue

            sequence = move._get_journal_sequence()
            if not sequence:
                raise UserError(_(
                    "Please define a sequence on the journal %(journal)s.",
                    journal=move.journal_id.display_name,
                ))
            # Pass the accounting date so date-ranged (sub)sequences follow the
            # entry date rather than the day the user happens to click Post.
            move.name = sequence.sudo().next_by_id(sequence_date=move.date)
            move.sequence_generated = True

        custom._inverse_name()

    def _must_check_constrains_date_sequence(self):
        """Skip the Odoo 18 "name must match the date" constraint.

        Numbers coming from an ir.sequence follow whatever prefix the user
        configured (Buddhist year, branch code, ...), which the sequence.mixin
        parser has no way to reconcile with the entry date.
        """
        if self._has_journal_sequence():
            return False
        return super()._must_check_constrains_date_sequence()

    # -------------------------------------------------------------------------
    # SEQUENCE-GAP DETECTION (Odoo 18 only, meaningless with ir.sequence)
    # -------------------------------------------------------------------------

    @api.depends('journal_id', 'sequence_number', 'sequence_prefix', 'state')
    def _compute_made_sequence_gap(self):
        # A standard ir.sequence is backed by a PostgreSQL sequence, which legally
        # skips numbers on rollback. Flagging those as irregular would paint most
        # of the list view red for nothing.
        custom = self.filtered(lambda m: m._has_journal_sequence())
        custom.made_sequence_gap = False
        standard = self - custom
        if standard:
            super(AccountMove, standard)._compute_made_sequence_gap()

    def _set_next_made_sequence_gap(self, made_gap):
        standard = self.filtered(lambda m: not m._has_journal_sequence())
        if not standard:
            return
        return super(AccountMove, standard)._set_next_made_sequence_gap(made_gap)

    @api.depends('date', 'journal_id', 'move_type', 'name', 'posted_before',
                 'sequence_number', 'sequence_prefix', 'state')
    def _compute_name_placeholder(self):
        # The number suggested by the mixin would not be the one actually drawn.
        custom = self.filtered(lambda m: m._has_journal_sequence())
        custom.name_placeholder = False
        standard = self - custom
        if standard:
            super(AccountMove, standard)._compute_name_placeholder()
