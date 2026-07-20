# -*- coding: utf-8 -*-
from datetime import datetime

import pytz

from odoo import models, fields, api

BKK_TZ = 'Asia/Bangkok'


def _to_bangkok(dt):
    """แปลง Datetime ของ Odoo (UTC, naive) เป็นเวลาไทย"""
    if not dt:
        return False
    return pytz.utc.localize(dt).astimezone(pytz.timezone(BKK_TZ))


# ตัวคั่นบรรทัดที่ปลอดภัยสำหรับ CSV ของ jasper_reports (ห้ามใช้ newline จริง
# เพราะจะทำให้ JRCsvDataSource อ่านเรกคอร์ดผิด) — ฝั่ง JRXML จะ split ด้วยตัวนี้
QC_LINE_SEPARATOR = '||'

# จำนวนบรรทัดของตาราง "รายการสินค้าที่ลูกค้าต้องการเพิ่ม" ในรายงาน
# ต้องตรงกับจำนวนแถวที่วางไว้ใน qc_checklist.jrxml เสมอ
# (JRXML วาดเส้นตารางแบบแถวต่อแถว จึงต้องกำหนดจำนวนแถวสูงสุดไว้ล่วงหน้า
#  แถวที่ไม่มีข้อมูลจะถูกยุบทิ้งด้วย isRemoveLineWhenBlank)
QC_EXTRA_SLOTS = 10


class VehicleBooking(models.Model):
    _inherit = 'vehicle.booking'

    # ------------------------------------------------------------------
    # หมายเหตุ: "เที่ยวส่งเลขที่" ในรายงานใช้เลขรันเอกสาร (field name) ของ
    # vehicle.booking โดยตรง จึงไม่มีเลขรันเฉพาะของ QC อีกต่อไป
    # ------------------------------------------------------------------
    # ฟิลด์สำหรับ Jasper (แยกวันที่ / เวลา จาก "วันเวลาออกเดินทางจริง")
    # ------------------------------------------------------------------
    jasper_qc_delivery_date = fields.Char(
        string='QC: วันที่ออกเดินทางจริง',
        compute='_compute_jasper_qc_delivery_datetime',
    )
    jasper_qc_delivery_time = fields.Char(
        string='QC: เวลาออกเดินทางจริง',
        compute='_compute_jasper_qc_delivery_datetime',
    )

    @api.depends('planned_start_date_t')
    def _compute_jasper_qc_delivery_datetime(self):
        for record in self:
            local_dt = _to_bangkok(record.planned_start_date_t)
            if local_dt:
                record.jasper_qc_delivery_date = '%s/%s/%s' % (
                    local_dt.strftime('%d'),
                    local_dt.strftime('%m'),
                    local_dt.year + 543,
                )
                record.jasper_qc_delivery_time = local_dt.strftime('%H:%M')
            else:
                record.jasper_qc_delivery_date = ''
                record.jasper_qc_delivery_time = ''

    # ------------------------------------------------------------------
    # รายการสินค้าที่ลูกค้าต้องการเพิ่ม — ดึงเฉพาะ "ชื่อสินค้า" (ไม่เอาจำนวน)
    # เก็บเป็นบรรทัดเดียวคั่นด้วย QC_LINE_SEPARATOR แล้วให้ JRXML แปลงกลับเป็น
    # newline ตอนแสดงผล
    # ------------------------------------------------------------------
    jasper_qc_extra_items = fields.Char(
        string='QC: รายการสินค้าที่ลูกค้าต้องการเพิ่ม',
        compute='_compute_jasper_qc_extra_items',
    )
    jasper_qc_extra_more = fields.Char(
        string='QC: หมายเหตุรายการที่เกินตาราง',
        compute='_compute_jasper_qc_extra_items',
    )

    @api.depends('transport_order_id.order_line_ids.product_name_o14',
                 'transport_order_id.order_line_ids.product_id')
    def _compute_jasper_qc_extra_items(self):
        for record in self:
            names = []
            for index, line in enumerate(record.order_line_ids, start=1):
                name = line.product_name_o14 or line.product_id.display_name or ''
                names.append('%d. %s' % (index, name))

            shown, overflow = names[:QC_EXTRA_SLOTS], names[QC_EXTRA_SLOTS:]

            # เติมช่องว่างให้ครบ QC_EXTRA_SLOTS เสมอ เพื่อให้ split() ฝั่ง JRXML
            # ได้จำนวน element คงที่ ไม่เกิด ArrayIndexOutOfBounds ตอน render
            shown += [''] * (QC_EXTRA_SLOTS - len(shown))

            record.jasper_qc_extra_items = QC_LINE_SEPARATOR.join(shown)
            record.jasper_qc_extra_more = (
                'และอีก %d รายการ (ดูรายการทั้งหมดในตารางตรวจสอบด้านบน)' % len(overflow)
                if overflow else ''
            )

    # ------------------------------------------------------------------
    # เวลาที่พิมพ์เอกสาร
    # ------------------------------------------------------------------
    jasper_qc_print_datetime = fields.Char(
        string='QC: เวลาพิมพ์',
        compute='_compute_jasper_qc_print_datetime',
    )

    def _compute_jasper_qc_print_datetime(self):
        now = datetime.now(pytz.timezone(BKK_TZ)).strftime('%d-%m-%Y %H:%M:%S')
        for record in self:
            record.jasper_qc_print_datetime = now


class TransportOrderLine(models.Model):
    _inherit = 'transport.order.line'

    jasper_qc_product_name = fields.Char(
        string='QC: ชื่อสินค้า',
        compute='_compute_jasper_qc_product_name',
    )

    @api.depends('product_name_o14', 'product_id')
    def _compute_jasper_qc_product_name(self):
        for line in self:
            line.jasper_qc_product_name = (
                line.product_name_o14 or line.product_id.display_name or ''
            )

    jasper_qc_quantity = fields.Char(
        string='QC: จำนวน + หน่วย',
        compute='_compute_jasper_qc_quantity',
    )

    @api.depends('quantity', 'uom_name')
    def _compute_jasper_qc_quantity(self):
        for line in self:
            qty = line.quantity or 0.0
            # ตัด .00 ออกถ้าเป็นจำนวนเต็ม
            if abs(qty - round(qty)) < 0.005:
                qty_text = '{:,.0f}'.format(qty)
            else:
                qty_text = '{:,.2f}'.format(qty)
            if line.uom_name:
                qty_text = '%s %s' % (qty_text, line.uom_name)
            line.jasper_qc_quantity = qty_text
