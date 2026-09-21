# -*- coding: utf-8 -*-
from odoo import models, fields, tools


class RentalReturnTracking(models.Model):
    """ตรวจสอบการตัดสต๊อกที่ยังไม่คืน (ระดับเอกสาร) ผ่าน SQL View

    เป็น PostgreSQL View (_auto = False) คำนวณ 'สด' จากตารางจริงทุกครั้งที่เปิด
    ไม่ต้องมี cron / ปุ่มรีเฟรช

    1 แถว = 1 ใบตัด (stock.move ที่เป็นใบส่งออก 'เสร็จสิ้น' และไม่ใช่ใบคืน)
      - qty_cut         : จำนวนที่ตัดออก (product_qty ของ move)
      - qty_returned    : จำนวนที่คืนกลับแล้ว (รวม move ที่อ้างอิงกลับผ่าน
                          origin_returned_move_id ที่เสร็จสิ้น)
      - qty_outstanding : จำนวนที่ยังค้างคืน = GREATEST(qty_cut - qty_returned, 0)
      - return_state    : not_returned / partial / returned

    นิยาม 'ตัด/คืน' ใช้ตรรกะเดียวกับ so_auto_stock_cut และ
    npd_rental_stock_overview:
      ใบตัด   = move state=done, picking outgoing, origin_returned_move_id IS NULL
      จำนวนคืน = move state=done ที่อ้างอิงกลับผ่าน origin_returned_move_id
      สาขา     = branch ของคลังต้นทาง (fallback: branch ของ picking -> ของบิลขาย)

    ยอด qty_outstanding รวมต่อ (สินค้า x สาขา) จะตรงกับ qty_rented
    ในรายงาน dev.rental.stock.overview (เจาะลึกว่ายอดนั้นมาจากเอกสารใดบ้าง)

    ต่างจาก Odoo 14: ทุกบริษัทอยู่ฐานเดียวกัน จึงเพิ่มคอลัมน์ 'บริษัท' ให้กรอง/จัดกลุ่มได้
    """
    _name = 'dev.rental.return.tracking'
    _description = 'ตรวจสอบการตัดสต๊อกที่ยังไม่คืน'
    _auto = False
    _order = 'end_rent_date, cut_date, product_id'
    _rec_name = 'picking_id'

    company_id = fields.Many2one('res.company', string='บริษัท', readonly=True)
    picking_id = fields.Many2one('stock.picking', string='ใบตัดสต๊อก', readonly=True)
    picking_name = fields.Char(
        string='เลขที่ใบตัด', related='picking_id.name', readonly=True)
    sale_id = fields.Many2one('sale.order', string='ใบสั่งขาย/เช่า', readonly=True)
    partner_id = fields.Many2one('res.partner', string='ลูกค้า', readonly=True)
    branch_id = fields.Many2one('res.branch', string='สาขา', readonly=True)

    product_id = fields.Many2one('product.product', string='สินค้า', readonly=True)
    product_code = fields.Char(
        string='รหัสสินค้า', related='product_id.default_code', readonly=True)
    product_name = fields.Char(
        string='ชื่อสินค้า', related='product_id.name', readonly=True)
    uom_name = fields.Char(
        string='หน่วย', related='product_id.uom_id.name', readonly=True)

    cut_date = fields.Datetime(string='วันที่ตัดสต๊อก', readonly=True)
    start_rent_date = fields.Date(string='เริ่มเช่า', readonly=True)
    end_rent_date = fields.Date(string='ครบกำหนดคืน', readonly=True)

    qty_cut = fields.Float(
        string='จำนวนที่ตัด', readonly=True, digits='Product Unit of Measure')
    qty_returned = fields.Float(
        string='จำนวนที่คืนแล้ว', readonly=True, digits='Product Unit of Measure')
    qty_outstanding = fields.Float(
        string='ค้างคืน', readonly=True, digits='Product Unit of Measure',
        help='จำนวนที่ตัดออกไปแล้วแต่ยังไม่ได้คืน = จำนวนที่ตัด - จำนวนที่คืนแล้ว')

    return_state = fields.Selection([
        ('not_returned', 'ยังไม่คืน'),
        ('partial', 'คืนบางส่วน'),
        ('returned', 'คืนครบแล้ว'),
    ], string='สถานะการคืน', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self._cr, self._table)

        # กันกรณี DB ไม่ได้ติดตั้งโมดูล customs (ไม่มีคอลัมน์ pfb_so_type)
        # -> ถ้าไม่มี ให้รวมทุกใบส่งออก done (อาจปนสินค้าขายขาด) แทนที่จะพัง
        self._cr.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'sale_order' AND column_name = 'pfb_so_type' LIMIT 1
        """)
        rent_filter = "AND so.pfb_so_type = 'rent'" if self._cr.fetchone() else ""

        # วันเริ่ม/สิ้นสุดเช่าบน picking มาจากโมดูล rental_stock_picking
        # (start_x_date / end_x_date) -> ถ้าไม่ได้ติดตั้ง ให้ใช้ NULL แทน
        def _picking_col(col, cast):
            self._cr.execute("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'stock_picking' AND column_name = %s LIMIT 1
            """, (col,))
            return "sp.%s" % col if self._cr.fetchone() else "NULL::%s" % cast

        start_col = _picking_col('start_x_date', 'date')
        end_col = _picking_col('end_x_date', 'date')

        self._cr.execute("""
            CREATE OR REPLACE VIEW {table} AS (
                WITH rental_prod AS (
                    -- สินค้าเช่า: ชื่อสินค้ามี '(R)' ต่อท้าย (ตามคอนเวนชันของ NPD)
                    -- Odoo 18: product_template.name เป็น translate=True (เก็บเป็น jsonb)
                    -- ต้อง cast ::text ก่อน ILIKE (ค้นทุกภาษาที่มีในค่า) มิฉะนั้น error jsonb ~~*
                    SELECT pp.id AS product_id
                      FROM product_product pp
                      JOIN product_template pt ON pt.id = pp.product_tmpl_id
                     WHERE pt.name::text ILIKE '%(R)%'
                ),
                returned AS (
                    -- จำนวนที่คืนแล้ว รวมกลับเข้าที่ move ตัดต้นทาง
                    SELECT rm.origin_returned_move_id AS move_id,
                           SUM(rm.product_qty)        AS returned_qty
                      FROM stock_move rm
                     WHERE rm.state = 'done'
                       AND rm.origin_returned_move_id IS NOT NULL
                     GROUP BY rm.origin_returned_move_id
                )
                SELECT sm.id                                       AS id,
                       sm.picking_id                               AS picking_id,
                       sp.sale_id                                  AS sale_id,
                       sp.partner_id                               AS partner_id,
                       sm.product_id                               AS product_id,
                       COALESCE(src.company_id, sp.company_id, so.company_id) AS company_id,
                       COALESCE(src.branch_id, sp.branch_id, so.branch_id)    AS branch_id,
                       COALESCE(sm.date, sp.date_done, sp.scheduled_date)     AS cut_date,
                       {start_col}                                 AS start_rent_date,
                       {end_col}                                   AS end_rent_date,
                       sm.product_qty                              AS qty_cut,
                       COALESCE(r.returned_qty, 0.0)               AS qty_returned,
                       GREATEST(sm.product_qty - COALESCE(r.returned_qty, 0.0), 0.0)
                                                                   AS qty_outstanding,
                       CASE
                           WHEN COALESCE(r.returned_qty, 0.0) <= 0
                               THEN 'not_returned'
                           WHEN COALESCE(r.returned_qty, 0.0) < sm.product_qty
                               THEN 'partial'
                           ELSE 'returned'
                       END                                         AS return_state
                  FROM stock_move sm
                  JOIN stock_picking sp       ON sp.id = sm.picking_id
                  JOIN stock_picking_type spt ON spt.id = sp.picking_type_id
                  LEFT JOIN stock_location src ON src.id = sm.location_id
                  LEFT JOIN sale_order so       ON so.id = sp.sale_id
                  LEFT JOIN returned r          ON r.move_id = sm.id
                 WHERE sm.state = 'done'
                   AND spt.code = 'outgoing'
                   AND sm.origin_returned_move_id IS NULL
                   AND sm.product_qty > 0
                   {rent_filter}
                   AND sm.product_id IN (SELECT product_id FROM rental_prod)
                   AND COALESCE(src.branch_id, sp.branch_id, so.branch_id) IS NOT NULL
            )
        """.format(table=self._table, rent_filter=rent_filter,
                   start_col=start_col, end_col=end_col))
