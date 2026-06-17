{
    'name': 'NPD : Generate Sub Sequences',
    'version': '18.0.1.0.0',
    'summary': 'กำหนด/สร้างเลขรันเอกสารแบบ sub-sequence ราย วัน/เดือน ต่อช่วงวันที่ (รองรับหลายบริษัทใน DB เดียว)',
    'description': """
รวมความสามารถจาก Odoo 14 (pfb_generate_subsequences + fiscal_year_sequence_extensible)
มาไว้ในโมดูลเดียวสำหรับ Odoo 18:

1. เพิ่มฟิลด์ prefix / suffix ให้กับ "ช่วงวันที่ของลำดับ" (ir.sequence.date_range)
   และ override การออกเลขให้ใช้ prefix/suffix ของแต่ละช่วงวันที่
   ผ่านตัวแปร %(prefix)s / %(suffix)s ใน prefix/suffix ของ sequence หลัก
2. ปุ่ม "Generate Sub Sequences" บนฟอร์ม ir.sequence เพื่อสร้างช่วงวันที่
   อัตโนมัติทั้งปี (ราย วัน หรือ ราย เดือน)

รองรับหลายบริษัทใน DB เดียว: สร้าง 1 sequence ต่อบริษัท (code เดียวกัน คนละ company)
แล้ว next_by_code จะเลือก sequence ของบริษัทที่กำลังใช้งานเอง — sub-sequence
แยกตาม sequence/บริษัทโดยอัตโนมัติ
""",
    'author': 'NPD',
    'category': 'Tools',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/generate_subsequences_view.xml',
    ],
    'installable': True,
    'application': False,
}
