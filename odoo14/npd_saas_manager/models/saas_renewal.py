# -*- coding: utf-8 -*-
"""ประวัติการต่ออายุสัญญา

เก็บแยกเป็นตารางแทนการเขียนทับ ``expire_date`` เฉย ๆ เพื่อให้ย้อนดูได้ว่าต่อกี่ครั้ง
ครั้งละกี่เดือน คิดเงินเท่าไร และใครเป็นคนต่อ — จำเป็นเวลามีข้อโต้แย้งเรื่องรอบบิล
"""
from odoo import models, fields


class SaasRenewal(models.Model):
    _name = 'saas.renewal'
    _description = 'ประวัติการต่ออายุสัญญาเช่าระบบ'
    _order = 'renew_date desc, id desc'

    tenant_id = fields.Many2one(
        'hrms.tenant', string='องค์กร', required=True,
        ondelete='cascade', index=True)
    renew_date = fields.Date(
        string='วันที่ต่อ', required=True, default=fields.Date.context_today)
    months = fields.Integer(string='จำนวนเดือน', required=True)
    previous_expire = fields.Date(string='หมดอายุเดิม')
    new_expire = fields.Date(string='หมดอายุใหม่', required=True)
    amount = fields.Monetary(string='ค่าบริการ', currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', string='สกุลเงิน',
        default=lambda self: self.env.company.currency_id)
    user_id = fields.Many2one(
        'res.users', string='ผู้บันทึก', default=lambda self: self.env.user)
    note = fields.Char(string='หมายเหตุ')
