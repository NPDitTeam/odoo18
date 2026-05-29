# -*- coding: utf-8 -*-
"""
Quick Test Script for Vehicle Maintenance Notifications
รันไดเร็กต์ใน Odoo Shell

ใช้: python odoo-bin shell -d database_name < test_quick.py
"""

if __name__ == '__main__':
    from odoo import api, SUPERUSER_ID
    
    @api.model
    def test_send_notification(self):
        """ทดสอบส่งแจ้งเตือนสำหรับการซ่อมล่าสุด"""
        
        # ค้นหาการซ่อมล่าสุด
        maintenance = self.env['vehicle.maintenance.history'].search(
            [], limit=1, order='create_date desc'
        )
        
        if not maintenance:
            return {'status': 'error', 'message': '❌ ไม่มีการซ่อมในระบบ'}
        
        # สร้างหรือดึง Notification
        notification = self.env['vehicle.maintenance.notification'].search([
            ('maintenance_id', '=', maintenance.id)
        ], limit=1)
        
        if not notification:
            notification = self.env['vehicle.maintenance.notification'].create({
                'maintenance_id': maintenance.id,
                'notification_enabled': True,
                'notification_interval': 1,  # 1 วัน
                'recipient_ids': [(6, 0, [self.env.user.id])],
            })
        
        # ส่งแจ้งเตือน
        notification.action_send_notification()
        
        return {
            'status': 'success',
            'message': '✅ ส่งแจ้งเตือนสำเร็จ',
            'notification_id': notification.id,
            'maintenance': maintenance.name,
        }
