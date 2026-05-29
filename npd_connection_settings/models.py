from odoo import models, fields


class ConnectionConfig(models.Model):
    _name = 'npd.connection.config'
    _description = 'NPD Connection Configuration'
    _rec_name = 'name'

    name = fields.Char(
        string='Connection Name',
        required=True,
        help='ชื่อการเชื่อมต่อ (เช่น NPD Main, NPD Dev)'
    )
    
    is_active = fields.Boolean(
        string='Active',
        default=False,
        help='ตั้งเป็นการเชื่อมต่อที่ใช้งานอยู่'
    )
    
    # Connection Details
    server_url = fields.Char(
        string='Server URL/IP',
        required=True,
        help='URL หรือ IP ของเซิร์ฟเวอร์ (เช่น https://npd-solution.com หรือ http://192.168.1.100:8070)'
    )
    
    database_name = fields.Char(
        string='Database Name',
        required=True,
        help='ชื่อฐานข้อมูล Odoo (เช่น NPD_Logistics)'
    )
    
    username = fields.Char(
        string='Username',
        required=True,
        help='ชื่อผู้ใช้ Odoo'
    )
    
    password = fields.Char(
        string='Password',
        required=True,
        help='รหัสผ่าน Odoo'
    )
    
    # Additional Info
    description = fields.Text(
        string='Description',
        help='หมายเหตุเพิ่มเติมเกี่ยวกับการเชื่อมต่อนี้'
    )
    
    # Metadata
    created_date = fields.Datetime(
        string='Created Date',
        default=fields.Datetime.now,
        readonly=True
    )
    
    last_modified = fields.Datetime(
        string='Last Modified',
        default=fields.Datetime.now,
        readonly=True
    )
    
    def write(self, vals):
        """Update last_modified when record is updated"""
        vals['last_modified'] = fields.Datetime.now()
        return super().write(vals)
    
    def get_connection_dict(self):
        """Return connection settings as a dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'server_url': self.server_url,
            'database_name': self.database_name,
            'username': self.username,
            'password': self.password,
            'is_active': self.is_active,
        }
