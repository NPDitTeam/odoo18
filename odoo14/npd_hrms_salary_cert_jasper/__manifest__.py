# -*- coding: utf-8 -*-
{
    'name': 'หนังสือรับรองเงินเดือน (Jasper)',
    'version': '18.0.1.0.1',
    'summary': 'ออกหนังสือรับรองเงินเดือนจากข้อมูลพนักงาน เลือกผู้ลงนาม หัวกระดาษตามบริษัทของพนักงาน',
    'description': """
คู่กับ o14 npd_salary_certificate (ผู้ใช้สั่ง 23 ต.ค. 2569)
* เมนู พนักงาน > หนังสือรับรองเงินเดือน
* ชื่อ ตำแหน่ง บริษัท เงินเดือน (+ตัวอักษร) วันเริ่มงาน ระยะเวลาทำงาน ดึงจาก employee.salary แก้ได้ก่อนพิมพ์
* หัวกระดาษ/โลโก้จากบริษัทของพนักงาน โทร/อีเมล/เว็บ/ท้ายกระดาษ ตั้งที่หน้าบริษัท แท็บ หนังสือรับรองเงินเดือน
* ผู้ลงนามตั้งค่าได้ (เริ่มต้น 2 คน)
    """,
    'category': 'Human Resources',
    'author': 'NPD Group',
    'license': 'LGPL-3',
    'depends': ['jasper_reports', 'npd_hrms_base', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/signer_data.xml',
        'data/report_data.xml',
        'views/salary_certificate_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
