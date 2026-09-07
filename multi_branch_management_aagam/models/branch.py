# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.osv import expression


class ResBranch(models.Model):
    _name = 'res.branch'
    _description = 'Branch'
    _rec_name = 'name'

    name = fields.Char(required=True, string='Branch Name')
    sequence = fields.Integer(help='Used to order Companies in the branch switcher', default=10)

    def _skip_branch_company_filter(self):
        """Users who administer branches see every branch, always.

        Why this matters beyond convenience: Odoo verifies record access by
        re-running a search, so a branch filtered out here does not merely
        disappear from a list - it reads back as AccessError, and any view that
        references it (a user's Allowed Branches, an employee's branch, ...)
        fails to render entirely. Managers were therefore losing whole screens
        whenever a branch sat outside the company currently selected in the
        switcher, and had to be granted each new branch by hand.
        """
        user = self.env.user
        return (
            self.env.su
            or user._is_superuser()
            or user.has_group('multi_branch_management_aagam.group_branch_manager')
            or user.has_group('base.group_system')
        )

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None):
        # Only show branches belonging to the active company/companies so that
        # Branch fields (advance, sale, purchase, invoice, payment, ...) cannot
        # select a branch from another company. Branches with no company
        # (company_ids empty) are shared and always visible. A user's OWN
        # allowed branches (branch_ids) are always visible too: otherwise a user
        # whose branch happens to live in another company could not even read
        # their own branch, which raises AccessError on every page and blocks
        # login. Set the context key 'bypass_branch_company_filter' to disable
        # this entirely (e.g. cross-company reports or maintenance scripts).
        if (not self.env.context.get('bypass_branch_company_filter')
                and not self._skip_branch_company_filter()):
            own_branch_ids = self.env.user.sudo().branch_ids.ids
            company_domain = expression.OR([
                [('id', 'in', own_branch_ids)],
                [('company_ids', '=', False)],
                [('company_ids', 'in', self.env.companies.ids)],
            ])
            domain = expression.AND([domain or [], company_domain])
        return super()._search(domain, offset=offset, limit=limit, order=order)
    company_ids = fields.Many2many(
        'res.company', 'res_branch_res_company_rel', 'res_branch_id', 'res_company_id',
        string='Companies', default=lambda self: self.env.company,
        help='Companies this branch belongs to. A branch can be shared by several companies.')
    # Compatibility field. This model scopes itself with the many2many
    # `company_ids`, but Odoo's own web client, several core mixins and most
    # third-party modules assume any company-scoped model exposes the singular
    # `company_id`. Without it, anything that references res.branch.company_id
    # dies at view-parse time with "field is undefined" and the whole view
    # fails to render (seen on Settings > Users and on the Branches action).
    # Computed and not stored, so `company_ids` stays the single source of truth.
    company_id = fields.Many2one(
        'res.company', string='Company',
        compute='_compute_company_id', search='_search_company_id',
        help='First company this branch belongs to. Kept for compatibility with '
             'code that expects a single company; the real link is Companies.')

    email = fields.Char(string='Email')
    phone = fields.Char(string='Mobile No.')

    @api.depends('company_ids')
    def _compute_company_id(self):
        for branch in self:
            branch.company_id = branch.company_ids[:1]

    def _search_company_id(self, operator, value):
        # Delegate to the many2many so domains on company_id keep working.
        return [('company_ids', operator, value)]


    street = fields.Char('Street', compute='_compute_address', inverse='_inverse_street')
    street2 = fields.Char('Street2', compute='_compute_address', inverse='_inverse_street2')
    zip = fields.Char(change_default=True, string='Zip', compute='_compute_address', inverse='_inverse_zip')
    city = fields.Char('City', compute='_compute_address', inverse='_inverse_city')
    country_id = fields.Many2one('res.country', string='Country', ondelete='restrict', compute='_compute_address',
                                 inverse='_inverse_country')

    location = fields.Char(string='Location', compute='_compute_location', store=True)
    state_id = fields.Many2one("res.country.state", string='State', ondelete='restrict', compute='_compute_address',
                               inverse='_inverse_state',
                               domain="[('country_id', '=?', country_id)]")

    partner_id = fields.Many2one('res.partner', string='Partner')
    warehouse_id = fields.Many2one('stock.warehouse')
    warehouse_ids = fields.Many2many('stock.warehouse', compute='_compute_warehouse_ids', store=1,
                                          string='Warehouse associated to this Branch')
    warehouse_count = fields.Integer("Warehouse Count", compute='_compute_warehouse_ids')

    _sql_constraints = [
        ('name_uniq', 'unique (name)', 'The Branch name must be unique !')
    ]

    @api.depends('warehouse_id')
    def _compute_warehouse_ids(self):
        for branch in self:
            branch.warehouse_ids = self.env['stock.warehouse'].search(
                [('branch_id', '=', branch.id)])
            branch.warehouse_count = len(branch.warehouse_ids)

    def action_view_warehouse(self):
        view_form_id = self.env.ref('stock.view_warehouse').id
        view_list_id = self.env.ref('stock.view_warehouse_tree').id
        action = {
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', self.warehouse_ids.ids)],
            'view_mode': 'list,form',
            'name': ('Warehouses'),
            'res_model': 'stock.warehouse',
        }
        if len(self.warehouse_ids) == 1:
            action.update({'views': [(view_form_id, 'form')], 'res_id': self.warehouse_ids.id})
        else:
            action['views'] = [(view_list_id, 'list'), (view_form_id, 'form')]
        return action

    @api.depends('country_id', 'state_id', 'city')
    def _compute_location(self):
        for rec in self:
            rec.location = None
        #     if not (rec.city or rec.state_id or rec.country_id) :
        #         rec.location = None
        #     else:
        #         rec.location = ('%s, %s, %s'%(rec.city, rec.state_id.name, rec.country_id.name))


    def _get_branch_address_fields(self, partner):
        return {
            'street': partner.street,
            'street2': partner.street2,
            'city': partner.city,
            'zip': partner.zip,
            'state_id': partner.state_id,
            'country_id': partner.country_id,
        }

    # TODO @api.depends(): currently now way to formulate the dependency on the
    # partner's contact address
    def _compute_address(self):
        print(
            "_compute_address:", self
        )
        for branch in self.filtered(lambda branch: branch.partner_id):
            address_data = branch.partner_id.sudo().address_get(adr_pref=['contact'])
            if address_data['contact']:
                partner = branch.partner_id.browse(address_data['contact']).sudo()
                branch.update(branch._get_branch_address_fields(partner))

    def _inverse_street(self):
        for branch in self:
            branch.partner_id.street = branch.street

    def _inverse_street2(self):
        for branch in self:
            branch.partner_id.street2 = branch.street2

    def _inverse_zip(self):
        for branch in self:
            branch.partner_id.zip = branch.zip

    def _inverse_city(self):
        for branch in self:
            branch.partner_id.city = branch.city

    def _inverse_state(self):
        for branch in self:
            branch.partner_id.state_id = branch.state_id

    def _inverse_country(self):
        for branch in self:
            branch.partner_id.country_id = branch.country_id


    @api.model
    def create(self, vals):
        partner = self.env['res.partner'].create({
            'name': vals['name'],
            'is_branch': True,
            'email': vals.get('email'),
            'phone': vals.get('phone'),
            'street': vals.get('street'),
            'street2': vals.get('street2'),
            'city': vals.get('city'),
            'zip': vals.get('zip'),
            'state_id': vals.get('state_id'),
            'country_id': vals.get('country_id'),
        })
        # compute stored fields, for example address dependent fields

        vals['partner_id'] = partner.id
        self.clear_caches()
        return super(ResBranch, self).create(vals)
