# -*- coding: utf-8 -*-
from odoo import api, models, fields, tools

# ชื่อคอลัมน์ผูกกับค่า REPAIR_SLA_MINUTES ของ npd_scrap_buttons ที่เดียว
# (แก้เวลา SLA ที่ไฟล์ npd_scrap_buttons/models/stock_scrap.py)
from odoo.addons.npd_scrap_buttons.models.stock_scrap import (
    repair_sla_label, SOLD_AS_IS_KEYWORD)


def _format_clock(total_seconds):
    """นาฬิกาแบบ HH:MM:SS (เกิน 1 วันขึ้นเป็น 'N วัน HH:MM:SS') — ตรงกับฝั่ง JS"""
    total_seconds = max(0, int(total_seconds))
    days = total_seconds // 86400
    clock = '%02d:%02d:%02d' % (
        (total_seconds % 86400) // 3600,
        (total_seconds % 3600) // 60,
        total_seconds % 60,
    )
    return '%d วัน %s' % (days, clock) if days else clock


class RentalStockOverview(models.Model):
    """รายงานภาพรวมสต็อก เช่า แยกบริษัท/สาขา (เรียลไทม์ผ่าน SQL View)

    เป็น PostgreSQL View (_auto = False) จึงคำนวณ 'สด' จากตารางจริงทุกครั้งที่เปิด

    1 แถว = (สินค้า x สาขา x บริษัท)
      - company_id  : บริษัทเจ้าของคลัง (stock_location.company_id)
      - qty_on_hand : ปริมาณคงคลังในคลัง internal ของสาขานั้น (stock_quant.quantity)
      - qty_rented  : จำนวนที่ถูกเช่า = จำนวนที่ 'ตัดสต๊อกออกเสร็จสิ้น' ของบิลเช่า
                      ที่ยังไม่ถูกคืนครบ (ตัด - คืน)
      - qty_lost / qty_damaged  : จากใบ Scrap (เสร็จสิ้น) แยกตามคลังปลายทาง
      - qty_transferred / qty_transferred_out : ย้ายเข้า/ออก จาก stock.api.transfer

    หมายเหตุ Odoo 18:
      * เดิมแต่ละบริษัทเป็นคนละ DB → ไม่มีคอลัมน์บริษัท; เวอร์ชันนี้รวม DB เดียว
        จึงเพิ่ม company_id (จากคลัง) เข้า grouping ทุก CTE
      * stock.api.transfer เปลี่ยน schema (ไม่มี database_selection, line ใช้
        product_id/source_location_id แทน default_code/location_id) → ปรับ CTE ย้ายสต็อก
    """
    _name = 'dev.rental.stock.overview'
    _description = 'รายงานภาพรวมสต็อก เช่า'
    _auto = False
    _order = 'company_id, branch_id, product_id'
    _rec_name = 'product_id'

    company_id = fields.Many2one('res.company', string='บริษัท', readonly=True)
    product_id = fields.Many2one('product.product', string='สินค้า', readonly=True)
    product_code = fields.Char(
        string='รหัสสินค้า', related='product_id.default_code', readonly=True)
    product_name = fields.Char(
        string='สินค้า', related='product_id.name', readonly=True)
    branch_id = fields.Many2one('res.branch', string='สาขา', readonly=True)
    uom_name = fields.Char(
        string='หน่วย', related='product_id.uom_id.name', readonly=True)
    qty_on_hand = fields.Float(
        string='ปริมาณที่มีอยู่', readonly=True, digits='Product Unit of Measure')
    qty_rented = fields.Float(
        string='จำนวนที่ถูกเช่า', readonly=True, digits='Product Unit of Measure')
    qty_lost = fields.Float(
        string='สินค้าหาย', readonly=True, digits='Product Unit of Measure')
    qty_damaged = fields.Float(
        string='สินค้าชำรุด', readonly=True, digits='Product Unit of Measure')
    qty_pending_repair = fields.Float(
        string='สินค้ารอซ่อม %s' % repair_sla_label(), readonly=True,
        digits='Product Unit of Measure',
        help='ใบ Scrap ที่อยู่ในสถานะ "อยู่ระหว่างการซ่อม" '
             'นับ %s จากวันที่เริ่มซ่อม' % repair_sla_label())
    repair_doc_count = fields.Integer(
        string='ใบที่กำลังซ่อม', readonly=True,
        help='จำนวนใบ Scrap สถานะ "อยู่ระหว่างการซ่อม" ของสินค้า+สาขานี้\n'
             'ถ้ามากกว่า 1 ใบ เวลาที่แสดงคือใบที่ใกล้ครบกำหนดที่สุด '
             '(กดปุ่มดูรายใบได้)')
    repair_deadline = fields.Datetime(
        string='ครบกำหนดซ่อม', readonly=True,
        help='เวลาครบกำหนดซ่อมของใบที่ใกล้ครบกำหนดที่สุด\n'
             'ถ้าไม่มีใบค้างอยู่ จะแสดงผลของใบที่ซ่อมสำเร็จล่าสุด')
    repair_done_date = fields.Datetime(
        string='วันที่ซ่อมสำเร็จ', readonly=True,
        help='มีค่าเมื่อไม่มีใบค้างซ่อมแล้ว ใช้ตรึงผลลัพธ์ไม่ให้เวลาวิ่งต่อ')
    repair_sla_text = fields.Char(
        string='เวลา %s' % repair_sla_label(), compute='_compute_repair_sla_text',
        store=False,
        help='ข้อความ ณ เวลาที่โหลดหน้า (นับถอยหลัง / เกินกำหนด / ซ่อมสำเร็จ)\n'
             'widget npd_repair_countdown จะทำให้เดินทุกวินาทีต่อในเบราว์เซอร์')
    qty_sold_as_is = fields.Float(
        string='สินค้าขายตามสภาพ', readonly=True,
        digits='Product Unit of Measure',
        help='ของที่ซ่อมไม่ได้แล้ว ย้ายไปรอขายมือสอง = ยอดคงเหลือในคลัง "%s" ของสาขานั้น\n'
             'ขายออกไปแล้วตัวเลขจะลดลงเอง (นับจากสต็อกจริง ไม่ใช่ยอดสะสม)'
             % SOLD_AS_IS_KEYWORD)
    qty_transferred = fields.Float(
        string='ย้ายสต็อก (เข้าสาขา/บ.อื่น)', readonly=True, digits='Product Unit of Measure')
    qty_transferred_out = fields.Float(
        string='ย้ายสต็อก (ออกสาขา/บ.อื่น)', readonly=True, digits='Product Unit of Measure')
    qty_initial = fields.Float(
        string='จำนวนตั้งต้น', readonly=True, digits='Product Unit of Measure',
        help='ปริมาณที่มีอยู่ + จำนวนที่ถูกเช่า + สินค้าหาย + สินค้าชำรุด')

    @api.depends('repair_deadline', 'repair_done_date', 'repair_doc_count')
    def _compute_repair_sla_text(self):
        """ข้อความสถานะ SLA คำนวณฝั่งเซิร์ฟเวอร์ (ตรรกะเดียวกับ widget ฝั่ง JS)

        มีไว้ให้รายงานอ่านรู้เรื่องแม้ widget ยังไม่โหลด และติดไปตอน export Excel
        """
        now = fields.Datetime.now()
        for rec in self:
            deadline = rec.repair_deadline
            if not deadline:
                rec.repair_sla_text = ''
                continue
            done = rec.repair_done_date
            if done:
                late = (done - deadline).total_seconds()
                text = ('เกินกำหนด ' + _format_clock(late)) if late > 0 else 'ซ่อมสำเร็จ'
            else:
                left = (deadline - now).total_seconds()
                text = _format_clock(left) if left >= 0 else 'เกินกำหนด ' + _format_clock(-left)
            if rec.repair_doc_count > 1:
                text += ' (%d ใบ)' % rec.repair_doc_count
            rec.repair_sla_text = text

    def action_open_repair_scraps(self):
        """Drill-down: เปิดใบ Scrap ของสินค้า+สาขานี้ที่อยู่ใน workflow ซ่อม"""
        self.ensure_one()
        domain = [
            ('product_id', '=', self.product_id.id),
            ('state', 'in', ['pending_repair', 'under_repair', 'repaired']),
        ]
        if self.branch_id:
            domain.append(('location_id.branch_id', '=', self.branch_id.id))
        return {
            'type': 'ir.actions.act_window',
            'name': 'ใบแจ้งซ่อม: %s / %s' % (
                self.product_id.display_name, self.branch_id.name or '-'),
            'res_model': 'stock.scrap',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {'create': False},
        }

    def init(self):
        tools.drop_view_if_exists(self._cr, self._table)

        # กันกรณี DB ไม่ได้ติดตั้งโมดูล customs (ไม่มีคอลัมน์ pfb_so_type)
        # -> ถ้าไม่มี ให้รวมทุกใบส่งออก done (อาจปนสินค้าขายขาด) แทนที่จะพัง
        self._cr.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'sale_order' AND column_name = 'pfb_so_type' LIMIT 1
        """)
        rent_filter = "AND so.pfb_so_type = 'rent'" if self._cr.fetchone() else ""

        # กันกรณี DB ยังไม่ได้อัปเกรด npd_scrap_buttons (ยังไม่มีคอลัมน์ repair_deadline)
        # -> ใช้ CTE เปล่าแทน เพื่อให้ view ยังสร้างได้และคอลัมน์รอซ่อมเป็น 0
        self._cr.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'stock_scrap' AND column_name = 'repair_deadline' LIMIT 1
        """)
        if self._cr.fetchone():
            repair_cte = """
                repair AS (
                    -- ใบ Scrap ที่เข้า workflow ซ่อม (npd_scrap_buttons)
                    -- สาขา = คลังต้นทาง location_id.branch_id (นิยามเดียวกับ CTE scrap)
                    --   qty_under_repair  : สถานะ 'อยู่ระหว่างการซ่อม' (นาฬิกา SLA กำลังเดิน)
                    --   open_deadline     : ครบกำหนดของใบที่ใกล้ครบที่สุดที่ยังซ่อมไม่เสร็จ
                    --   done_deadline/date: ผลของใบที่ซ่อมสำเร็จล่าสุด (ใช้เมื่อไม่มีใบค้าง)
                    SELECT s.product_id  AS product_id,
                           sl.branch_id  AS branch_id,
                           sl.company_id AS company_id,
                           SUM(s.scrap_qty) FILTER (WHERE s.state = 'under_repair')
                               AS qty_under_repair,
                           MIN(s.repair_deadline) FILTER (WHERE s.state = 'under_repair')
                               AS open_deadline,
                           COUNT(*) FILTER (WHERE s.state = 'under_repair')
                               AS open_count,
                           (ARRAY_AGG(s.repair_deadline ORDER BY s.repair_end_date DESC NULLS LAST)
                               FILTER (WHERE s.state = 'repaired')
                           )[1] AS done_deadline,
                           MAX(s.repair_end_date) FILTER (WHERE s.state = 'repaired')
                               AS done_date
                      FROM stock_scrap s
                      JOIN stock_location sl ON sl.id = s.location_id
                     WHERE s.state IN ('pending_repair', 'under_repair', 'repaired')
                       AND sl.branch_id IS NOT NULL
                       AND s.product_id IN (SELECT product_id FROM rental_prod)
                     GROUP BY s.product_id, sl.branch_id, sl.company_id
                ),
                sold_as_is AS (
                    -- สินค้าขายตามสภาพ = ของที่ยังค้างอยู่ในคลัง 'ขายตามสภาพ' รายสาขา
                    -- (ยอดคงเหลือ ไม่ใช่ยอดสะสม -> ขายออกไปแล้วตัวเลขลดลงเอง)
                    -- อ้างสาขาจาก scrap_branch_id ไม่ใช่ branch_id เพราะคลังกลุ่มนี้
                    -- ต้องไม่ผูก branch_id ไม่งั้นจะไปแย่งผลการค้นหาคลังต้นทางของโมดูลอื่น
                    SELECT sq.product_id      AS product_id,
                           sl.scrap_branch_id AS branch_id,
                           sl.company_id      AS company_id,
                           SUM(sq.quantity)   AS qty_sold_as_is
                      FROM stock_quant sq
                      JOIN stock_location sl ON sl.id = sq.location_id
                     WHERE sl.usage = 'internal'
                       AND sl.scrap_branch_id IS NOT NULL
                       AND sl.complete_name ILIKE '%{sold_kw}%'
                       AND sq.product_id IN (SELECT product_id FROM rental_prod)
                     GROUP BY sq.product_id, sl.scrap_branch_id, sl.company_id
                ),
            """.replace('{sold_kw}', SOLD_AS_IS_KEYWORD)
        else:
            repair_cte = """
                repair AS (
                    SELECT NULL::integer   AS product_id,
                           NULL::integer   AS branch_id,
                           NULL::integer   AS company_id,
                           0.0::numeric    AS qty_under_repair,
                           NULL::timestamp AS open_deadline,
                           0::bigint       AS open_count,
                           NULL::timestamp AS done_deadline,
                           NULL::timestamp AS done_date
                     WHERE FALSE
                ),
                sold_as_is AS (
                    SELECT NULL::integer AS product_id,
                           NULL::integer AS branch_id,
                           NULL::integer AS company_id,
                           0.0::numeric  AS qty_sold_as_is
                     WHERE FALSE
                ),
            """

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
                onhand AS (
                    SELECT sq.product_id            AS product_id,
                           sl.branch_id             AS branch_id,
                           sl.company_id            AS company_id,
                           SUM(sq.quantity)         AS qty_on_hand
                      FROM stock_quant sq
                      JOIN stock_location sl ON sl.id = sq.location_id
                     WHERE sl.usage = 'internal'
                       AND sl.branch_id IS NOT NULL
                       AND sq.product_id IN (SELECT product_id FROM rental_prod)
                     GROUP BY sq.product_id, sl.branch_id, sl.company_id
                ),
                cut AS (
                    SELECT sm.id           AS move_id,
                           sm.product_id   AS product_id,
                           COALESCE(src.branch_id, sp.branch_id, so.branch_id)   AS branch_id,
                           COALESCE(src.company_id, sp.company_id, so.company_id) AS company_id,
                           sm.product_qty  AS delivered
                      FROM stock_move sm
                      JOIN stock_picking sp       ON sp.id = sm.picking_id
                      JOIN stock_picking_type spt ON spt.id = sp.picking_type_id
                      LEFT JOIN stock_location src ON src.id = sm.location_id
                      LEFT JOIN sale_order so       ON so.id = sp.sale_id
                     WHERE sm.state = 'done'
                       AND spt.code = 'outgoing'
                       AND sm.origin_returned_move_id IS NULL
                       AND sm.product_qty > 0
                       {rent_filter}
                       AND sm.product_id IN (SELECT product_id FROM rental_prod)
                       AND COALESCE(src.branch_id, sp.branch_id, so.branch_id) IS NOT NULL
                ),
                returned AS (
                    SELECT rm.origin_returned_move_id AS move_id,
                           SUM(rm.product_qty)        AS returned_qty
                      FROM stock_move rm
                     WHERE rm.state = 'done'
                       AND rm.origin_returned_move_id IS NOT NULL
                     GROUP BY rm.origin_returned_move_id
                ),
                rented AS (
                    SELECT c.product_id AS product_id,
                           c.branch_id  AS branch_id,
                           c.company_id AS company_id,
                           SUM(GREATEST(c.delivered - COALESCE(r.returned_qty, 0), 0)) AS qty_rented
                      FROM cut c
                      LEFT JOIN returned r ON r.move_id = c.move_id
                     GROUP BY c.product_id, c.branch_id, c.company_id
                ),
                scrap AS (
                    -- สินค้าหาย / สินค้าชำรุด จากใบ Scrap (เฉพาะสถานะเสร็จสิ้น)
                    -- แยกประเภทจากคลังปลายทาง (scrap_location_id): 'หาย' vs 'ชำรุด'
                    -- 'สินค้าชำรุด' เริ่มนับตั้งแต่ 7/7/2026 (เวลาไทย) เป็นต้นไปเท่านั้น
                    SELECT s.product_id AS product_id,
                           sl.branch_id AS branch_id,
                           sl.company_id AS company_id,
                           SUM(s.scrap_qty) FILTER (WHERE dl.name ILIKE '%หาย%')   AS qty_lost,
                           SUM(s.scrap_qty) FILTER (
                               WHERE dl.name ILIKE '%ชำรุด%'
                                 AND (s.date_done AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Bangkok')::date
                                     >= DATE '2026-07-07'
                           ) AS qty_damaged
                      FROM stock_scrap s
                      JOIN stock_location sl ON sl.id = s.location_id
                      JOIN stock_location dl ON dl.id = s.scrap_location_id
                     WHERE s.state = 'done'
                       AND sl.branch_id IS NOT NULL
                       AND s.product_id IN (SELECT product_id FROM rental_prod)
                       AND (dl.name ILIKE '%หาย%' OR dl.name ILIKE '%ชำรุด%')
                     GROUP BY s.product_id, sl.branch_id, sl.company_id
                ),
                {repair_cte}
                transfer AS (
                    -- ย้ายเข้า: stock.api.transfer (เฉพาะรายการที่สำเร็จ) นับตามคลังปลายทาง
                    -- Odoo 18: join บน product_id ตรง ๆ (line.product_id) และใช้ destination_location_id
                    SELECT tl.product_id AS product_id,
                           dl.branch_id  AS branch_id,
                           dl.company_id AS company_id,
                           SUM(tl.request_qty) AS qty_transferred
                      FROM stock_api_transfer_line tl
                      JOIN stock_location dl ON dl.id = tl.destination_location_id
                      JOIN rental_prod rp ON rp.product_id = tl.product_id
                     WHERE tl.status = 'สำเร็จ'
                       AND dl.branch_id IS NOT NULL
                     GROUP BY tl.product_id, dl.branch_id, dl.company_id
                ),
                transfer_out AS (
                    -- ย้ายออก: นับตามคลังต้นทาง (source_location_id)
                    -- Odoo 18: DB เดียวหลายบริษัท จึงไม่ต้องกรอง database_selection อีกต่อไป
                    SELECT tl.product_id AS product_id,
                           sl.branch_id  AS branch_id,
                           sl.company_id AS company_id,
                           SUM(tl.request_qty) AS qty_transferred_out
                      FROM stock_api_transfer_line tl
                      JOIN stock_location sl ON sl.id = tl.source_location_id
                      JOIN rental_prod rp ON rp.product_id = tl.product_id
                     WHERE tl.status = 'สำเร็จ'
                       AND sl.branch_id IS NOT NULL
                     GROUP BY tl.product_id, sl.branch_id, sl.company_id
                ),
                keys AS (
                    SELECT product_id, branch_id, company_id FROM onhand
                    UNION SELECT product_id, branch_id, company_id FROM rented
                    UNION SELECT product_id, branch_id, company_id FROM scrap
                    UNION SELECT product_id, branch_id, company_id FROM transfer
                    UNION SELECT product_id, branch_id, company_id FROM transfer_out
                    UNION SELECT product_id, branch_id, company_id FROM repair
                    UNION SELECT product_id, branch_id, company_id FROM sold_as_is
                )
                SELECT row_number() OVER ()                  AS id,
                       k.product_id                          AS product_id,
                       k.branch_id                           AS branch_id,
                       k.company_id                          AS company_id,
                       (COALESCE(o.qty_on_hand, 0.0)
                        + COALESCE(rt.qty_rented, 0.0)
                        + COALESCE(sc.qty_lost, 0.0)
                        + COALESCE(sc.qty_damaged, 0.0)
                        + COALESCE(rp.qty_under_repair, 0.0)
                        + COALESCE(sa.qty_sold_as_is, 0.0))  AS qty_initial,
                       COALESCE(o.qty_on_hand, 0.0)          AS qty_on_hand,
                       COALESCE(rt.qty_rented, 0.0)          AS qty_rented,
                       COALESCE(sc.qty_lost, 0.0)            AS qty_lost,
                       COALESCE(sc.qty_damaged, 0.0)         AS qty_damaged,
                       COALESCE(rp.qty_under_repair, 0.0)    AS qty_pending_repair,
                       COALESCE(rp.open_count, 0)::integer   AS repair_doc_count,
                       COALESCE(rp.open_deadline, rp.done_deadline) AS repair_deadline,
                       CASE WHEN rp.open_count > 0 THEN NULL ELSE rp.done_date END
                                                             AS repair_done_date,
                       COALESCE(sa.qty_sold_as_is, 0.0)      AS qty_sold_as_is,
                       COALESCE(tr.qty_transferred, 0.0)     AS qty_transferred,
                       COALESCE(tro.qty_transferred_out, 0.0) AS qty_transferred_out
                  FROM keys k
                  LEFT JOIN onhand o        ON o.product_id = k.product_id AND o.branch_id = k.branch_id
                                           AND COALESCE(o.company_id, 0) = COALESCE(k.company_id, 0)
                  LEFT JOIN rented rt       ON rt.product_id = k.product_id AND rt.branch_id = k.branch_id
                                           AND COALESCE(rt.company_id, 0) = COALESCE(k.company_id, 0)
                  LEFT JOIN repair rp       ON rp.product_id = k.product_id AND rp.branch_id = k.branch_id
                                           AND COALESCE(rp.company_id, 0) = COALESCE(k.company_id, 0)
                  LEFT JOIN sold_as_is sa   ON sa.product_id = k.product_id AND sa.branch_id = k.branch_id
                                           AND COALESCE(sa.company_id, 0) = COALESCE(k.company_id, 0)
                  LEFT JOIN scrap sc        ON sc.product_id = k.product_id AND sc.branch_id = k.branch_id
                                           AND COALESCE(sc.company_id, 0) = COALESCE(k.company_id, 0)
                  LEFT JOIN transfer tr     ON tr.product_id = k.product_id AND tr.branch_id = k.branch_id
                                           AND COALESCE(tr.company_id, 0) = COALESCE(k.company_id, 0)
                  LEFT JOIN transfer_out tro ON tro.product_id = k.product_id AND tro.branch_id = k.branch_id
                                           AND COALESCE(tro.company_id, 0) = COALESCE(k.company_id, 0)
            )
        """.format(repair_cte=repair_cte, table=self._table, rent_filter=rent_filter))
