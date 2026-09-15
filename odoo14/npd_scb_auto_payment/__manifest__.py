# -*- coding: utf-8 -*-
{
    # ชื่อทางเทคนิคยังเป็น npd_scb_auto_payment ตามเดิม (เปลี่ยนไม่ได้ ผูกกับ DB)
    # แต่ชื่อที่ผู้ใช้เห็นเปลี่ยนให้ตรงกับงานจริง = ตรวจสอบการโอน ไม่ใช่สร้างใบรับชำระ
    'name': 'NPD ตรวจสอบการโอนเงิน',
    # พอร์ตจาก o14 14.0.5.6.0 — o18: ใบที่ลงบันทึกแล้ว = state in_process/paid (ไม่มี posted)
    'version': '18.0.1.0.0',
    'summary': 'ตรวจสอบการโอนเงินของใบรับชำระ โดยให้ AI อ่านสลิปแล้วเทียบกับรายการเดินบัญชีจริง',
    'description': """
NPD ตรวจสอบการโอนเงิน
=====================
ตรวจสอบการโอนที่ "หน้ารับชำระ" (account.payment)

- พนักงานสร้างใบรับชำระเอง แล้วแนบสลิปการโอน (รูปภาพ/PDF) ในเอกสารแนบ
- AI (Gemini ตัวเดียวกับปุ่ม "ใช้วันที่จากสลิป") อ่านสลิป -> ชื่อผู้โอน / จำนวนเงิน / วันที่
- จับคู่กับรายการเดินบัญชีจริงของธนาคาร (npd.scb.bank.statement ดึงจาก Google Sheet
  แท็บ statement_*) โดยเทียบ ชื่อบริษัท + จำนวนเงิน + วันที่
- ข้อมูลธนาคารมาช้ากว่าจริง ~1 วัน จึงตรวจเมื่อพ้นวันที่ในใบรับชำระไปแล้ว
  (โอนวันนี้ -> ตรวจพรุ่งนี้)
- แสดงผลบนหน้ารับชำระ: โอนสำเร็จ / ไม่สำเร็จ (พร้อมเหตุผลว่าไม่สำเร็จเพราะอะไร)
- เมนู "ผลตรวจสอบการโอน" รวมรายการที่ไม่สำเร็จ/รอตรวจ กดแล้วเข้าหน้ารับชำระได้ทันที
""",
    'category': 'Accounting',
    'author': 'NPD S Group',
    'license': 'AGPL-3',
    'depends': [
        'base',
        'account',
        'web',
        'account_payment_invoice',
        # ใช้ตัวอ่านสลิปด้วย AI ตัวเดียวกับปุ่ม "ใช้วันที่จากสลิป"
        'payment_slip_date_ai',
        # แหล่งข้อมูลรายการเดินบัญชีจริงของธนาคาร (Google Sheet)
        'npd_scb_cashflow',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/scb_verify_cron.xml',
        'views/account_payment_views.xml',
        'views/scb_counterparty_alias_views.xml',
        'views/res_config_settings_views.xml',
    ],
    # ตอนติดตั้งใหม่ ตั้ง "วันที่เริ่มตรวจสอบ" = วันที่ติดตั้ง
    # กัน cron กวาดใบรับชำระเก่าทั้งฐานข้อมูลมาเรียก AI จนโควตาหมด
    'post_init_hook': '_scb_set_default_start_date',
    'installable': True,
    'application': False,
    'auto_install': False,
}
