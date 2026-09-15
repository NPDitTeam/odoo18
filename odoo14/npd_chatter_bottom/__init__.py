from . import models


def _set_all_users_chatter_bottom(env):
    """ตอนติดตั้ง: ผู้ใช้ทุกคน (รวมที่ archive) ใช้ช่องบันทึกด้านล่าง — หลังจากนี้แต่ละคนเปลี่ยนเองได้"""
    env.cr.execute("UPDATE res_users SET chatter_position = 'bottom'")
