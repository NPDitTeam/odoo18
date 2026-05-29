# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ResBranch(models.Model):
    _name = 'res.branch'
    _description = 'Branch'
    _rec_name = 'name'

    name = fields.Char(required=True, string='Branch Name')
    sequence = fields.Integer(help='Used to order Companies in the branch switcher', default=10)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company,required=True)
    email = fields.Char(string='Email')
    phone = fields.Char(string='Mobile No.')


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
