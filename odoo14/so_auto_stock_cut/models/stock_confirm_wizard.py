# -*- coding: utf-8 -*-
from odoo import models, api, fields
from odoo.exceptions import UserError
import pymysql
import logging

_logger = logging.getLogger(__name__)
_LOGGER = logging.getLogger(__name__)
def _dbg(msg):
    # ใช้ทั้ง logger และ print เป็น fallback
    try:
        _LOGGER.info(msg)
    except Exception:
        pass
    try:
        print(msg)
    except Exception:
        pass

class StockCutConfirmWizard(models.TransientModel):
    _name = 'stock.cut.confirm.wizard'
    _description = 'Confirm Stock Cut Wizard'

    order_id = fields.Many2one('sale.order', string='Sale Order')
    confirm_line_ids = fields.One2many('stock.cut.confirm.line', 'wizard_id', string='Stock Moves to Confirm')

    greenhome_line_ids = fields.One2many('stock.cut.greenhome.line', 'wizard_id', string='ข้อมูลบ้านเขียว')

    can_return_greenhome = fields.Boolean(string='Allow Greenhome Return', default=False)
    # ----------------------------
    # Helpers
    # ----------------------------

    # --- NEW: helpers for MySQL update ---------------------------------

    def _mysql_column_exists(self, cur, table_name, column_name):
        cur.execute("""
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND COLUMN_NAME = %s
            LIMIT 1
        """, (table_name, column_name))
        return cur.fetchone() is not None

    def _resolve_branch_id_mysql(self, cur, branch_name, fallback_id=None):
        """
        คืนค่า branch_id (string) ที่ MySQL ใช้งานจริง
        1) ถ้ามี fallback_id (จาก mapping) จะลองใช้ก่อน
        2) ถ้าไม่ชัวร์/ไม่พบ จะค้นจาก master_branch โดยเทียบชื่อ
        """
        if fallback_id:
            return str(fallback_id)

        if not branch_name:
            return None

        # ค้นจากชื่อสาขาให้เลย (กันสะกดคลาดเคลื่อนนิดหน่อย)
        cur.execute("""
            SELECT branch_id
              FROM master_branch
             WHERE branch_name = %s
               AND cancel = 'N'
             LIMIT 1
        """, (branch_name,))
        row = cur.fetchone()
        return str(row['branch_id']) if row else None

    def _update_mysql_after_cut(self, branch_id_for_mysql, items, branch_name=None):
        """
        อัปเดต master_stockactual ให้ใช้ฟิลด์:
          - sa_stockin  (คงเหลือ)  = sa_stockin  - qty
          - sa_stockout (ถูกเช่า)   = sa_stockout + qty
        ตรวจก่อน-หลัง และฟ้อง pdn ที่ไม่พบแถวให้ชัด
        """
        if not items:
            return

        conn = None
        cur = None
        try:
            conn = pymysql.connect(
                host='150.95.26.61',
                user='greenhome',
                password='NPD@db789',
                database='npd_db',
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=False,
                connect_timeout=8, read_timeout=8, write_timeout=8,
            )
            cur = conn.cursor()

            # ✅ คอลัมน์ที่ต้องมี
            has_stockin = self._mysql_column_exists(cur, 'master_stockactual', 'sa_stockin')
            has_stockout = self._mysql_column_exists(cur, 'master_stockactual', 'sa_stockout')
            if not has_stockin and not has_stockout:
                raise UserError("❌ MySQL: ไม่พบ sa_stockin/sa_stockout ใน master_stockactual")

            # ✅ ยืนยัน branch_id จากฐาน (กัน mapping เพี้ยน)
            resolved_branch_id = self._resolve_branch_id_mysql(cur, branch_name, branch_id_for_mysql)
            if not resolved_branch_id:
                raise UserError(f"❌ MySQL: หา branch_id ของสาขา '{branch_name or ''}' ไม่เจอ")

            # 🔎 รวบรวม pdn ทั้งหมดไว้เช็คก่อน
            pdn_list = [(it.get('pdn_id') or '').strip() for it in items if (it.get('pdn_id') or '').strip()]
            if not pdn_list:
                raise UserError("❌ ไม่มี pdn_id ใด ๆ ให้ปรับปรุง")

            # ---- PRECHECK: มีแถวไหนบ้างที่แมตช์จริง ----
            in_clause = ",".join(["%s"] * len(pdn_list))
            cur.execute(f"""
                SELECT sa_pdnid
                  FROM master_stockactual
                 WHERE sa_cancel = 'N'
                   AND branchid = %s
                   AND sa_pdnid IN ({in_clause})
            """, (resolved_branch_id, *pdn_list))
            found = {r['sa_pdnid'] for r in cur.fetchall()}
            not_found = [p for p in pdn_list if p not in found]
            if not_found:
                raise UserError("❌ MySQL: ไม่พบแถวใน master_stockactual สำหรับ pdn: " + ", ".join(not_found))

            # ---- LOG ค่าก่อนอัปเดต (เพื่อเทียบหลังทำเสร็จ) ----
            cur.execute(f"""
                SELECT sa_pdnid, COALESCE(sa_stockin,0) AS stockin, COALESCE(sa_stockout,0) AS stockout
                  FROM master_stockactual
                 WHERE sa_cancel = 'N'
                   AND branchid = %s
                   AND sa_pdnid IN ({in_clause})
                 ORDER BY sa_pdnid
            """, (resolved_branch_id, *pdn_list))
            before_map = {r['sa_pdnid']: (r['stockin'], r['stockout']) for r in cur.fetchall()}

            # ---- อัปเดตจริง (ตัด LIMIT 1 ออก) ----
            sql_dec_stockin = """
                UPDATE master_stockactual
                   SET sa_stockin = GREATEST(COALESCE(sa_stockin, 0) - %s, 0)
                 WHERE sa_cancel = 'N'
                   AND branchid = %s
                   AND sa_pdnid = %s
            """
            sql_inc_stockout = """
                UPDATE master_stockactual
                   SET sa_stockout = COALESCE(sa_stockout, 0) + %s
                 WHERE sa_cancel = 'N'
                   AND branchid = %s
                   AND sa_pdnid = %s
            """

            total_rows_affected = 0
            for it in items:
                pdn_id = (it.get('pdn_id') or '').strip()
                qty = float(it.get('qty') or 0)
                if not pdn_id or qty <= 0:
                    continue

                if has_stockin:
                    cur.execute(sql_dec_stockin, (qty, resolved_branch_id, pdn_id))
                    total_rows_affected += cur.rowcount
                if has_stockout:
                    cur.execute(sql_inc_stockout, (qty, resolved_branch_id, pdn_id))
                    total_rows_affected += cur.rowcount

            if total_rows_affected == 0:
                raise UserError("❌ MySQL: ไม่มีแถวใดถูกอัปเดต (ตรวจ branch/pdn อีกครั้ง)")

            conn.commit()

            # ---- VERIFY หลังอัปเดต ----
            cur.execute(f"""
                SELECT sa_pdnid, COALESCE(sa_stockin,0) AS stockin, COALESCE(sa_stockout,0) AS stockout
                  FROM master_stockactual
                 WHERE sa_cancel = 'N'
                   AND branchid = %s
                   AND sa_pdnid IN ({in_clause})
                 ORDER BY sa_pdnid
            """, (resolved_branch_id, *pdn_list))
            after_map = {r['sa_pdnid']: (r['stockin'], r['stockout']) for r in cur.fetchall()}

            # พิมพ์ log ชัด ๆ (ดูได้ใน Odoo log)
            for pdn_id in pdn_list:
                b_in, b_out = before_map.get(pdn_id, (None, None))
                a_in, a_out = after_map.get(pdn_id, (None, None))
                _msg = f"🧾 MySQL VERIFY pdn={pdn_id} | stockin: {b_in} → {a_in} | stockout: {b_out} → {a_out} | branch={resolved_branch_id}"
                _logger = getattr(self.env, 'logger', None)
                # ถ้าไม่มี logger ใน env ให้ใช้ print
                print(_msg) if _logger is None else _logger.info(_msg)

        except Exception as e:
            try:
                if conn: conn.rollback()
            except Exception:
                pass
            raise UserError(f"❌ อัปเดต MySQL ล้มเหลว: {str(e)}")
        finally:
            try:
                if cur: cur.close()
            except Exception:
                pass
            try:
                if conn: conn.close()
            except Exception:
                pass

    def _apply_return_for_picking(self, branch_id_for_mysql, items, picking_name):
        """
        คืนสินค้า:
          - ลด rentorder_detail.rentd_amount ตามจำนวนที่คืน (ไม่ติดลบ)
          - ถ้าทุกรายการในใบ = 0 ให้ตั้ง rentorder_head.renth_return='Y' (เพื่อให้ query รายงานตัดออก)
        """
        if not items:
            return
        conn = None;
        cur = None
        try:
            conn = pymysql.connect(
                host='150.95.26.61', user='greenhome', password='NPD@db789',
                database='npd_db', charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor, autocommit=False,
                connect_timeout=8, read_timeout=8, write_timeout=8,
            )
            cur = conn.cursor()

            # ensure head exists
            cur.execute("SELECT renth_id FROM rentorder_head WHERE renth_id=%s LIMIT 1", (picking_name,))
            if not cur.fetchone():
                # ถ้าไม่เคยมีใบ OUT/ใบอ้างอิง ให้สร้างหัวไว้ก่อน (ยังคง return='N')
                cur.execute("""
                    INSERT INTO rentorder_head (renth_id, branchid, renth_return, renth_cancel)
                    VALUES (%s, %s, 'N', 'N')
                """, (picking_name, branch_id_for_mysql))

            # ลดยอดใน detail รายตัว
            for it in items:
                pdn_id = (it.get('pdn_id') or '').strip()
                qty = float(it.get('qty') or 0)
                if not pdn_id or qty <= 0:
                    continue

                # ดึงยอดเดิม
                cur.execute("""
                    SELECT rentd_amount
                      FROM rentorder_detail
                     WHERE rentd_id=%s AND rentd_proid=%s
                     LIMIT 1
                """, (picking_name, pdn_id))
                row = cur.fetchone()
                if not row:
                    # ไม่มีบรรทัดเดิม ก็ข้าม (ถือว่าคืนของที่ระบบไม่เคยปล่อย)
                    continue

                new_amt = max(float(row['rentd_amount'] or 0) - qty, 0.0)
                cur.execute("""
                    UPDATE rentorder_detail
                       SET rentd_amount=%s
                     WHERE rentd_id=%s AND rentd_proid=%s
                """, (new_amt, picking_name, pdn_id))

            # ถ้าทุกรายการ = 0 ให้ปิดใบเป็นคืนแล้ว (รายงานจะไม่เอาไปรวม rented)
            cur.execute("""
                SELECT SUM(COALESCE(rentd_amount,0)) AS sum_amt
                  FROM rentorder_detail
                 WHERE rentd_id=%s
            """, (picking_name,))
            s = cur.fetchone()
            all_zero = not s or float(s['sum_amt'] or 0) <= 0
            if all_zero:
                cur.execute("""
                    UPDATE rentorder_head
                       SET renth_return='Y'
                     WHERE renth_id=%s
                """, (picking_name,))

            conn.commit()

        except Exception as e:
            try:
                if conn: conn.rollback()
            except Exception:
                pass
            raise UserError(f"❌ อัปเดตคืนสินค้า (rentorder_*) ล้มเหลว: {str(e)}")
        finally:
            try:
                if cur: cur.close()
            except Exception:
                pass
            try:
                if conn: conn.close()
            except Exception:
                pass

    def _update_mysql_after_return(self, branch_id_for_mysql, items, branch_name=None):
        """
        คืนสินค้า:
          - sa_stockin  = sa_stockin + qty
          - sa_stockout = GREATEST(sa_stockout - qty, 0)
        """
        if not items:
            return

        conn = None
        cur = None
        try:
            conn = pymysql.connect(
                host='150.95.26.61', user='greenhome', password='NPD@db789',
                database='npd_db', charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor, autocommit=False,
                connect_timeout=8, read_timeout=8, write_timeout=8,
            )
            cur = conn.cursor()

            resolved_branch_id = self._resolve_branch_id_mysql(cur, branch_name, branch_id_for_mysql)
            if not resolved_branch_id:
                raise UserError(f"❌ MySQL: หา branch_id ไม่เจอสำหรับ '{branch_name}'")

            _logger.info(f"🔑 Resolved Branch ID: {resolved_branch_id}")

            # ตรวจสอบว่ามีแถวใน master_stockactual หรือไม่
            pdn_list = [it['pdn_id'] for it in items]
            in_clause = ','.join(['%s'] * len(pdn_list))

            cur.execute(f"""
                SELECT sa_pdnid, 
                       COALESCE(sa_stockin,0) AS stockin_before,
                       COALESCE(sa_stockout,0) AS stockout_before
                  FROM master_stockactual
                 WHERE sa_cancel='N' 
                   AND branchid=%s 
                   AND sa_pdnid IN ({in_clause})
            """, (resolved_branch_id, *pdn_list))

            before_data = {r['sa_pdnid']: r for r in cur.fetchall()}

            if not before_data:
                raise UserError(
                    f"❌ MySQL: ไม่พบข้อมูลสต็อกใน master_stockactual\n"
                    f"Branch ID: {resolved_branch_id}\n"
                    f"PDN IDs: {', '.join(pdn_list)}"
                )

            _logger.info(f"📊 พบข้อมูลสต็อกเดิม {len(before_data)} รายการ")

            # อัปเดตจริง
            sql_inc_stockin = """
                UPDATE master_stockactual
                   SET sa_stockin = COALESCE(sa_stockin,0) + %s
                 WHERE sa_cancel='N' AND branchid=%s AND sa_pdnid=%s
            """
            sql_dec_stockout = """
                UPDATE master_stockactual
                   SET sa_stockout = GREATEST(COALESCE(sa_stockout,0) - %s, 0)
                 WHERE sa_cancel='N' AND branchid=%s AND sa_pdnid=%s
            """

            affected = 0
            for it in items:
                pdn_id = (it.get('pdn_id') or '').strip()
                qty = float(it.get('qty') or 0)
                if not pdn_id or qty <= 0:
                    continue

                cur.execute(sql_inc_stockin, (qty, resolved_branch_id, pdn_id))
                affected += cur.rowcount

                cur.execute(sql_dec_stockout, (qty, resolved_branch_id, pdn_id))
                affected += cur.rowcount

            if affected == 0:
                raise UserError("❌ MySQL: ไม่มีแถวถูกอัปเดต — ตรวจ branch/pdn")

            conn.commit()

            # ตรวจสอบหลัง UPDATE
            cur.execute(f"""
                SELECT sa_pdnid,
                       COALESCE(sa_stockin,0) AS stockin_after,
                       COALESCE(sa_stockout,0) AS stockout_after
                  FROM master_stockactual
                 WHERE sa_cancel='N' 
                   AND branchid=%s 
                   AND sa_pdnid IN ({in_clause})
            """, (resolved_branch_id, *pdn_list))

            after_data = {r['sa_pdnid']: r for r in cur.fetchall()}

            # แสดงการเปลี่ยนแปลง
            for pdn_id in pdn_list:
                before = before_data.get(pdn_id, {})
                after = after_data.get(pdn_id, {})

                _logger.info(f"""
      📦 {pdn_id}:
         stockin:  {before.get('stockin_before', 0)} → {after.get('stockin_after', 0)}
         stockout: {before.get('stockout_before', 0)} → {after.get('stockout_after', 0)}
                """)

        except Exception as e:
            try:
                if conn: conn.rollback()
            except Exception:
                pass
            raise UserError(f"❌ อัปเดตสต็อกคืนของ ล้มเหลว: {str(e)}")
        finally:
            try:
                if cur: cur.close()
            except Exception:
                pass
            try:
                if conn: conn.close()
            except Exception:
                pass

    def _branch_mapping(self):
        return {
            'โคราช-บายพาส': '02', 'อุดรธานี': '04', 'ขอนแก่น-โลตัส': '05', 'ชะอำ': '06',
            'ศาลายา': '07', 'ภูเก็ต': '08', 'อุบลราชธานี': '09', 'สุรินทร์': '12',
            'มหาสารคาม': '13', 'พัทยา': '15', 'อยุธยา': '16', 'ปลวกแดง': '17',
            'พระราม2': '19', 'บ้านฉาง': '20', 'ปทุมธานี': '21', 'บางละมุง': '22',
            'พิษณุโลก': '23', 'นครสวรรค์': '24', 'เชียงใหม่': '25', 'ทุ่งครุ': '26',
            'สุวินทวงศ์': '27', 'ลาดกระบัง': '28', 'คลองหลวง': '29'
        }

    def _upsert_rented_for_picking(self, branch_id_for_mysql, items, picking_name):
        """
        ทำให้รายงานเห็น 'สินค้าที่ถูกเช่า' ทันที:
          - ensure head: rentorder_head(renth_id=picking) พร้อมสถานะที่รายงานอ่านได้
          - set detail: rentorder_detail(rentd_id=picking, rentd_proid) = ปริมาณล่าสุด (ไม่บวกทับ)
        """
        if not items:
            return

        conn = None
        cur = None
        try:
            conn = pymysql.connect(
                host='150.95.26.61',
                user='greenhome',
                password='NPD@db789',
                database='npd_db',
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=False,
                connect_timeout=8, read_timeout=8, write_timeout=8,
            )
            cur = conn.cursor()

            # 1) ensure rentorder_head
            cur.execute("""
                SELECT renth_id
                  FROM rentorder_head
                 WHERE renth_id = %s
                 LIMIT 1
            """, (picking_name,))
            row = cur.fetchone()
            if not row:
                # ไม่ใส่ renth_date (ตารางคุณไม่มีคอลัมน์นี้)
                cur.execute("""
                    INSERT INTO rentorder_head (renth_id, branchid, renth_return, renth_cancel)
                    VALUES (%s, %s, 'N', 'N')
                """, (picking_name, branch_id_for_mysql))
            else:
                cur.execute("""
                    UPDATE rentorder_head
                       SET branchid=%s, renth_return='N', renth_cancel='N'
                     WHERE renth_id=%s
                """, (branch_id_for_mysql, picking_name))

            # 2) set ปริมาณล่าสุดแบบ idempotent ต่อสินค้าในใบนี้ (ไม่สะสมซ้ำ)
            for it in items:
                pdn_id = (it.get('pdn_id') or '').strip()
                qty = float(it.get('qty') or 0)
                if not pdn_id:
                    continue

                cur.execute("""
                    SELECT rentd_id, rentd_proid
                      FROM rentorder_detail
                     WHERE rentd_id = %s AND rentd_proid = %s
                     LIMIT 1
                """, (picking_name, pdn_id))
                drow = cur.fetchone()

                if not drow:
                    cur.execute("""
                        INSERT INTO rentorder_detail (rentd_id, rentd_proid, rentd_amount, rentd_amt_return)
                        VALUES (%s, %s, %s, 0)
                    """, (picking_name, pdn_id, qty))
                else:
                    # ตั้งเป็นค่าล่าสุด (ไม่บวกซ้ำ)
                    cur.execute("""
                        UPDATE rentorder_detail
                           SET rentd_amount = %s
                         WHERE rentd_id = %s AND rentd_proid = %s
                    """, (qty, picking_name, pdn_id))

            conn.commit()

        except Exception as e:
            try:
                if conn: conn.rollback()
            except Exception:
                pass
            raise UserError(f"❌ อัปเดตสินค้าที่ถูกเช่า (rentorder_*) ล้มเหลว: {str(e)}")
        finally:
            try:
                if cur: cur.close()
            except Exception:
                pass
            try:
                if conn: conn.close()
            except Exception:
                pass

    def return_greenhome_only(self):
        """
        ปุ่มสำหรับคืนสินค้าบ้านเขียวโดยตรง
        จะทำการ sync MySQL เท่านั้น โดยไม่สร้าง picking ใหม่
        """
        self.ensure_one()

        if self.order_id:
            self.order_id.write({'return_greenhome_state': 'processing'})

        # ตรวจสอบสิทธิ์ผู้ใช้ (คงไว้)
        if not self.env.user.allow_greenhome_return:
            # ❌ ล้มเหลว: ตีธง error ก่อนโยนข้อความ
            if self.order_id:
                self.order_id.write({'return_greenhome_state': 'error'})
            raise UserError("❌ คุณไม่มีสิทธิ์ใช้งานฟังก์ชันคืนสินค้าบ้านเขียว\nกรุณาติดต่อผู้ดูแลระบบ")

        # ตรวจสอบว่ามี picking ที่ต้องการคืนหรือไม่ (ใช้ใบจัดส่งขาออกล่าสุด)
        pickings = self.order_id.picking_ids.filtered(
            lambda p: p.state == 'done' and p.picking_type_id.code == 'outgoing'
        ).sorted('id', reverse=True)

        if not pickings:
            if self.order_id:
                self.order_id.write({'return_greenhome_state': 'error'})
            raise UserError("❌ ไม่พบใบจัดส่งที่สำเร็จแล้วสำหรับคำสั่งขายนี้")

        # ใช้ picking ขาออกล่าสุดเป็นฐานข้อมูลการคืน
        picking = pickings[0]

        # ตรวจสอบ bk_reference_code (คงไว้)
        missing_bk_products = []
        for move in picking.move_ids:
            # เราใช้ move.quantity เพราะเราสมมติว่าต้องการคืนตามจำนวนที่เคยปล่อยออกไป
            if move.quantity > 0 and move.product_id:
                if not move.product_id.bk_reference_code:
                    missing_bk_products.append(move.product_id.display_name)

        if missing_bk_products:
            if self.order_id:
                self.order_id.write({'return_greenhome_state': 'error'})
            product_list = '\n• '.join(missing_bk_products)
            raise UserError(
                f"❌ พบสินค้าที่ยังไม่ได้ระบุรหัสเชื่อมโยงบ้านเขียว:\n\n"
                f"• {product_list}\n\n"
                f"กรุณาแจ้งฝ่าย IT เพื่อลงรหัสเชื่อมโยงก่อนดำเนินการคืนสินค้า"
            )

        # หา branch และ location (คงไว้)
        location = self.env['stock.location'].search([
            ('branch_id', '=', self.order_id.branch_id.id),
            ('usage', '=', 'internal'),
        ], limit=1)

        if not location or not location.branch_id:
            if self.order_id:
                self.order_id.write({'return_greenhome_state': 'error'})
            raise UserError("❌ ไม่พบสาขาที่เชื่อมโยงกับคลังสินค้า")

        branch_name = location.branch_id.name
        branch_id_for_mysql = self._branch_mapping().get(branch_name)

        if not branch_id_for_mysql:
            raise UserError(f"❌ ไม่พบ branch mapping สำหรับ '{branch_name}'")

        # รวมจำนวนจาก move lines (ใช้ quantity_done จากใบจัดส่งเดิม)
        agg = {}  # pdn_id -> qty คืน
        for move in picking.move_ids:
            # ใช้ quantity_done จากใบจัดส่งเดิม เป็นปริมาณที่ต้องการคืน
            qty = float(move.quantity or 0.0)
            if qty <= 0:
                continue

            pdn_id = getattr(move.product_id, 'bk_reference_code', False)
            if not pdn_id:
                _logger.warning(f"⚠️ สินค้า '{move.product_id.display_name}' ไม่มี bk_reference_code - ข้าม")
                continue

            # สมมติว่าต้องการคืนเต็มจำนวนที่ปล่อยออกไปในใบนั้น
            agg[pdn_id] = agg.get(pdn_id, 0.0) + qty

        items = [{'pdn_id': k, 'qty': v} for k, v in agg.items() if v > 0]

        if not items:
            if self.order_id:
                self.order_id.write({'return_greenhome_state': 'error'})
            raise UserError("❌ ไม่พบรายการสินค้าที่ต้องคืน")

        # ใช้ชื่อใบจัดส่งขาออกเดิมเป็น Rent Head ID (renth_id)
        # เนื่องจากฟังก์ชันนี้ต้องการคืนโดยตรงที่ MySQL และไม่สนใจใบคืนใน Odoo
        rent_head_id = self._get_rent_head_id_for_return(picking)

        try:
            _logger.info(f"🔄 เริ่มคืนสินค้าบ้านเขียวสำหรับ {picking.name} | Rent Head ID ที่ใช้: {rent_head_id}")

            # 1) ลด total_rented ใน rentorder_detail (ในตาราง rentorder_detail/head)
            # จุดนี้คือการคืนสินค้าในรายงาน Greenhome
            self._apply_return_for_picking(
                branch_id_for_mysql=branch_id_for_mysql,
                items=items,
                picking_name=rent_head_id, # ใช้ชื่อใบจัดส่งขาออกเดิม
            )

            # 2) เดิน master_stockactual (เพิ่ม stockin, ลด stockout)
            # จุดนี้คือการอัปเดตสต็อกคงเหลือ/ถูกเช่าใน Greenhome
            self._update_mysql_after_return(
                branch_id_for_mysql=branch_id_for_mysql,
                items=items,
                branch_name=branch_name,
            )

            _logger.info(f"✅ คืนสินค้าบ้านเขียวสำเร็จ: {picking.name}")

            if self.order_id:
                self.order_id.write({'return_greenhome_state': 'done'})

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '✅ คืนสินค้าบ้านเขียวสำเร็จ',
                    'message': f'อัปเดตข้อมูลรายการ {picking.name} ในระบบบ้านเขียวเรียบร้อย\n'
                               f'จำนวนสินค้า: {len(items)} รายการ',
                    'sticky': False,
                    'type': 'success',
                    'next': {'type': 'ir.actions.act_window_close'}
                }
            }


        except UserError as ue:

            if self.order_id:
                self.order_id.write({'return_greenhome_state': 'error'})

            _logger.error(f"❌ คืนสินค้าบ้านเขียวล้มเหลว: {str(ue)}")

            raise



        except Exception as e:

            if self.order_id:
                self.order_id.write({'return_greenhome_state': 'error'})

            _logger.error(f"❌ เกิดข้อผิดพลาดร้ายแรง: {str(e)}", exc_info=True)

            raise UserError(f"❌ เกิดข้อผิดพลาดร้ายแรง: กรุณาติดต่อผู้ดูแลระบบ\nรายละเอียด: {str(e)}")


    def _get_rent_head_id_for_return(self, picking):
        """คืนค่า renth_id ที่ต้องไปลดในรายงาน: ถ้า origin = 'Return of XXX' -> ใช้ XXX, ไม่งั้นใช้ picking.name"""
        origin = (picking.origin or '').strip()
        marker = 'Return of '
        if origin.startswith(marker):
            return origin[len(marker):].strip()
        return picking.name

    def _sync_mysql_on_return(self, picking):
        """เรียกหลังใบรับคืน validate แล้ว: ลด total_rented และเดิน stockactual กลับด้าน"""

        # 🔍 DEBUG: ข้อมูลเริ่มต้น
        _logger.info(f"""
    ╔══════════════════════════════════════════════════
    ║ 🔄 SYNC MYSQL ON RETURN
    ╠══════════════════════════════════════════════════
    ║ Picking: {picking.name}
    ║ Origin: {picking.origin}
    ║ Location Dest: {picking.location_dest_id.complete_name if picking.location_dest_id else 'N/A'}
    ║ Location Src: {picking.location_id.complete_name if picking.location_id else 'N/A'}
    ╚══════════════════════════════════════════════════
        """)

        # หา branch_id MySQL - ใช้ location_dest_id เป็นหลัก (คลังที่คืนเข้า)
        location = picking.location_dest_id or picking.location_id

        if not location:
            raise UserError("❌ ไม่พบ location สำหรับใบคืน")

        if not location.branch_id:
            raise UserError(f"❌ Location '{location.complete_name}' ไม่มี branch กำหนด")

        branch_name = location.branch_id.name
        branch_id_for_mysql = self._branch_mapping().get(branch_name)

        _logger.info(f"📍 Branch: {branch_name} -> MySQL ID: {branch_id_for_mysql}")

        if not branch_id_for_mysql:
            if self.order_id:
                self.order_id.write({'return_greenhome_state': 'error'})
            raise UserError(f"❌ ไม่พบ branch mapping สำหรับ '{branch_name}'")

        # รวมจำนวนจาก move lines ที่ทำสำเร็จ
        agg = {}  # pdn_id -> qty คืน
        for move in picking.move_ids:
            qty = float(move.quantity or 0.0)
            if qty <= 0:
                continue

            pdn_id = getattr(move.product_id, 'bk_reference_code', False)
            if not pdn_id:
                _logger.warning(f"⚠️ สินค้า '{move.product_id.display_name}' ไม่มี bk_reference_code - ข้าม")
                continue

            agg[pdn_id] = agg.get(pdn_id, 0.0) + qty
            _logger.info(f"  ✓ {move.product_id.display_name} (PDN: {pdn_id}) = {qty}")

        items = [{'pdn_id': k, 'qty': v} for k, v in agg.items() if v > 0]

        if not items:
            _logger.warning("⚠️ ไม่มีรายการคืนที่ต้องซิงค์ (ไม่มี pdn_id หรือ qty = 0)")
            return

        _logger.info(f"📦 รายการคืนทั้งหมด: {len(items)} รายการ")

        # ใบหัวที่ต้องไปลดในรายงาน
        rent_head_id = self._get_rent_head_id_for_return(picking)
        _logger.info(f"📄 Rent Head ID: {rent_head_id}")

        # 1) ลด total_rented ใน rentorder_detail
        _logger.info("1️⃣ กำลังลด total_rented...")
        self._apply_return_for_picking(
            branch_id_for_mysql=branch_id_for_mysql,
            items=items,
            picking_name=rent_head_id,
        )

        # 2) เดิน master_stockactual
        _logger.info("2️⃣ กำลังอัปเดต stockactual...")
        self._update_mysql_after_return(
            branch_id_for_mysql=branch_id_for_mysql,
            items=items,
            branch_name=branch_name,
        )

        _logger.info("✅ ซิงค์ MySQL สำเร็จทั้งหมด!")

    def _fetch_stock_numbers_like_daily_report(self, branch_id_for_mysql, pdn_ids):
        """
        ดึง begin / rented / lost ตามสูตรเดียวกับ stock_daily_report.py แล้วคำนวณ remain
        """
        if not pdn_ids:
            return {}

        conn = None
        try:
            conn = pymysql.connect(
                host='150.95.26.61',
                user='greenhome',
                password='NPD@db789',
                database='npd_db',
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
            cur = conn.cursor()

            # ========== DEBUG: ตรวจสอบข้อมูลก่อนดึง ==========
            # Log branch_id ที่ใช้
            _logger.info(f"🔍 Fetching data for branch_id: {branch_id_for_mysql}")
            _logger.info(f"🔍 PDN IDs to fetch: {pdn_ids}")

            # ---------- Query 1: begin + price & weight (เหมือน report ทุกประการ) ----------
            in_clause = ','.join(['%s'] * len(pdn_ids))
            q_begin = f"""
                SELECT
                    master_branch.branch_name,
                    master_productname.pdn_id,
                    master_productname.pdn_name,
                    master_stockactual.sa_firststock,
                    master_productprice.pp_day,
                    master_productprice.pp_month,
                    master_productprice.pp_insure,
                    master_productprice.pp_lost,
                    master_productname.pdn_weight
                FROM master_stockactual
                INNER JOIN master_productname 
                    ON master_stockactual.sa_pdnid = master_productname.pdn_id
                INNER JOIN master_branch 
                    ON master_stockactual.branchid = master_branch.branch_id
                INNER JOIN master_productprice 
                    ON master_stockactual.sa_pdnid = master_productprice.pp_pdid
                WHERE master_stockactual.sa_cancel = 'N'
                  AND master_stockactual.branchid = %s
                  AND master_productprice.branchid = %s
                  AND master_productname.pdn_id IN ({in_clause})
                  AND master_branch.branch_id <> '01'
                ORDER BY master_productname.pdn_id
            """

            # Debug: พิมพ์ query ที่จะรัน
            _logger.info(f"🔍 Query Begin: {q_begin % (branch_id_for_mysql, branch_id_for_mysql, *pdn_ids)}")

            cur.execute(q_begin, (branch_id_for_mysql, branch_id_for_mysql, *pdn_ids))
            begin_rows = cur.fetchall()

            _logger.info(f"✅ Found {len(begin_rows)} rows for stock begin")

            data = {}
            for r in begin_rows:
                data[r['pdn_id']] = {
                    'branch_name': r['branch_name'],
                    'product_name': r['pdn_name'],
                    'stock_begin': r['sa_firststock'] or 0,
                    'price_per_day': r['pp_day'] or 0.0,
                    'price_per_month': r['pp_month'] or 0.0,
                    'guarantee': r['pp_insure'] or 0.0,
                    'lost_price': r['pp_lost'] or 0.0,
                    'weight': r['pdn_weight'] or 0.0,
                    'stock_rented': 0,
                    'stock_lost': 0,
                    'stock_remain': 0,
                }

            # ---------- Query 2: rented (เหมือนรายงานทุกประการ) ----------
            q_rented = f"""
                SELECT rentorder_detail.rentd_proid,
                       SUM(rentorder_detail.rentd_amount) AS total_rented
                FROM rentorder_detail
                JOIN rentorder_head 
                    ON rentorder_head.renth_id = rentorder_detail.rentd_id
                WHERE rentorder_head.branchid = %s
                  AND rentorder_head.renth_return = 'N'
                  AND rentorder_head.renth_cancel = 'N'
                  AND rentorder_detail.rentd_proid IN ({in_clause})
                GROUP BY rentorder_detail.rentd_proid
            """

            cur.execute(q_rented, (branch_id_for_mysql, *pdn_ids))
            rented_rows = cur.fetchall()

            _logger.info(f"✅ Found {len(rented_rows)} products with rented qty")

            for rr in rented_rows:
                pid = rr['rentd_proid']
                if pid in data:
                    data[pid]['stock_rented'] = rr['total_rented'] or 0
                    _logger.info(f"  - {pid}: rented = {rr['total_rented']}")

            # ---------- Query 3: lost (เพิ่มเงื่อนไขปีให้เหมือน report) ----------
            q_lost = f"""
                SELECT rentorder_detail.rentd_proid,
                       SUM(rentorder_detail.rentd_amount - rentorder_detail.rentd_amt_return) AS total_lost
                FROM rentorder_detail
                JOIN rentorder_head 
                    ON rentorder_head.renth_id = rentorder_detail.rentd_id
                WHERE rentorder_head.branchid = %s
                  AND rentorder_detail.rentd_proid IN ({in_clause})
                  AND rentd_amount <> rentd_amt_return
                  AND rentd_amt_return < rentd_amount
                  AND rentorder_head.renth_return = 'Y'
                  AND rentorder_head.renth_cancel = 'N'
                  AND YEAR(rentorder_head.renth_date_return) >= '2019'
                GROUP BY rentorder_detail.rentd_proid
            """

            cur.execute(q_lost, (branch_id_for_mysql, *pdn_ids))
            lost_rows = cur.fetchall()

            _logger.info(f"✅ Found {len(lost_rows)} products with lost qty")

            for lr in lost_rows:
                pid = lr['rentd_proid']
                if pid in data:
                    data[pid]['stock_lost'] = lr['total_lost'] or 0
                    _logger.info(f"  - {pid}: lost = {lr['total_lost']}")

            # ---------- Compute remain ----------
            for pid, rec in data.items():
                rec['stock_remain'] = (rec.get('stock_begin') or 0) \
                                      - (rec.get('stock_rented') or 0) \
                                      - (rec.get('stock_lost') or 0)

                _logger.info(f"📊 {pid}: begin={rec['stock_begin']}, "
                             f"rented={rec['stock_rented']}, "
                             f"lost={rec['stock_lost']}, "
                             f"remain={rec['stock_remain']}")

            return data

        except Exception as e:
            _logger.error(f"❌ Error fetching MySQL data: {str(e)}")
            raise UserError(f"❌ ดึงข้อมูลสต๊อกจาก MySQL ไม่สำเร็จ: {str(e)}")
        finally:
            try:
                if conn:
                    conn.close()
            except Exception:
                pass

    # ในส่วน default_get method
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        order_id = self.env.context.get('default_order_id')

        if 'can_return_greenhome' in fields_list:
            res['can_return_greenhome'] = self.env.user.allow_greenhome_return
        if not order_id:
            return res

        order = self.env['sale.order'].browse(order_id)
        location = self.env['stock.location'].search([
            ('branch_id', '=', order.branch_id.id),
            ('usage', '=', 'internal')
        ], limit=1)
        location_name = location.display_name if location else "ไม่พบคลังของสาขา"
        branch_name = location.branch_id.name if location and location.branch_id else False

        # ----------------- ตรวจสอบ bk_reference_code ก่อนดำเนินการ -----------------
        missing_bk_products = []
        for so_line in order.order_line.filtered(
                lambda l: not l.display_type
                          and l.product_id
                          and l.product_id.type in ('product', 'consu')
                          and (l.pfb_quantity or 0) > 0
        ):
            # ตรวจสอบว่ามี bk_reference_code หรือไม่
            if not so_line.product_id.bk_reference_code:
                missing_bk_products.append(so_line.product_id.display_name)

        # ถ้ามีสินค้าที่ไม่มี bk_reference_code ให้แจ้งเตือนทันที
        if missing_bk_products:
            product_list = '\n• '.join(missing_bk_products)
            raise UserError(
                f"❌ พบสินค้าที่ยังไม่ได้ระบุรหัสเชื่อมโยงบ้านเขียว:\n\n"
                f"• {product_list}\n\n"
                f"กรุณาแจ้งฝ่าย IT ส่วนกลางเพื่อลงรหัสเชื่อมโยงให้ครบถ้วนก่อนดำเนินการตัดสต๊อก"
            )

        # ----------------- เตรียมไลน์เดิม (ตัดสต๊อก) -----------------
        products_to_check = []
        base_lines = []
        for so_line in order.order_line.filtered(
                lambda l: not l.display_type
                          and l.product_id
                          and l.product_id.type in ('product', 'consu')
                          and (l.pfb_quantity or 0) > 0
        ):
            products_to_check.append({
                'pdn_id': so_line.product_id.bk_reference_code,
                'quantity': so_line.pfb_quantity,
                'product_id': so_line.product_id.id,
            })
            base_lines.append((0, 0, {
                'product_id': so_line.product_id.id,
                'quantity': so_line.pfb_quantity,
                'location_name': location_name,
            }))

        res['order_id'] = order.id
        res['confirm_line_ids'] = base_lines

        # ----------------- ดึง “ข้อมูลบ้านเขียว” แยกชุด -----------------
        branch_id_for_mysql = self._branch_mapping().get(branch_name)
        if not branch_id_for_mysql:
            return res

        pdn_ids = [p['pdn_id'] for p in products_to_check if p.get('pdn_id')]
        if not pdn_ids:
            return res

        # ดึงตัวเลข begin/rented/lost/remain แบบเดียวกับรายงาน
        data_by_pdn = self._fetch_stock_numbers_like_daily_report(branch_id_for_mysql, pdn_ids)

        # สร้าง greenhome_line_ids (คนละโมเดล ไม่ปน confirm_line_ids)
        greenhome_lines = []
        for item in products_to_check:
            pid = item['pdn_id']
            rec = data_by_pdn.get(pid, {}) or {}
            greenhome_lines.append((0, 0, {
                'pdn_code': pid,
                'branch_name': rec.get('branch_name'),
                'product_name': rec.get('product_name'),
                'stock_begin': rec.get('stock_begin', 0),
                'stock_rented': rec.get('stock_rented', 0),
                'stock_lost': rec.get('stock_lost', 0),
                'stock_remain': rec.get('stock_remain', 0),
            }))

        res['greenhome_line_ids'] = greenhome_lines

        # ----------------- เติม stock_remain ลง confirm_line_ids -----------------
        # สร้าง mapping pdn_id -> stock_remain
        pdn_remain_map = {}
        for item in products_to_check:
            pid = item.get('pdn_id')
            if pid and pid in data_by_pdn:
                product_id = item['product_id']
                pdn_remain_map[product_id] = data_by_pdn[pid].get('stock_remain', 0)

        # อัปเดต confirm_line_ids ที่สร้างไว้แล้ว
        updated_lines = []
        for cmd in res.get('confirm_line_ids', []):
            if cmd[0] == 0:  # (0, 0, vals)
                vals = cmd[2]
                product_id = vals.get('product_id')
                remain = pdn_remain_map.get(product_id, 0)
                vals['stock_remain'] = remain
                vals['need_manual_input'] = vals.get('quantity', 0) > remain
            updated_lines.append(cmd)
        res['confirm_line_ids'] = updated_lines

        return res

    def _fix_stale_reserved_qty(self, cut_items, location):
        """
        ปลด reserved เฉพาะสินค้าที่กำลังจะตัดสต็อก ที่ location นี้เท่านั้น
        เพื่อให้ action_assign() สามารถ reserve ใหม่ได้อย่างถูกต้อง

        ทำ 3 อย่าง:
        1) ปลด move_line reservations (set product_uom_qty=0) ที่ qty_done=0
           เฉพาะสินค้า+location ที่กำลังตัด
        2) Force set quant.reserved_quantity = 0
        3) Invalidate cache

        หลังจากนี้ action_assign() จะ reserve ใหม่เฉพาะ picking นี้
        """
        cr = self.env.cr
        product_ids = [pid for pid in cut_items.keys()]
        if not product_ids:
            return

        for product_id in product_ids:
            product = cut_items[product_id]['product']

            # 1) ปลด move_line reservations ที่ยังไม่ได้ทำ (qty_done=0)
            #    เฉพาะสินค้า + location ที่กำลังตัดสต็อก
            cr.execute("""
                UPDATE stock_move_line
                SET quantity = 0
                WHERE product_id = %s
                  AND location_id = %s
                  AND state NOT IN ('done', 'cancel')
                  AND quantity = 0
            """, (product_id, location.id))
            cleared = cr.rowcount
            if cleared > 0:
                _dbg(
                    f"⚠️ UNRESERVE: {product.display_name} @ {location.display_name} | "
                    f"ปลด {cleared} move_lines"
                )

            # 2) Force set reserved_quantity = 0 บน quant
            cr.execute("""
                UPDATE stock_quant
                SET reserved_quantity = 0
                WHERE product_id = %s
                  AND location_id = %s
                  AND reserved_quantity > 0
            """, (product_id, location.id))
            if cr.rowcount > 0:
                _dbg(f"   ✅ Reset quant reserved_quantity = 0")

            # 3) Invalidate cache
            self.env['stock.quant'].invalidate_recordset()
            product.invalidate_recordset(['qty_available', 'virtual_available', 'free_qty'])

    def _adjust_odoo_stock(self, product, location, target_qty):
        """
        ปรับ stock.quant ใน Odoo ให้มีจำนวนเท่ากับ target_qty
        ใช้สำหรับเติมสต็อกก่อนตัด (sync จากบ้านเขียว หรือจากที่ผู้ใช้กรอก)
        """
        current_qty = product.with_context(location=location.id).qty_available
        target_qty = float(target_qty)
        diff = target_qty - current_qty
        if diff > 0:
            _dbg(f"📦 _adjust_odoo_stock: {product.display_name} "
                 f"current={current_qty}, target={target_qty}, diff=+{diff}")
            self.env['stock.quant']._update_available_quantity(
                product, location, diff
            )
            # invalidate cache เพื่อให้ qty_available อ่านค่าใหม่
            product.invalidate_recordset(['qty_available', 'virtual_available', 'free_qty'])
        elif diff < 0:
            _dbg(f"📦 _adjust_odoo_stock: {product.display_name} "
                 f"current={current_qty} >= target={target_qty}, ไม่ต้องเติม")

    def confirm_stock_cut(self):
        pickings = self.order_id.picking_ids.filtered(lambda p: p.state != 'cancel').sorted('id', reverse=True)
        if not pickings:
            raise UserError("❌ ไม่พบใบจัดส่งสำหรับคำสั่งขายนี้")
        picking = pickings[0]

        # ============ ตรวจสอบ bk_reference_code ก่อนตัดสต๊อก ============
        missing_bk_products = []
        for line in self.confirm_line_ids.filtered(lambda l: l.product_id and (l.quantity or 0) > 0):
            if not line.product_id.bk_reference_code:
                missing_bk_products.append(line.product_id.display_name)

        if missing_bk_products:
            product_list = '\n• '.join(missing_bk_products)
            raise UserError(
                f"❌ ไม่สามารถตัดสต๊อกได้!\n\n"
                f"พบสินค้าที่ยังไม่ได้ระบุรหัสเชื่อมโยงบ้านเขียว (bk_reference_code):\n\n"
                f"• {product_list}\n\n"
                f"กรุณาแจ้งฝ่าย IT ส่วนกลางเพื่อลงรหัสเชื่อมโยงให้ครบถ้วนก่อนดำเนินการตัดสต๊อก\n"
                f"หากต้องการตัดสต๊อกด่วน สามารถใช้งานผ่านเมนู Inventory โดยตรง"
            )

        # sync วันที่เช่า
        if self.order_id.start_rent_date:
            picking.write({'start_x_date': self.order_id.start_rent_date})
        if self.order_id.end_rent_date:
            picking.write({'end_x_date': self.order_id.end_rent_date})

        if picking.state == 'done':
            raise UserError("📦 ใบจัดส่งนี้ถูกตัดสต๊อกเรียบร้อยแล้ว ไม่สามารถตัดซ้ำได้")

        # ใช้คลังสาขา
        location = self.env['stock.location'].search([
            ('branch_id', '=', self.order_id.branch_id.id),
            ('usage', '=', 'internal'),
        ], limit=1)
        if not location:
            raise UserError("❌ ไม่พบคลังต้นทางของสาขา (ย่อย)")

        if picking.location_id.id != location.id:
            picking.write({'location_id': location.id})

        # ✅ อ่าน product/quantity จาก SO line โดยตรง (เพราะ readonly field ใน TransientModel ไม่ถูกส่งกลับจาก client)
        so_lines = self.order_id.order_line.filtered(
            lambda l: not l.display_type
                      and l.product_id
                      and l.product_id.type in ('product', 'consu')
                      and (l.pfb_quantity or 0) > 0
        )
        # สร้าง mapping product_id -> {quantity, product, pdn_id}
        cut_items = {}
        for sol in so_lines:
            cut_items[sol.product_id.id] = {
                'product': sol.product_id,
                'quantity': sol.pfb_quantity,
                'pdn_id': sol.product_id.bk_reference_code,
            }
        _dbg(f"📊 cut_items from SO: {[(v['product'].display_name, v['quantity']) for v in cut_items.values()]}")

        # ✅ ดึง stock_remain จากบ้านเขียว (ดึงสดทุกครั้ง)
        branch_name = location.branch_id.name if location.branch_id else False
        branch_id_for_mysql = self._branch_mapping().get(branch_name)
        gh_remain_map = {}  # product_id -> stock_remain
        if branch_id_for_mysql:
            pdn_ids = [v['pdn_id'] for v in cut_items.values() if v.get('pdn_id')]
            pdn_to_product = {v['pdn_id']: pid for pid, v in cut_items.items() if v.get('pdn_id')}
            if pdn_ids:
                data_by_pdn = self._fetch_stock_numbers_like_daily_report(branch_id_for_mysql, pdn_ids)
                for pdn_id, rec in data_by_pdn.items():
                    product_id = pdn_to_product.get(pdn_id)
                    if product_id:
                        gh_remain_map[product_id] = rec.get('stock_remain', 0)
        _dbg(f"📊 gh_remain_map = {gh_remain_map}")

        # ✅ ดึง manual_stock_input จาก confirm_line_ids (field นี้ไม่ readonly จึงถูกส่งกลับ)
        manual_input_map = {}  # product_id -> manual_stock_input
        for line in self.confirm_line_ids:
            if line.product_id and line.manual_stock_input and line.manual_stock_input > 0:
                manual_input_map[line.product_id.id] = line.manual_stock_input

        # ✅ ตรวจสต๊อกก่อนตัด (เช็คจากบ้านเขียว + เติม Odoo stock)
        lines_need_input = []
        for product_id, item in cut_items.items():
            product = item['product']
            quantity = item['quantity']
            gh_remain = gh_remain_map.get(product_id, 0)
            manual_input = manual_input_map.get(product_id, 0)

            if quantity <= gh_remain:
                # กรณีพอ: เอา stock_remain ไปเติม Odoo stock ก่อนตัด
                self._adjust_odoo_stock(product, location, gh_remain)
                _dbg(f"✅ เติมสต็อก Odoo '{product.display_name}' = {gh_remain} (บ้านเขียว)")
            else:
                # กรณีไม่พอ: ต้องกรอก manual
                if manual_input > 0:
                    # ผู้ใช้กรอกแล้ว → เติม Odoo stock ตามที่ระบุ
                    self._adjust_odoo_stock(product, location, manual_input)
                    _dbg(f"✅ เติมสต็อก Odoo '{product.display_name}' = {manual_input} (กรอกเอง)")
                else:
                    lines_need_input.append((product, quantity, gh_remain))

        # ถ้ายังมีรายการที่ต้องกรอกสต็อกจริง → แจ้งเตือนให้กรอก
        if lines_need_input:
            msg_parts = []
            for product, quantity, remain in lines_need_input:
                msg_parts.append(
                    f"• {product.display_name} (ต้องตัด {quantity:.0f}, บ้านเขียวคงเหลือ {remain:.0f})"
                )
            raise UserError(
                "⚠️ กรุณานับจำนวนสต็อกจริงจากสาขา แล้วกรอกในช่อง 'จำนวนสต็อกจริง':\n\n"
                + "\n".join(msg_parts)
                + "\n\nกรอกจำนวนแล้วกด 'ยืนยันตัดสต๊อก' อีกครั้ง"
            )

        # ============ จัดการ moves + validate picking ============
        _dbg(f"🔧 picking {picking.name}: state={picking.state}, moves={len(picking.move_ids)}")
        for m in picking.move_ids:
            _dbg(f"   existing move: {m.product_id.display_name} (id={m.product_id.id}), state={m.state}, qty={m.product_uom_qty}, loc={m.location_id.complete_name}")

        # ✅ แก้ reserved_quantity ค้างใน stock.quant ก่อนตัดสต๊อก
        # ป้องกัน error "unreserve more products than you have in stock"
        self._fix_stale_reserved_qty(cut_items, location)

        # ✅ ถ้ายังไม่มี move → สร้างใหม่
        if not picking.move_ids:
            _dbg("📦 ไม่มี moves → สร้างใหม่")
            moves = []
            for product_id, item in cut_items.items():
                product = item['product']
                moves.append((0, 0, {
                    'name': product.name,
                    'product_id': product.id,
                    'product_uom_qty': float(item['quantity']),
                    'product_uom': product.uom_id.id,
                    'location_id': location.id,
                    'location_dest_id': picking.location_dest_id.id,
                    'picking_id': picking.id,
                }))
            picking.write({'move_ids': moves})
            _dbg(f"📦 สร้าง moves สำเร็จ: {len(moves)} รายการ")

        # ✅ อัพเดท location ของ moves ที่มีอยู่
        for move in picking.move_ids:
            if move.location_id.id != location.id:
                move.location_id = location.id

        # ✅ confirm moves ที่ยังเป็น draft
        draft_moves = picking.move_ids.filtered(lambda m: m.state == 'draft')
        if draft_moves:
            _dbg(f"📦 confirming {len(draft_moves)} draft moves")
            draft_moves._action_confirm()

        # ✅ unreserve ก่อน (ล้าง reservation เก่าบน picking นี้)
        if picking.move_ids.filtered(lambda m: m.state not in ('draft', 'cancel', 'done')):
            picking.do_unreserve()
            _dbg(f"📦 do_unreserve() done — ล้าง reservation เก่า")

        # ✅ reserve สต็อก
        picking.action_assign()
        _dbg(f"📦 action_assign() done. state={picking.state}")

        # ✅ ใส่ qty_done บน move_lines
        cut_items_keys = list(cut_items.keys())
        _dbg(f"📝 cut_items keys (product_ids): {cut_items_keys}")

        any_qty_set = False
        for move in picking.move_ids:
            item = cut_items.get(move.product_id.id)
            if not item:
                _dbg(f"⚠️ move product_id={move.product_id.id} ({move.product_id.display_name}) ไม่อยู่ใน cut_items, ข้าม")
                continue

            qty_done = float(item['quantity'] or 0.0)
            _dbg(f"📝 move {move.product_id.display_name}: qty_done={qty_done}, "
                 f"move_lines={len(move.move_line_ids)}, state={move.state}")

            if move.move_line_ids:
                # มี move_line อยู่แล้ว → set qty_done บน move_line แรก, ลบที่เหลือ
                first_ml = move.move_line_ids[0]
                for extra_ml in move.move_line_ids[1:]:
                    extra_ml.unlink()
                first_ml.write({
                    'picking_id': picking.id,
                    'quantity': qty_done,
                    'location_id': location.id,
                    'location_dest_id': move.location_dest_id.id,
                })
                if move.product_id.tracking in ('lot', 'serial') and not (first_ml.lot_id or first_ml.lot_name):
                    first_ml.lot_name = f"AUTO-{fields.Date.today()}"
                any_qty_set = True
                _dbg(f"  ✅ set qty_done={qty_done} on existing move_line {first_ml.id}")
            else:
                # ไม่มี move_line → สร้างใหม่ (ต้องใส่ picking_id ด้วย!)
                ml_vals = {
                    'move_id': move.id,
                    'picking_id': picking.id,
                    'product_id': move.product_id.id,
                    'product_uom_id': move.product_uom.id,
                    'location_id': location.id,
                    'location_dest_id': move.location_dest_id.id,
                    'quantity': qty_done,
                }
                if move.product_id.tracking in ('lot', 'serial'):
                    ml_vals['lot_name'] = f"AUTO-{fields.Date.today()}"
                self.env['stock.move.line'].create(ml_vals)
                any_qty_set = True
                _dbg(f"  ✅ created move_line via move.write with qty_done={qty_done}")

        if not any_qty_set:
            raise UserError(
                "❌ ไม่สามารถจับคู่สินค้ากับ moves ในใบจัดส่งได้\n\n"
                f"cut_items product_ids: {cut_items_keys}\n"
                f"move product_ids: {[m.product_id.id for m in picking.move_ids]}"
            )

        # ✅ invalidate cache + validate picking
        picking.invalidate_recordset()
        # ตรวจสอบ qty_done ก่อน validate
        for m in picking.move_ids:
            _dbg(f"  pre-validate: {m.product_id.display_name} quantity_done={m.quantity_done}, "
                 f"move_line_ids={len(m.move_line_ids)}")
            for ml in m.move_line_ids:
                _dbg(f"    move_line {ml.id}: qty_done={ml.quantity}, reserved={ml.product_uom_qty}")

        # ✅ Fix reserved อีกรอบก่อน validate (หลัง action_assign อาจสร้าง reservation ใหม่ที่ไม่ sync)
        self._fix_stale_reserved_qty(cut_items, location)

        _dbg(f"🚀 กำลัง button_validate() picking {picking.name}")
        picking.with_context(skip_immediate=True, skip_sms=True).button_validate()

        # --- NEW: เตรียมรายการที่จะอัปเดต MySQL ---
        # map สาขา Odoo -> branch_id MySQL

        # ใช้ตัวแปร location เดิม (ไม่ค้นหาใหม่)
        branch_name = location.branch_id.name if location and location.branch_id else False
        branch_id_for_mysql = self._branch_mapping().get(branch_name)

        # --- รวมจำนวนตาม pdn_id (aggregate) ใช้ cut_items จาก SO line ---
        items_for_mysql = []
        if branch_id_for_mysql:
            agg = {}  # pdn_id -> total qty
            for product_id, item in cut_items.items():
                pdn_id = item.get('pdn_id')
                qty = float(item['quantity'] or 0.0)
                if not pdn_id or qty <= 0:
                    continue
                agg[pdn_id] = agg.get(pdn_id, 0.0) + qty
            items_for_mysql = [{'pdn_id': k, 'qty': v} for k, v in agg.items() if v > 0]

        # --- อัปเดต “สินค้าที่ถูกเช่า” (rentorder_*) + (ออปชัน) เดิน stockactual ---
        if branch_id_for_mysql and items_for_mysql:
            try:
                # ทำให้ SELECT SUM(rentd_amount) เห็นผลทันที
                self._upsert_rented_for_picking(
                    branch_id_for_mysql=branch_id_for_mysql,
                    items=items_for_mysql,
                    picking_name=picking.name,  # ใช้เลขที่ใบจัดส่งอ้างอิงไปเป็น renth_id/rentd_id
                )

                # (ออปชัน) ถ้ายังต้องการให้ master_stockactual เดินด้วย ก็เรียกต่อ
                self._update_mysql_after_cut(
                    branch_id_for_mysql=branch_id_for_mysql,
                    items=items_for_mysql,
                    branch_name=branch_name
                )

                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': '✅ ตัดสต๊อกสำเร็จ',
                        'message': f'ใบจัดส่ง {picking.name} ถูกตัดใน Odoo และอัปเดตข้อมูลรายงานเรียบร้อย',
                        'sticky': False,
                        'type': 'success',
                        'next': {'type': 'ir.actions.act_window_close'}
                    }
                }
            except UserError as ue:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': '⚠️ ตัดสต๊อกสำเร็จ แต่ซิงก์รายงานล้มเหลว',
                        'message': str(ue),
                        'sticky': True,
                        'type': 'warning',
                        'next': {'type': 'ir.actions.act_window_close'}
                    }
                }

    @api.model
    def check_missing_bk_reference_codes(self):
        """
        ตรวจสอบและรายงานสินค้าทั้งหมดที่ไม่มี bk_reference_code
        สามารถเรียกใช้ผ่าน Server Actions หรือ Scheduled Actions
        """
        products_missing_bk = self.env['product.product'].search([
            ('bk_reference_code', '=', False),
            ('type', 'in', ['product', 'consu']),
            ('active', '=', True)
        ])

        if products_missing_bk:
            report_lines = []
            for product in products_missing_bk:
                report_lines.append(f"- {product.default_code or 'N/A'} | {product.name}")

            report_text = '\n'.join(report_lines)

            # สร้าง log message
            _logger.warning(
                f"พบสินค้า {len(products_missing_bk)} รายการที่ไม่มี bk_reference_code:\n{report_text}"
            )

            # ส่งอีเมลแจ้ง IT (ถ้าต้องการ)
            # mail_template = self.env.ref('module_name.email_template_missing_bk_code')
            # if mail_template:
            #     mail_template.send_mail(self.id, force_send=True)

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': f'⚠️ พบสินค้า {len(products_missing_bk)} รายการที่ไม่มีรหัสเชื่อมโยง',
                    'message': 'กรุณาตรวจสอบ log หรือรายงานเพื่อดูรายละเอียด',
                    'type': 'warning',
                    'sticky': True,
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '✅ ตรวจสอบเสร็จสิ้น',
                    'message': 'สินค้าทุกรายการมีรหัสเชื่อมโยงบ้านเขียวครบถ้วน',
                    'type': 'success',
                }
            }
