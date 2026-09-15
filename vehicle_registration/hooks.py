"""
Post-installation hooks for vehicle_registration module

หมายเหตุการอัปเกรดมา Odoo 18:
  * ลายเซ็น hook เปลี่ยนจาก (cr, registry) เป็น (env) ตั้งแต่ Odoo 17
  * ``ir.cron`` ไม่มีฟิลด์ ``numbercall`` และ ``doall`` แล้ว
ทั้งสองอย่างทำให้ติดตั้งโมดูลนี้บน Odoo 18 ไม่ผ่านมาก่อน
"""
import logging

_logger = logging.getLogger(__name__)

CRON_NAME = '📱 ส่งแจ้งเตือนการซ่อมไปยัง Microsoft Teams'


def post_init_hook(env):
    """สร้าง CRON Job หลังจากติดตั้ง Module"""
    try:
        cron = env['ir.cron'].search([('name', '=', CRON_NAME)], limit=1)
        if cron:
            _logger.info('✓ CRON Job มีอยู่แล้ว')
            return

        env['ir.cron'].create({
            'name': CRON_NAME,
            'model_id': env.ref(
                'vehicle_registration.model_vehicle_maintenance_notification').id,
            'state': 'code',
            'code': (
                "model = env['vehicle.maintenance.notification']\n"
                "model._cron_send_maintenance_notifications()"
            ),
            'interval_number': 1,
            'interval_type': 'days',
            'active': True,
        })
        _logger.info('✓ สร้าง CRON Job สำเร็จ: %s', CRON_NAME)

    except Exception as exc:
        _logger.error('✗ ข้อผิดพลาดในการสร้าง CRON: %s', exc)


def uninstall_hook(env):
    """ลบ CRON Job เมื่อถอนการติดตั้ง Module"""
    try:
        cron = env['ir.cron'].search([('name', '=', CRON_NAME)])
        if cron:
            cron.unlink()
            _logger.info('✓ ลบ CRON Job สำเร็จ')
    except Exception as exc:
        _logger.error('✗ ข้อผิดพลาดในการลบ CRON: %s', exc)
