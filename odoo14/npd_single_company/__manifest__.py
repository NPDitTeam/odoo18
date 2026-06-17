{
    'name': 'NPD Single Company Switcher',
    'version': '18.0.1.0.0',
    'summary': 'บังคับให้ตัวสลับบริษัทบน navbar เลือกได้ทีละ 1 บริษัทเท่านั้น',
    'description': """
ปรับตัวสลับบริษัท (Switch Company) บน navbar ให้ทำงานแบบ single-company:
- คลิกบริษัทใด = สลับไปบริษัทนั้นบริษัทเดียวทันที (ไม่สะสมหลายบริษัท)
- ซ่อน checkbox เลือกหลายบริษัท / ปุ่ม Confirm-Reset
เพื่อให้ใช้งานง่าย ลดความสับสนจากการ active หลายบริษัทพร้อมกัน
""",
    'category': 'Tools',
    'author': 'NPD',
    'license': 'LGPL-3',
    'depends': ['web'],
    'assets': {
        'web.assets_backend': [
            'npd_single_company/static/src/single_company_switch.js',
            'npd_single_company/static/src/single_company_switch.xml',
            'npd_single_company/static/src/single_company_switch.scss',
        ],
    },
    'installable': True,
    'application': False,
}