class StockCutGreenhomeLine(models.TransientModel):
    _name = 'stock.cut.greenhome.line'
    _description = 'Greenhome Stock Snapshot Line'

    wizard_id = fields.Many2one('stock.cut.confirm.wizard', ondelete='cascade')

    # ฟิลด์สำหรับแสดงผลใน XML (ชื่อไทยตามที่ต้องการ)
    pdn_code = fields.Char(string='รหัสสินค้า')
    branch_name = fields.Char(string='สาขา')
    product_name = fields.Char(string='รายการสินค้า')

    stock_begin = fields.Integer(string='สินค้าตั้งต้น')
    stock_remain = fields.Integer(string='สินค้าคงเหลือ')
    stock_lost = fields.Integer(string='สินค้าที่ปรับหาย')
    stock_rented = fields.Integer(string='สินค้าที่ถูกเช่า')


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        res = super().button_validate()
        for picking in self:
            # เรียกเฉพาะใบรับคืนที่ done แล้ว
            is_return = (
                    picking.state == 'done'
                    and picking.picking_type_id.code == 'incoming'
                    and picking.sale_id  # ต้องมี SO
            )
            if is_return:
                wiz = self.env['stock.cut.confirm.wizard'].with_context(
                    default_order_id=picking.sale_id.id
                ).create({'order_id': picking.sale_id.id})
                # จะไปคืน “ตามใบ OUT ล่าสุดของ SO” (นี่แหละข้อจำกัด)
                wiz.return_greenhome_only()
        return res

    # def _should_sync_greenhome_on_return(self, picking):
    #     if picking.state != 'done':
    #         return False
    #     if picking.picking_type_id.code != 'incoming':
    #         return False
    #     # คืนจากลูกค้า → เข้าคลังภายใน (กันใบรับซัพพลายเออร์/อื่นๆ)
    #     if not (picking.location_id and picking.location_id.usage == 'customer'):
    #         return False
    #     if not (picking.location_dest_id and picking.location_dest_id.usage == 'internal'):
    #         return False
    #     # มาจาก wizard คืนของจริง หรือ origin ขึ้นต้น Return of ...
    #     if any(picking.move_ids.mapped('origin_returned_move_id')):
    #         return True
    #     if (picking.origin or '').startswith('Return of '):
    #         return True
    #     return False
    #
    # def action_done(self):
    #     res = super().action_done()
    #     for picking in self:
    #         try:
    #             if self._should_sync_greenhome_on_return(picking):
    #                 _logger.info(f"✅ เริ่มซิงค์ Greenhome (return) สำหรับ {picking.name}")
    #                 self.env['stock.cut.confirm.wizard']._sync_mysql_on_return(picking)
    #                 _logger.info(f"✅ ซิงก์สำเร็จ: {picking.name}")
    #         except Exception as e:
    #             msg = f"❌ ซิงค์ MySQL (รับคืน) ล้มเหลว: {e}"
    #             _logger.error(msg, exc_info=True)
    #             try:
    #                 self.env['bus.bus']._sendone(
    #                     self.env.user.partner_id,
    #                     'simple_notification',
    #                     {'type': 'danger', 'title': '⚠️ ซิงก์ MySQL (รับคืน) ล้มเหลว', 'message': str(e), 'sticky': True}
    #                 )
    #             except Exception:
    #                 pass
    #     return res

