# -*- coding: utf-8 -*-
"""ตารางจับคู่ระเบียนระหว่าง Odoo 14 กับ Odoo 18

เลข id ของสองฐานเป็นคนละชุดกัน จะเอา id ฝั่ง 14 มาใช้ตรง ๆ ไม่ได้
ที่นี่จึงจดไว้ว่าแถว id เท่าไรของฝั่ง 14 กลายเป็นแถวไหนของฝั่ง 18
ใช้สองเรื่อง

1. รอบถัดไปรู้ได้ทันทีว่าต้องไปแก้แถวไหน ไม่ต้องไล่หาด้วยกุญแจธรรมชาติซ้ำ
2. ฟิลด์ที่ชี้ไปโมเดลอื่น (many2one) แปลงเลขข้ามฐานได้ เช่น สลิปฝั่ง 14
   ชี้ไปพนักงาน id 57 ต้องแปลงเป็นพนักงานคนเดียวกันซึ่งฝั่ง 18 เป็น id อื่น

ไม่ผูก ondelete กับระเบียนปลายทาง ถ้าฝั่ง 18 ลบแถวทิ้ง รายการจับคู่จะค้างไว้
แล้วถูกล้างตอนรอบถัดไปตรวจเจอว่าปลายทางหายไป ทำแบบนี้เพื่อให้เห็นร่องรอย
ว่าเคยมีการลบเกิดขึ้น แทนที่จะหายเงียบไปพร้อมกัน
"""
import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class HrmsSyncMap(models.Model):
    _name = 'npd.hrms.sync.map'
    _description = 'การจับคู่ระเบียน Odoo 14 กับ Odoo 18'
    _order = 'o14_model, o14_id'
    _rec_name = 'o14_model'

    o14_model = fields.Char(string='โมเดลฝั่ง 14', required=True, index=True)
    o14_id = fields.Integer(string='id ฝั่ง 14', required=True, index=True)
    res_model = fields.Char(string='โมเดลฝั่ง 18', required=True, index=True)
    res_id = fields.Integer(string='id ฝั่ง 18', required=True, index=True)
    natural_key = fields.Char(string='กุญแจที่ใช้จับคู่',
                              help='ค่าที่ใช้หาคู่ตอนแรก เก็บไว้ให้ตรวจย้อนได้')
    o14_write_date = fields.Datetime(
        string='แก้ไขล่าสุดฝั่ง 14',
        help='ใช้ตัดสินว่ารอบถัดไปต้องดึงแถวนี้มาอีกไหม')

    _sql_constraints = [
        ('o14_uniq', 'unique(o14_model, o14_id)',
         'แถวนี้ของฝั่ง 14 ถูกจับคู่ไว้แล้ว'),
    ]

    # ------------------------------------------------------------------
    @api.model
    def lookup(self, o14_model, o14_id):
        """หา id ฝั่ง 18 จาก id ฝั่ง 14 — ไม่เจอคืน False"""
        if not o14_id:
            return False
        record = self.search([('o14_model', '=', o14_model),
                              ('o14_id', '=', o14_id)], limit=1)
        return record.res_id if record else False

    @api.model
    def lookup_many(self, o14_model, o14_ids):
        """แปลงหลาย id พร้อมกัน — คืน dict {id14: id18}

        ใช้ตอนซิงก์ทีละชุด จะได้ไม่ต้องยิงค้นทีละแถว
        """
        if not o14_ids:
            return {}
        records = self.search_read(
            [('o14_model', '=', o14_model), ('o14_id', 'in', list(o14_ids))],
            ['o14_id', 'res_id'])
        return {row['o14_id']: row['res_id'] for row in records}

    @api.model
    def remember(self, o14_model, o14_id, record, natural_key=False,
                 o14_write_date=False):
        """จดคู่ใหม่ หรืออัปเดตคู่เดิม"""
        existing = self.search([('o14_model', '=', o14_model),
                                ('o14_id', '=', o14_id)], limit=1)
        values = {
            'res_model': record._name,
            'res_id': record.id,
            'natural_key': natural_key or False,
            'o14_write_date': o14_write_date or False,
        }
        if existing:
            existing.write(values)
            return existing
        values.update({'o14_model': o14_model, 'o14_id': o14_id})
        return self.create(values)

    @api.model
    def known_write_dates(self, o14_model):
        """คืน {id14: วันที่แก้ไขล่าสุดที่เคยดึงมา} ของโมเดลนี้

        เอนจินเอาไปเทียบว่าแถวไหนเปลี่ยนแล้วบ้าง จะได้ข้ามแถวที่ไม่ขยับ
        """
        rows = self.search_read([('o14_model', '=', o14_model)],
                                ['o14_id', 'o14_write_date'])
        return {row['o14_id']: row['o14_write_date'] for row in rows}

    @api.model
    def drop_dangling(self, o14_model):
        """ล้างคู่ที่ปลายทางฝั่ง 18 ถูกลบไปแล้ว

        ถ้าไม่ล้าง รอบถัดไปจะคิดว่าแถวนี้ซิงก์แล้วและข้ามไป ทำให้ข้อมูลหาย
        """
        dropped = 0
        for chunk in self.search([('o14_model', '=', o14_model)]):
            target = self.env[chunk.res_model].browse(chunk.res_id).exists()
            if not target:
                chunk.unlink()
                dropped += 1
        if dropped:
            _logger.info('[HRMS-SYNC] ล้างการจับคู่ที่ปลายทางหายไป %s แถว (%s)',
                         dropped, o14_model)
        return dropped
