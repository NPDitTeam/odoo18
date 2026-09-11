# -*- coding: utf-8 -*-
"""ข้อมูลแรงงานต่างชาติ — แท็บ "ข้อมูลต่างชาติ" บนหน้าข้อมูลพนักงาน

ย้ายมาจากชีทติดตามเอกสารของ HR (บัตรชมพู / Passport / ใบอนุญาตทำงาน /
การต่อเอกสาร) ให้อยู่ในทะเบียนพนักงานที่เดียว — พอร์ตจาก Odoo 14 (employee_salary)

เลขที่ Passport (passport_number) นิยามอยู่ใน employee_salary.py และแอปอ่านอยู่
จึงไม่ย้ายนิยามฟิลด์ ย้ายแค่ตำแหน่งบนฟอร์มมาไว้แท็บนี้
"""
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

# ชีทเดิมให้ "ขึ้นสีแดงก่อนหนึ่งเดือน"
FOREIGN_DOC_WARN_MONTHS = 1


class HrmsForeignDocStatus(models.Model):
    """สถานะการต่อเอกสาร เช่น "ครบ 2 ปีแรก"

    เป็นตารางแทน selection เพราะ HR เพิ่ม/แก้ชื่อสถานะเองได้ทันที
    ไม่ต้องรอแก้โค้ดทุกครั้งที่ขั้นตอนของกรมการจัดหางานเปลี่ยน
    ใช้ร่วมทุกบริษัท (ขั้นตอน MOU เหมือนกันทุกนายจ้าง)
    """
    _name = 'hrms.foreign.doc.status'
    _description = 'สถานะการต่อเอกสารแรงงานต่างชาติ'
    _order = 'sequence, id'

    name = fields.Char(string='สถานะ', required=True)
    sequence = fields.Integer(string='ลำดับ', default=10)
    active = fields.Boolean(string='ใช้งาน', default=True)


class EmployeeSalaryForeignWorker(models.Model):
    _inherit = 'employee.salary'

    # ---- บัตรชมพู ----
    pink_card_issue_date = fields.Date(string='วันออกบัตรชมพู')
    pink_card_expiry_date = fields.Date(string='วันหมดอายุบัตรชมพู', tracking=True)

    # ---- หนังสือเดินทาง (passport_number อยู่ใน employee_salary.py) ----
    passport_issue_date = fields.Date(string='วันออก Passport')
    passport_expiry_date = fields.Date(string='วันหมด Passport', tracking=True)

    # ---- ข้อมูลนายจ้าง ----
    employer_business_type = fields.Char(
        string='ประเภทกิจการ', help='เช่น ผลิตหรือจำหน่ายวัสดุก่อสร้าง')
    employer_workplace = fields.Text(string='สถานที่ทำงาน')

    # ---- ใบอนุญาตทำงาน (Work Permit) ----
    work_permit_issue_date = fields.Date(string='ออก Permit ให้วันที่')
    work_permit_expiry_date = fields.Date(
        string='อนุญาตให้ทำงานถึงวันที่', tracking=True,
        help='ใช้คู่กับการเป็นผู้ประกันตนตามกฎหมายประกันสังคม\n'
             'ระบบจะเตือนสีแดงก่อนหมดอายุ 1 เดือน')

    # ---- การต่อเอกสาร ----
    foreign_doc_status_id = fields.Many2one(
        'hrms.foreign.doc.status', string='สถานะการต่อเอกสาร', tracking=True)
    return_trip_date = fields.Date(string='เดินทางกลับเพื่อต่อสถานะ')
    work_permit_renewal_date = fields.Date(
        string='ยื่นคำขอต่ออายุใบอนุญาตทำงาน', help='วันที่ยื่นคำขอต่ออายุ Work Permit')
    bt50_submit_date = fields.Date(
        string='ยื่น บต.50',
        help='วันที่ยื่น บต.50 ผ่านระบบอิเล็กทรอนิกส์ของกรมการจัดหางาน')
    foreign_doc_note = fields.Text(string='หมายเหตุเอกสารต่างชาติ')

    # ---- เตือนใกล้หมดอายุ ----
    pink_card_expiring = fields.Boolean(compute='_compute_foreign_doc_expiring')
    passport_expiring = fields.Boolean(compute='_compute_foreign_doc_expiring')
    work_permit_expiring = fields.Boolean(compute='_compute_foreign_doc_expiring')
    foreign_doc_expiring = fields.Boolean(
        string='เอกสารต่างชาติใกล้หมดอายุ', compute='_compute_foreign_doc_expiring')

    @api.depends('pink_card_expiry_date', 'passport_expiry_date', 'work_permit_expiry_date')
    def _compute_foreign_doc_expiring(self):
        """ไม่ store — "วันนี้" ขยับทุกวัน ถ้าเก็บค่าไว้จะค้างเป็นของเมื่อวาน
        รวมกรณีเลยวันหมดอายุไปแล้วด้วย (ยิ่งต้องแดง)
        """
        cutoff = fields.Date.context_today(self) + relativedelta(months=FOREIGN_DOC_WARN_MONTHS)
        for rec in self:
            rec.pink_card_expiring = bool(
                rec.pink_card_expiry_date and rec.pink_card_expiry_date <= cutoff)
            rec.passport_expiring = bool(
                rec.passport_expiry_date and rec.passport_expiry_date <= cutoff)
            rec.work_permit_expiring = bool(
                rec.work_permit_expiry_date and rec.work_permit_expiry_date <= cutoff)
            rec.foreign_doc_expiring = (rec.pink_card_expiring
                                        or rec.passport_expiring
                                        or rec.work_permit_expiring)
