{
    'name': 'NPD ช่องบันทึก (Chatter) ด้านล่างเป็นค่าเริ่มต้น',
    'version': '18.0.1.0.0',
    'summary': 'ผู้ใช้ทุกคนเห็นช่องส่งข้อความ/บันทึกโน้ต/ประวัติ ใต้เอกสารแบบ o14 (เปลี่ยนเองได้ที่การตั้งค่าส่วนตัว)',
    'description': """
ต่อยอด muk_web_chatter (มีฟิลด์ chatter_position ด้านข้าง/ด้านล่าง ในการตั้งค่าส่วนตัวอยู่แล้ว)
- ค่าเริ่มต้น = ด้านล่าง ทั้งผู้ใช้เดิม (ตั้งให้ตอนติดตั้ง) และผู้ใช้ที่สร้างใหม่
- ป้ายภาษาไทย: ตำแหน่งช่องบันทึก (Chatter) / ด้านล่าง / ด้านข้าง
- แก้เอกสารถูกบีบเตี้ยจนมี scrollbar ซ้อนเมื่อช่องบันทึกอยู่ด้านล่างบนจอกว้าง
""",
    'author': 'NPD',
    'license': 'LGPL-3',
    'category': 'Tools/UI',
    'depends': ['muk_web_chatter'],
    'assets': {
        'web.assets_backend': [
            'npd_chatter_bottom/static/src/scss/chatter_bottom.scss',
        ],
    },
    'post_init_hook': '_set_all_users_chatter_bottom',
    'installable': True,
    'application': False,
}
