"""
Post-installation hooks for vehicle_registration module
"""
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def post_init_hook(cr, registry):
    """สร้าง CRON Job หลังจากติดตั้ง Module"""
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    try:
        # ตรวจสอบว่า CRON มีอยู่หรือไม่
        cron = env['ir.cron'].search([
            ('name', '=', '📱 ส่งแจ้งเตือนการซ่อมไปยัง Microsoft Teams')
        ], limit=1)
        
        if not cron:
            # สร้าง CRON Job ใหม่
            env['ir.cron'].create({
                'name': '📱 ส่งแจ้งเตือนการซ่อมไปยัง Microsoft Teams',
                'model_id': env.ref('vehicle_registration.model_vehicle_maintenance_notification').id,
                'state': 'code',
                'code': """
model = env['vehicle.maintenance.notification']
model._cron_send_maintenance_notifications()
""",
                'interval_number': 1,
                'interval_type': 'days',
                'numbercall': -1,
                'doall': False,
                'active': True,
            })
            _logger.info("✓ สร้าง CRON Job สำเร็จ: 📱 ส่งแจ้งเตือนการซ่อมไปยัง Microsoft Teams")
        else:
            _logger.info("✓ CRON Job มีอยู่แล้ว")
            
    except Exception as e:
        _logger.error(f"✗ ข้อผิดพลาดในการสร้าง CRON: {str(e)}")


def uninstall_hook(cr, registry):
    """ลบ CRON Job เมื่อถอนการติดตั้ง Module"""
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    try:
        cron = env['ir.cron'].search([
            ('name', '=', '📱 ส่งแจ้งเตือนการซ่อมไปยัง Microsoft Teams')
        ])
        
        if cron:
            cron.unlink()
            _logger.info("✓ ลบ CRON Job สำเร็จ")
            
    except Exception as e:
        _logger.error(f"✗ ข้อผิดพลาดในการลบ CRON: {str(e)}")