#     def button_validate(self):
#         res = super().button_validate()
#
#         for picking in self:
#             try:
#                 # ตรวจสอบว่าเป็นใบรับคืนหรือไม่
#                 is_return = (
#                         picking.picking_type_id.code == 'incoming'
#                         and (picking.origin or '').startswith('Return of ')
#                 )
#
#                 # 🔍 DEBUG: แสดงข้อมูลการตรวจสอบ
#                 _logger.info(f"""
# ╔══════════════════════════════════════════════════
# ║ 🔍 VALIDATE PICKING DEBUG
# ╠══════════════════════════════════════════════════
# ║ Picking: {picking.name}
# ║ Type Code: {picking.picking_type_id.code}
# ║ Origin: {picking.origin or 'N/A'}
# ║ State: {picking.state}
# ║ Is Return?: {is_return}
# ╚══════════════════════════════════════════════════
#                 """)
#
#                 if is_return and picking.state == 'done':
#                     _logger.info(f"✅ เริ่มซิงค์ MySQL สำหรับใบคืน: {picking.name}")
#
#                     # เรียก method คืนสินค้า
#                     self.env['stock.cut.confirm.wizard']._sync_mysql_on_return(picking)
#
#                     _logger.info(f"✅ ซิงค์ MySQL สำเร็จ: {picking.name}")
#
#             except Exception as e:
#                 error_msg = f"❌ ซิงค์ MySQL (รับคืน) ล้มเหลว: {str(e)}"
#                 _logger.error(error_msg, exc_info=True)
#
#                 # แจ้งเตือนผู้ใช้
#                 self.env['bus.bus']._sendone(
#                     self.env.user.partner_id,
#                     'simple_notification',
#                     {
#                         'type': 'danger',
#                         'title': '⚠️ ซิงค์ MySQL (รับคืน) ล้มเหลว',
#                         'message': str(e),
#                         'sticky': True,
#                     }
#                 )
#
#         return res

