# -*- coding: utf-8 -*-
{
    'name': 'NPD ค้นหาเลขเอกสาร',
    'version': '18.0.1.0.1',
    'summary': 'popup ค้นหาเลขเอกสารทุกประเภทในระบบ พิมพ์แล้วขึ้นรายการทันที เลือกแล้วพาไปหน้าเอกสาร',
    'description': """
ค้นหาเลขเอกสาร (พอร์ตจาก o14 npd_doc_finder)
==============================================
เมนู การออกใบแจ้งหนี้ > ค้นหาเลขเอกสาร

* พิมพ์เลขเอกสารบางส่วน ระบบแสดงรายการที่ตรงทันที พร้อมบอกว่ามาจากเมนูไหน
* เลือกแล้วพาไปเปิดเอกสารนั้นให้เลย (เอกสารต่างบริษัท ระบบติ๊กบริษัทนั้นเพิ่มให้)
* แสดงเฉพาะเอกสารที่ผู้ใช้เปิดได้จริง (สิทธิ + กฎสาขา/บริษัทของเอกสารนั้น)
* เอกสารจากโมดูลใหม่ที่มีเลขรัน + มีเมนู ระบบเพิ่มให้เองทุกคืน 02:00 (ป้ายชื่อ = ชื่อเมนู)
    """,
    'category': 'Accounting',
    'author': 'NPD',
    'license': 'LGPL-3',
    'depends': ['account', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'views/doc_finder_views.xml',
        'data/cron.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'npd_doc_finder/static/src/js/doc_finder.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
