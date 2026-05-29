# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class ResUsers(models.Model):
    _inherit = "res.users"

    branch_id = fields.Many2one('res.branch', string='Branch', help='The default branch for this user.',
                                context={'user_preference': True})
                            # default=lambda self: self.env.branch_id.id)
    branch_ids = fields.Many2many('res.branch', 'res_branch_users_rel', 'user_id', 'bid', string='Branches',)
                                  # default=lambda self: self.env.branch_id.id)

    multi_branch_id = fields.Many2many('res.branch', 'res_branch_users_multi_rel_b', 'user_id', 'bid',
                                       string='Multi Branches')

    @api.model
    def create(self, vals):
        res = super(ResUsers, self).create(vals)
        
        try:
            branch_id = self.env.ref('multi_branch_management_aagam.main_branch')
        except ValueError:
            # External ID not found, use search fallback
            branch_id = self.env['res.branch'].search([], limit=1)
        
        if res and branch_id:
            res.branch_id = branch_id.id
            res.branch_ids = [(6, 0, branch_id.ids)]
            res.multi_branch_id =  [(6, 0, branch_id.ids)]
        return res

    def res_user_branch(self, *args,**kwargs):
        
        branch = kwargs['branch']
        self.sudo().write({'branch_id':  branch[0]})

        self.sudo().write({'multi_branch_id': [
            (6,0, branch)]})

    def res_user_branch_clcik(self, *args, **kwargs):
        
        branch = kwargs['branch']
        
        for i in branch:
            self.sudo().write({'multi_branch_id': [
                (6, 0, branch)]})



    @api.onchange('branch_id')
    def onchange_multi_branch(self):
        
        branch = self.env['res.branch'].sudo().search([('id', '=', self.branch_id.id)])
        for i in branch:
            self.sudo().write({'multi_branch_id': [
                (6,0,  [i.id])]})        

    def _branch_count(self):
        return self.env['res.branch'].sudo().search_count([])

    branch_count = fields.Integer(compute='_compute_branch_count', string="Number of Branch", default=_branch_count)

    def _compute_branch_count(self):
        branch_count = self._branch_count()
        for user in self:
            user.branch_count = branch_count