class StockScrap(models.Model):
    _inherit = 'stock.scrap'
    # คำหลักที่ถือว่าเป็นเหตุผล "สินค้าหาย"
    _LOSS_KEYWORDS = ('สินค้าหาย', 'lost', 'loss', 'หาย')

    def _is_loss_reason(self):
        """คืน True ถ้าเหตุผล/ปลายทางบอกว่าเป็น 'สินค้าหาย'"""
        self.ensure_one()
        texts = []
        # เหตุผลเป็น many2one
        if hasattr(self, 'reason_id') and self.reason_id:
            texts += [
                (self.reason_id.display_name or '').lower(),
                (getattr(self.reason_id, 'name', '') or '').lower()
            ]
        # เหตุผลเป็น char
        if hasattr(self, 'reason') and self.reason:
            texts.append((self.reason or '').lower())
        # ชื่อ location ปลายทาง (เช่น Virtual Locations/สินค้าหาย)
        if self.scrap_location_id:
            texts += [
                (self.scrap_location_id.complete_name or '').lower(),
                (self.scrap_location_id.name or '').lower()
            ]
        # มีคำใดคำหนึ่งที่ตรงกับคีย์เวิร์ด
        return any(k in t for t in texts for k in self._LOSS_KEYWORDS if t)

    def _upsert_lost_for_scrap(self, branch_name, pdn_id, qty, scrap_name):
        """บันทึก ‘สินค้าหาย’ ให้รายงานเห็น (rentorder_*):
        - head: rentorder_head.renth_id = scrap_name, renth_return='Y', renth_cancel='N'
        - detail: rentorder_detail (rentd_amount เพิ่มตาม qty, rentd_amt_return = 0)
        """
        if not (branch_name and pdn_id and qty > 0 and scrap_name):
            return

        conn = cur = None
        try:
            conn = pymysql.connect(
                host='150.95.26.61', user='greenhome', password='NPD@db789',
                database='npd_db', charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor, autocommit=False,
                connect_timeout=8, read_timeout=8, write_timeout=8,
            )
            cur = conn.cursor()

            wiz = self.env['stock.cut.confirm.wizard']
            fallback = wiz._branch_mapping().get(branch_name)
            branch_id = wiz._resolve_branch_id_mysql(cur, branch_name, fallback)
            if not branch_id:
                raise UserError(f"❌ MySQL: หา branch_id ของสาขา '{branch_name}' ไม่เจอ")

            # 1) ensure head (ตั้ง return=Y เพื่อให้ query_lost นับ, และลงวันที่เผื่อเงื่อนไข YEAR(...))
            cur.execute("SELECT renth_id FROM rentorder_head WHERE renth_id=%s LIMIT 1", (scrap_name,))
            if not cur.fetchone():
                cur.execute("""
                    INSERT INTO rentorder_head (renth_id, branchid, renth_return, renth_cancel, renth_date_return)
                    VALUES (%s, %s, 'Y', 'N', CURDATE())
                """, (scrap_name, branch_id))
            else:
                cur.execute("""
                    UPDATE rentorder_head
                       SET branchid=%s, renth_return='Y', renth_cancel='N', renth_date_return=COALESCE(renth_date_return, CURDATE())
                     WHERE renth_id=%s
                """, (branch_id, scrap_name))

            # 2) upsert detail (เพิ่มยอดหายสะสมในใบ scrap นี้)
            cur.execute("""
                SELECT rentd_amount, rentd_amt_return
                  FROM rentorder_detail
                 WHERE rentd_id=%s AND rentd_proid=%s
                 LIMIT 1
            """, (scrap_name, pdn_id))
            d = cur.fetchone()
            if not d:
                cur.execute("""
                    INSERT INTO rentorder_detail (rentd_id, rentd_proid, rentd_amount, rentd_amt_return)
                    VALUES (%s, %s, %s, 0)
                """, (scrap_name, pdn_id, qty))
            else:
                cur.execute("""
                    UPDATE rentorder_detail
                       SET rentd_amount = COALESCE(rentd_amount,0) + %s,
                           rentd_amt_return = 0
                     WHERE rentd_id=%s AND rentd_proid=%s
                """, (qty, scrap_name, pdn_id))

            conn.commit()

        except Exception as e:
            try:
                if conn: conn.rollback()
            except Exception:
                pass
            raise UserError(f"⚠️ บันทึก ‘สินค้าหาย’ ลงรายงานล้มเหลว: {e}")
        finally:
            try:
                if cur: cur.close()
            except Exception:
                pass
            try:
                if conn: conn.close()
            except Exception:
                pass

    def _mysql_decrease_stockin(self, branch_name, pdn_id, qty):
        """ลด sa_stockin ตามจำนวนที่หาย + debug log"""
        if not pdn_id or qty <= 0:
            _dbg(f"⛔ LOSS SKIP | pdn_id='{pdn_id}' | qty={qty}")
            return

        conn = cur = None
        try:
            conn = pymysql.connect(
                host='150.95.26.61', user='greenhome', password='NPD@db789',
                database='npd_db', charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor, autocommit=False,
                connect_timeout=8, read_timeout=8, write_timeout=8,
            )
            cur = conn.cursor()

            wiz = self.env['stock.cut.confirm.wizard']

            # ต้องมีคอลัมน์
            if not wiz._mysql_column_exists(cur, 'master_stockactual', 'sa_stockin'):
                raise UserError("❌ MySQL: ไม่พบคอลัมน์ sa_stockin ใน master_stockactual")

            # map + cross-check branch
            fallback = wiz._branch_mapping().get(branch_name)
            branch_id = wiz._resolve_branch_id_mysql(cur, branch_name, fallback)
            if not branch_id:
                raise UserError(f"❌ MySQL: หา branch_id ของสาขา '{branch_name or ''}' ไม่เจอ")

            # DEBUG ก่อนยิง UPDATE
            _dbg(
                f"🧪 LOSS DEBUG | branch_name='{branch_name}' -> branch_id='{branch_id}' | pdn_id='{pdn_id}' | qty={qty}")

            # ต้องมีแถวปลายทาง
            cur.execute("""
                SELECT 1
                  FROM master_stockactual
                 WHERE sa_cancel='N' AND branchid=%s AND sa_pdnid=%s
                 LIMIT 1
            """, (branch_id, pdn_id))
            if not cur.fetchone():
                raise UserError(f"❌ MySQL: ไม่พบ master_stockactual (branch={branch_id}, pdn_id={pdn_id})")

            # อัปเดต
            cur.execute("""
                UPDATE master_stockactual
                   SET sa_stockin = GREATEST(COALESCE(sa_stockin,0) - %s, 0)
                 WHERE sa_cancel='N' AND branchid=%s AND sa_pdnid=%s
            """, (float(qty), branch_id, pdn_id))
            if cur.rowcount == 0:
                raise UserError("❌ MySQL: ไม่มีแถวถูกอัปเดต (ตรวจ branch/pdn)")

            conn.commit()

            # VERIFY หลังอัปเดต
            cur.execute("""
                SELECT COALESCE(sa_stockin,0) AS stockin
                  FROM master_stockactual
                 WHERE sa_cancel='N' AND branchid=%s AND sa_pdnid=%s
                 LIMIT 1
            """, (branch_id, pdn_id))
            r = cur.fetchone() or {}
            _dbg(f"🧾 LOSS VERIFY | pdn={pdn_id} | stockin(after)={r.get('stockin')} | branch_id={branch_id}")

        except Exception as e:
            try:
                if conn: conn.rollback()
            except Exception:
                pass
            raise UserError(f"⚠️ อัปเดต MySQL (สินค้าหาย) ล้มเหลว: {e}")
        finally:
            try:
                if cur: cur.close()
            except Exception:
                pass
            try:
                if conn: conn.close()
            except Exception:
                pass


    # ------- main hook -------
    def action_validate(self):
        res = super().action_validate()

        for scrap in self:
            try:
                if scrap.scrap_qty <= 0 or not scrap.product_id:
                    continue
                if not scrap._is_loss_reason():
                    continue  # ไม่ใช่เคส 'สินค้าหาย'

                # หา branch จาก Source Location (คลังที่ของหาย)
                src_loc = scrap.location_id
                branch_name = src_loc.branch_id.name if src_loc and src_loc.branch_id else None

                # bk_reference_code -> pdn_id (บ้านเขียว)
                pdn_id = getattr(scrap.product_id, 'bk_reference_code', False)
                if not pdn_id:
                    raise UserError(
                        f"⚠️ สินค้า '{scrap.product_id.display_name}' ไม่มี bk_reference_code จึงซิงก์ MySQL ไม่ได้"
                    )

                qty = float(scrap.scrap_qty or 0.0)

                # DEBUG: ก่อนยิงไป MySQL (ยังเป็นข้อมูลฝั่ง Odoo)
                _dbg(
                    f"🧪 SCRAP DEBUG | scrap={scrap.name} | product='{scrap.product_id.display_name}' "
                    f"| pdn_id(bk_reference_code)='{pdn_id}' | qty={qty} | src_branch='{branch_name}' "
                    f"| reason='{getattr(scrap, 'reason', '') or getattr(getattr(scrap, 'reason_id', None), 'display_name', '')}' "
                    f"| scrap_location='{getattr(scrap.scrap_location_id, 'complete_name', '')}'"
                )

                # 1) ลดคงเหลือฝั่ง master_stockactual.sa_stockin
                self._mysql_decrease_stockin(branch_name, pdn_id, qty)

                # 2) บันทึก ‘สินค้าหาย’ ให้รายงานเห็น (rentorder_*), ใช้เลขใบ Scrap เป็นหัวรายการ
                self._upsert_lost_for_scrap(
                    branch_name=branch_name,
                    pdn_id=pdn_id,
                    qty=qty,
                    scrap_name=scrap.name,
                )

            except UserError as ue:
                self.env['bus.bus'].sendone(
                    (self._cr.dbname, 'res.partner', self.env.user.partner_id.id),
                    {'type': 'simple_notification', 'title': '⚠️ ซิงก์ MySQL (สินค้าหาย) ล้มเหลว', 'message': str(ue)}
                )
            except Exception as e:
                self.env['bus.bus'].sendone(
                    (self._cr.dbname, 'res.partner', self.env.user.partner_id.id),
                    {'type': 'simple_notification', 'title': '⚠️ ซิงก์ MySQL (สินค้าหาย) ล้มเหลว', 'message': str(e)}
                )
        return res
