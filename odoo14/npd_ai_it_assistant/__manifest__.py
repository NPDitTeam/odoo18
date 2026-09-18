# -*- coding: utf-8 -*-
{
    'name': 'NPD - ตัวช่วย AI-IT (AI-IT Assistant)',
    # พอร์ตจาก o14 14.0.1.9.0
    'version': '18.0.1.4.0',
    'category': 'Productivity/Discuss',
    'summary': 'แท็บ "ตัวช่วย AI-IT" ในกล่องสนทนา ให้พนักงานแจ้งปัญหาเป็นหัวข้อ แล้วให้ AI แก้ให้',
    'description': """
ตัวช่วย AI-IT (Odoo 18)
=======================
เพิ่มแท็บ "ตัวช่วย AI-IT" ในเมนูสนทนา (ข้าง ๆ ทั้งหมด / แชท / ช่อง)
เลือกหัวข้อแล้วระบบเปิดห้องแชทกับ "ตัวช่วย AI-IT" คุยกันเป็นขั้นตอน

หัวข้อ
    1. แก้ปัญหาตัดสต็อกไม่ได้เนื่องจากสต็อกไม่พอ (เติมสต๊อกคลังสาขา + สั่งตัดสต๊อกต่อ)
    2. แก้ไขวันที่ใบแจ้งหนี้ (ร่าง = แก้วันที่ / ลงบันทึกแล้ว = ยกเลิกการชำระ + ยกเลิกใบ)
    3. แก้ไขวันที่คืนสินค้า
    4. แก้ไขสถานะการเช่า (ถอยจากปิดบิล)
    5. แก้การปัดเศษ VAT ในใบแจ้งหนี้ (สลับแบบยอดรวม/รายบรรทัด)

ประวัติการแก้: บัญชี > การรายงาน > ประวัติการแก้ AI-IT
ล้างประวัติแชทเก่าทุกวันตี 4 (System Parameter npd_ai_it_assistant.chat_history_days)
ใช้ Gemini API key เดียวกับโมดูล AI เดิม (advance_clear_ai_check.gemini_api_key)

ต่างจาก o14
    - ห้องแชทเป็น discuss.channel, หน้าจอ JS เขียนใหม่เป็น OWL ของ Odoo 18
    - ใบรับชำระที่ลงบันทึกแล้วคือสถานะ in_process/paid (o18 ไม่มี posted)
    - บรรทัดสินค้าในใบแจ้งหนี้ใช้ display_type = product (ไม่มี exclude_from_invoice_tab)
    - สินค้าที่ต้องตัดสต๊อก = is_storable
    """,
    'author': 'NPD Dev',
    'license': 'LGPL-3',
    'depends': [
        'mail',
        'stock',
        'sale_stock',
        'account',
        # res.branch + branch_id บน users/เอกสาร/คลัง ของ o18
        'multi_branch_management_aagam',
    ],
    'post_init_hook': 'post_init_hook',
    'data': [
        'security/ai_it_security.xml',
        'security/ir.model.access.csv',
        'data/ai_it_bot_data.xml',
        'data/ai_it_topic_data.xml',
        'data/ai_it_cron_data.xml',
        'views/ai_it_topic_views.xml',
        'views/ai_it_session_views.xml',
        'views/ai_it_menus.xml',
        # ต้องมาหลัง ai_it_menus.xml เพราะเมนูประวัติอ้าง menu_npd_ai_it_root
        'views/ai_it_history_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'npd_ai_it_assistant/static/src/**/*.js',
            'npd_ai_it_assistant/static/src/**/*.xml',
            'npd_ai_it_assistant/static/src/**/*.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
