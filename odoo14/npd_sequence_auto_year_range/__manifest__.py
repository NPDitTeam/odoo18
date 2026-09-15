# -*- coding: utf-8 -*-
{
    'name': 'NPD Sequence: Auto Yearly Sub Sequences',
    'version': '18.0.1.1.0',
    'summary': 'ขึ้นปีใหม่ สร้างช่วงเลขรันเอกสาร (Sub Sequences) ของปีนั้นให้อัตโนมัติ ตามรูปแบบล่าสุด',
    'description': """
สร้าง Sub Sequences ปีใหม่อัตโนมัติ (พอร์ตจาก Odoo 14)
==================================================
เดิมทุกต้นปีต้องเปิดทีละ Sequence ที่ติ๊ก "Use subsequences per date_range"
แล้วกด Generate Sub Sequences ใส่รูปแบบ/ปีเอง (ใน DB เดียวมี Sequence ของทุกบริษัท)

โมดูลนี้เพิ่มการกระทำที่กำหนดไว้ (Scheduled Action) รันทุกปี 00:01 น. วันที่ 1 ม.ค. (เวลาไทย)

* อ่านชุดล่าสุดของปีก่อน (ช่วงที่สร้างพร้อมกันและครบทั้งปี) ของแต่ละ Sequence ทุกบริษัท
* เดารูปแบบ prefix/suffix จากข้อมูลจริง: ปี ค.ศ./พ.ศ. (4 หรือ 2 หลัก) เดือน วัน และข้อความคงที่
  แล้วตรวจว่ารูปแบบนั้นสร้างค่าเดิมได้ตรงทุกช่วงก่อนใช้
* สร้างช่วงของปีใหม่แบบเดียวกัน (รายวัน / รายเดือน / ทั้งปี) ข้ามวันที่มีช่วงอยู่แล้ว
  รันซ้ำได้ไม่สร้างซ้ำ
* Sequence ที่ prefix ว่าง (Odoo สร้างช่วงทั้งปีให้เองอยู่แล้ว) จะข้าม
* สรุปผลเก็บที่ ตั้งค่า > เทคนิค > Logging (โหมดนักพัฒนา)

เรื่องเวลา: nextcall ของ cron Odoo เก็บเป็น UTC เสมอ จึงตั้งไว้ 17:01 UTC ของ 31 ธ.ค.
(= 00:01 น. 1 ม.ค. เวลาไทย) และปีที่จะสร้างคำนวณจากเวลาไทย ไม่ใช่วันที่ของ server
""",
    'category': 'Technical',
    'author': 'NPD Dev',
    'license': 'LGPL-3',
    'depends': [
        'base',
        # ฟิลด์ prefix/suffix บน ir.sequence.date_range + ปุ่ม Generate Sub Sequences
        'npd_generate_subsequences',
    ],
    'data': [
        'data/ir_cron.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
}
