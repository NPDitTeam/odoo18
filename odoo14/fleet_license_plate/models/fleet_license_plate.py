from odoo import models, fields


class FleetLicensePlate(models.Model):
    _name = 'fleet.license_plate'
    _description = 'ทะเบียนรถ'

    name = fields.Char(string='ป้ายทะเบียน', required=True)
    brand = fields.Char(string='ยี่ห้อรถ')
    model = fields.Char(string='รุ่นรถ')
    year = fields.Integer(string='ปีที่ผลิต')
    employee_id = fields.Many2one('hr.employee', string='พนักงานขับรถ')
    active = fields.Boolean(string='ใช้งานอยู่', default=True)

    _sql_constraints = [
        ('unique_license_plate', 'unique(name)', 'ป้ายทะเบียนนี้มีอยู่ในระบบแล้ว!'),
    ]
