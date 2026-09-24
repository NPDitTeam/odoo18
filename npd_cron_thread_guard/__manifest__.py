# -*- coding: utf-8 -*-
{
    'name': 'กันเธรด cron ตาย (NPD)',
    'version': '18.0.1.0.0',
    'summary': 'แก้บั๊กแกน Odoo ที่ทำให้งานตั้งเวลาหยุดทั้งระบบจนกว่าจะรีสตาร์ต',
    'description': """
กันเธรด cron ตาย
================
เมื่อรันแบบ workers = 0 เธรด cron จะไล่อ่านรายการฐานข้อมูลใน
odoo/service/server.py ด้วย registries.d.items() ซึ่งไม่ได้ถือล็อก
ถ้าจังหวะนั้นมีเธรดเว็บโหลดหรือปลดฐานข้อมูลอยู่ Python จะโยน
RuntimeError: OrderedDict mutated during iteration แล้วเธรด cron ตายถาวร
ไม่ฟื้นเอง งานตั้งเวลาทั้งระบบจึงหยุดจนกว่าจะรีสตาร์ต

โมดูลนี้เปลี่ยนที่เก็บรายการฐานข้อมูลให้คืนสำเนาเวลาไล่อ่าน การไล่อ่านจึงไม่
สะดุดแม้มีการแก้ไขพร้อมกัน ไม่ได้แตะไฟล์แกน จึงอยู่รอดตอนสร้างคอนเทนเนอร์ใหม่
    """,
    'author': 'NPD',
    'category': 'Technical',
    'depends': ['base'],
    'installable': True,
    'application': False,
    'auto_install': True,
}
