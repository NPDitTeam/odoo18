# -*- coding: utf-8 -*-
{
    'name': 'แบบฟอร์มหนังสือรับรองหักภาษี ณ ที่จ่าย (50 ทวิ)',
    'version': '18.0.1.0.0',
    'summary': 'พิมพ์หนังสือรับรองหักภาษี ณ ที่จ่าย ลงแบบฟอร์มราชการ',
    'description': """
แบบฟอร์มหนังสือรับรองหักภาษี ณ ที่จ่าย (50 ทวิ)
================================================
พิมพ์ทับแบบฟอร์มราชการ พร้อมช่องเลขผู้เสียภาษีแบบแยกหลัก
และแปลงจำนวนเงินเป็นตัวอักษรภาษาไทย

โลโก้ดึงจากข้อมูลบริษัทที่พนักงานสังกัด ไม่ใช่รายชื่อที่ฝังไว้ในเทมเพลต
จึงถูกต้องทั้งกรณีหลายบริษัทและกรณีปล่อยเช่าให้ลูกค้าใช้
    """,
    'category': 'Human Resources',
    'author': 'NPD Group',
    'license': 'LGPL-3',
    'depends': ['web', 'npd_hr_wt_cert'],
    'data': [
        'data/paper_format.xml',
        'reports/hr_wt_cert_form_view.xml',
        'reports/hr_wt_cert_form.xml',
    ],
    'assets': {
        'web.report_assets_common': [
            'npd_hr_wt_cert_form/static/scss/style_report.scss',
        ],
    },
    'installable': True,
    'application': False,
}
