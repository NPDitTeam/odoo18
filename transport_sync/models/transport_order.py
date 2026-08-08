# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import json
import logging

_logger = logging.getLogger(__name__)

# ⚙️ ตั้งค่าการเชื่อมต่อ Odoo 14
ODOO14_CONFIG = {
    'url': 'https://npderp.com',
    'database': 'NPD_Logistics_New',
    'username': 'Npd_admin',
    'password': '1234',
}

class TransportOrder(models.Model):
    _name = 'transport.order'
    _description = 'Transport Order from Odoo 14'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_order desc'

    # ข้อมูลพื้นฐาน
    name = fields.Char('เลขที่', required=True, copy=False, readonly=True,
                       default='New', tracking=True)
    odoo14_id = fields.Integer('Odoo 14 ID', readonly=True)
    branch_id = fields.Many2one('res.branch', string='สาขา', tracking=True, readonly=True)
    branch_name_o14 = fields.Char('ชื่อสาขา (Odoo14)', readonly=True)
    state = fields.Selection([
        ('draft', 'Quotation'),
        ('sent', 'Quotation Sent'),
        ('sale', 'Sales Order'),
        ('done', 'Locked'),
        ('cancel', 'Cancelled'),
    ], string='สถานะ', default='draft', tracking=True, readonly=True)
    date_order = fields.Datetime('วันที่สั่ง', tracking=True, default=fields.Datetime.now, readonly=True)
    validity_date = fields.Date('วันหมดอายุ', readonly=True)

    # ข้อมูลลูกค้า
    partner_id = fields.Many2one('res.partner', string='ลูกค้า', tracking=True, readonly=True)
    partner_name_o14 = fields.Char('ชื่อลูกค้า (Odoo14)', readonly=True)
    partner_phone = fields.Char('โทรศัพท์', readonly=True)
    partner_email = fields.Char('อีเมล', readonly=True)

    # 🚚 ข้อมูลการขนส่งพื้นฐาน (Basic)
    delivery_type = fields.Selection(
        string='ประเภทการจัดส่ง',
        selection=[
            ('customer', 'จัดส่งไปยังลูกค้า'),
            ('branch', 'จัดส่งมายังสาขา'),
        ],
        default='customer',
        required=True,
        tracking=True
    )
    pickup_location = fields.Text('สถานที่รับสินค้า', readonly=True)
    destination = fields.Text('ปลายทาง', readonly=True)
    vehicle_type_id = fields.Integer('Vehicle Type ID (Odoo14)', readonly=True)
    vehicle_type_name = fields.Char('ประเภทรถ', readonly=True)
    distance_km = fields.Float('ระยะทาง (กม.)', digits=(10, 3), readonly=True)
    shipping_cost_raw = fields.Float('ค่าขนส่งก่อนปัดเศษ', readonly=True)
    shipping_cost = fields.Float('ค่าขนส่งหลังปัดเศษ', readonly=True)
    use_special_delivery_zero = fields.Boolean('ใช้ค่าขนส่งพิเศษที่เป็น 0', readonly=True)
    shipping_cost_m = fields.Float('ค่าขนส่งพิเศษ', readonly=True, default=False)


    # 👤 ข้อมูลพนักงานและรถ (Vehicle Assignment)
    delivery_employee_id = fields.Integer('Employee ID (Odoo14)', readonly=True)
    delivery_employee_name = fields.Char('พนักงานส่งของ', readonly=True)
    license_plate_id = fields.Integer('License Plate ID (Odoo14)', readonly=True)
    license_plate_name = fields.Char('ทะเบียนรถ', readonly=False, tracking=True)  # ✅ สามารถแก้ไขได้

    # ⛽ ข้อมูลค่าน้ำมัน (Fuel)
    fuel_price_per_liter = fields.Float('ค่าน้ำมันเชื้อเพลิง (บาท/ลิตร)', digits=(10, 2), readonly=True)
    fuel_consumption_rate = fields.Float('อัตราสิ้นเปลืองเชื้อเพลิง (กม./ลิตร)', digits=(10, 2), readonly=True)
    fuel_used_per_trip = fields.Float('จำนวนน้ำมันที่ใช้ต่อเที่ยว (ลิตร)', digits=(10, 3), readonly=True)
    fuel_cost_per_trip = fields.Float('ค่าน้ำมันต่อเที่ยว (บาท)', digits=(10, 2), readonly=True)

    # 📉 ข้อมูลค่าเสื่อมราคา (Depreciation)
    vehicle = fields.Float('ต้นทุนค่ารถ (บาท)', digits=(12, 2), readonly=True)
    vehicle_cost = fields.Float('ต้นทุนค่ารถดอกเบี้ย 12% (บาท)', digits=(12, 2), readonly=True)
    salvage_value = fields.Float('มูลค่าซาก (บาท)', digits=(12, 2), readonly=True)
    depreciation_period = fields.Integer('ระยะเวลาค่าเสื่อมราคา (ปี)', readonly=True)
    depreciation_per_trip = fields.Float('ค่าเสื่อมตัวรถต่อรอบ (บาท)', digits=(10, 2), readonly=True)

    # 💰 ค่าใช้จ่ายประจำปี (Annual Expenses)
    annual_vehicle_tax_y = fields.Float('ค่าภาษีป้ายวงกลม (บาท/ปี)', digits=(10, 2), readonly=True)
    annual_vehicle_tax = fields.Float('ค่าภาษีป้ายวงกลม (คำนวณ)', digits=(10, 2), readonly=True)
    annual_insurance_class2 = fields.Float('ค่าเบี้ยประกันชั้น 2 (บาท/ปี)', digits=(10, 2), readonly=True)
    annual_insurance_class1 = fields.Float('ประกันชั้น 1 (บาท/ปี)', digits=(10, 2), readonly=True)
    annual_compulsory_insurance1 = fields.Float('ค่าประกัน พรบ (บาท/ปี)', digits=(10, 2), readonly=True)
    annual_compulsory_insurance = fields.Float('ค่าประกัน พรบ (คำนวณ)', digits=(10, 2), readonly=True)
    total_depreciation_per_trip = fields.Float('รวมค่าเสื่อมต่อรอบ (บาท)', digits=(10, 2), readonly=True)

    # 👷 ข้อมูลค่าแรงงาน (Labor)
    labor_costs = fields.Integer('ค่าแรง (บาท)', readonly=True)
    working_days_per_month = fields.Integer('จำนวนวันทำงานต่อเดือน', readonly=True)
    driver_salary = fields.Float('เงินเดือนพนักงานขับรถ (บาท/เดือน)', digits=(10, 2), readonly=True)
    maintenance_cost = fields.Float('ค่าซ่อมบำรุง (บาท/เดือน)', digits=(10, 2), readonly=True)
    trips_per_day = fields.Integer('จำนวนรอบที่วิ่ง/วัน', readonly=True)
    labor_cost_per_trip = fields.Float('ค่าแรงต่อเที่ยว (บาท)', digits=(10, 2), readonly=True)
    total_labor_per_trip = fields.Float('ค่าแรงต่อรอบไปกลับ (บาท)', digits=(10, 2), readonly=True)

    # 📋 ค่าใช้จ่ายอื่นๆ (Other Expenses)
    trip_allowance = fields.Float('ค่าเที่ยว', digits=(10, 2), readonly=True)
    daily_allowance = fields.Float('ค่าเบี้ยเลี้ยง', digits=(10, 2), readonly=True)

    # 📊 สรุปต้นทุนและกำไร (Cost Summary)
    total_cost_per_trip = fields.Float('ราคาต้นทุน (บาท/รอบ)', digits=(10, 2), readonly=True)
    profit_per_trip = fields.Float('กำไร (บาท/รอบ)', digits=(10, 2), readonly=True)
    profit_per_trip_p = fields.Float('กำไร% (เปอร์เซ็นต์)', digits=(10, 2), readonly=True)

    # ข้อมูลการเงิน
    amount_untaxed = fields.Float('ยอดก่อนภาษี', readonly=True)
    amount_tax = fields.Float('ภาษี', readonly=True)
    amount_total = fields.Float('ยอดรวม', readonly=True)
    currency_name = fields.Char('สกุลเงิน', default='THB', readonly=True)

    # ข้อมูลเพิ่มเติม
    salesperson_name = fields.Char('พนักงานขาย', readonly=True)
    company_id = fields.Many2one('res.company', string='บริษัท', default=lambda self: self.env.company, readonly=True)
    company_name_o14 = fields.Char('ชื่อบริษัท (Odoo14)', readonly=True)
    note = fields.Html('หมายเหตุ', readonly=True)

    # บิลต่ออายุจากบ้านเขียว
    is_renew_green_house = fields.Boolean('บิลต่ออายุจากบ้านเขียว', default=False, readonly=True)

    # รายการสินค้า
    order_line_ids = fields.One2many('transport.order.line', 'order_id', string='รายการสินค้า', readonly=True)
    order_lines_count = fields.Integer('จำนวนรายการ', compute='_compute_order_lines_count')
    total_weight_order = fields.Float('น้ำหนักรวมคำสั่ง', compute='_compute_total_weight', readonly=True)

    # สถานะการซิงค์
    sync_date = fields.Datetime('วันที่ซิงค์', readonly=True)
    sync_status = fields.Selection([
        ('pending', 'รอซิงค์'),
        ('synced', 'ซิงค์แล้ว'),
        ('error', 'ผิดพลาด'),
    ], string='สถานะซิงค์', default='pending')
    sync_error = fields.Text('ข้อผิดพลาด')

    # ✅ ส่งตรงจาก Odoo 18 (ปุ่ม "ส่งไปยังระบบขนส่ง") ไม่ใช่ sync จาก Odoo 14
    # ใช้แยก record คนละแหล่ง กันชนกับข้อมูลที่ sync มาจาก Odoo 14
    is_from_odoo18 = fields.Boolean('ส่งจาก Odoo 18', default=False, readonly=True)

    def _receive_from_sale_order(self, order_data):
        """ รับข้อมูลจาก sale.order (odoo18) ส่งตรง — create/update โดยจับคู่ด้วย name
            เฉพาะ record ที่มาจาก odoo18 (กันชนกับข้อมูล sync จาก odoo14)
            คืนค่า (record, status) โดย status = 'created' / 'updated' / 'skipped' """
        name = order_data.get('name')
        if not name:
            raise UserError(_('ไม่พบเลขเอกสาร'))
        # ตั้ง id = 0 เพื่อไม่ให้ไปเซ็ต odoo14_id ชนกับของจริงจาก odoo14
        order_data = dict(order_data)
        order_data['id'] = 0

        existing = self.search([
            ('name', '=', name),
            ('is_from_odoo18', '=', True),
        ], limit=1)

        if existing:
            # ป้องกัน: ถ้ารายการเดิมถูกดึงไปใช้/อ้างอิงแล้วจนลบ-อัพเดทไม่ได้
            # ให้ rollback แล้ว"ข้าม" (ไม่ทำให้ทั้ง transaction พัง)
            try:
                with self.env.cr.savepoint():
                    self._update_existing_order(existing, order_data)
                    existing.write({'is_from_odoo18': True, 'odoo14_id': 0})
            except Exception as e:
                _logger.warning(
                    "⏭️ ข้ามการอัพเดทคำสั่งขนส่ง %s (ลบ/อัพเดทรายการเดิมไม่ได้ "
                    "อาจถูกดึงไปใช้แล้ว): %s", name, e)
                return existing, 'skipped'
            _logger.info("🔄 อัพเดทคำสั่งขนส่งจาก Odoo18: %s", name)
            return existing, 'updated'

        order = self._process_order(order_data)
        if order:
            order.write({'is_from_odoo18': True, 'odoo14_id': 0})
            _logger.info("✅ สร้างคำสั่งขนส่งจาก Odoo18: %s", name)
        return order, 'created'

    @api.model_create_multi
    def create(self, vals_list):
        """Override create - ใช้เลขเอกสารจาก Odoo 14 โดยตรง (ไม่ generate sequence)"""
        for vals in vals_list:
            # ✅ ถ้ามี name มาจาก Odoo 14 แล้ว ใช้ตัวนั้นเลย (ไม่ต้อง generate)
            # ✅ ถ้าเป็น 'New' หรือไม่มี name ให้ generate (กรณีสร้างใหม่ด้วยมือ)
            if vals.get('name') and vals.get('name') != 'New':
                # ใช้ name จาก Odoo 14 โดยตรง ไม่ต้อง generate
                pass
            else:
                # กรณีสร้างด้วยมือ ให้ generate sequence ใหม่
                vals['name'] = self.env['ir.sequence'].next_by_code('transport.order') or 'New'
        return super().create(vals_list)

    @api.depends('order_line_ids')
    def _compute_order_lines_count(self):
        for record in self:
            record.order_lines_count = len(record.order_line_ids)

    @api.depends('order_line_ids', 'order_line_ids.total_weight')
    def _compute_total_weight(self):
        for record in self:
            record.total_weight_order = sum(line.total_weight for line in record.order_line_ids)

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None):
        """Override search เพื่อกรองตาม branch ของ user"""
        # ✅ เพิ่ม domain filter ตาม user preference
        user = self.env.user
        
        # ถ้า user ไม่เลือก "แสดงทุกสาขา" ให้กรองเฉพาะสาขาของตัวเอง
        if not user.show_all_branches and user.branch_id:
            # เพิ่ม domain สำหรับกรองเฉพาะ branch ของ user
            branch_domain = [('branch_id', '=', user.branch_id.id)]
            domain = domain + branch_domain if domain else branch_domain
            _logger.debug(f"🔍 Filtering by branch: {user.branch_id.name}")
        else:
            _logger.debug(f"🌍 Showing all branches (show_all_branches={user.show_all_branches})")
        
        # ✅ Odoo 18: ไม่มี access_rights_uid parameter
        return super(TransportOrder, self)._search(domain, offset=offset, limit=limit, order=order)

    def action_sync_from_odoo14(self):
        """ดึงข้อมูลจาก Odoo 14 ทั้งหมด (Full Sync)"""
        return self._sync_orders_from_odoo14(today_only=False)

    def action_sync_recent_from_odoo14(self):
        """ดึงข้อมูลจาก Odoo 14 เฉพาะวันปัจจุบัน + อัพเดทข้อมูลที่มีอยู่"""
        return self._sync_orders_from_odoo14(today_only=True)

    @api.model
    def action_remove_duplicates(self):
        """ลบรายการที่ name ซ้ำกัน (เก็บไว้เฉพาะรายการแรก)"""
        deleted_count = self._remove_duplicate_orders()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'ลบรายการซ้ำสำเร็จ!',
                'message': f'🗑️ ลบรายการซ้ำแล้ว {deleted_count} รายการ',
                'type': 'success',
                'sticky': False,
            }
        }

    def _remove_duplicate_orders(self):
        """ลบ records ที่มี name ซ้ำกัน (เก็บไว้เฉพาะ record ที่มี id น้อยที่สุด)
           ✅ ข้าม record ที่มี vehicle_booking อ้างอิงอยู่
        """
        self.env.cr.execute("""
            SELECT name, COUNT(*), array_agg(id ORDER BY id)
            FROM transport_order
            WHERE name IS NOT NULL
            GROUP BY name
            HAVING COUNT(*) > 1
        """)
        duplicates = self.env.cr.fetchall()
        
        total_deleted = 0
        skipped_in_use = 0
        
        for name, count, ids in duplicates:
            # เก็บ id แรก (น้อยที่สุด) ลบที่เหลือ
            ids_to_delete = ids[1:]  # ข้าม id แรก
            if ids_to_delete:
                # ✅ เช็คว่ามี vehicle_booking อ้างอิงอยู่หรือไม่
                self.env.cr.execute("""
                    SELECT transport_order_id 
                    FROM vehicle_booking 
                    WHERE transport_order_id = ANY(%s)
                """, (ids_to_delete,))
                used_ids = [row[0] for row in self.env.cr.fetchall()]
                
                # ✅ กรองเอาเฉพาะ id ที่ไม่ถูกใช้งาน
                safe_to_delete = [id for id in ids_to_delete if id not in used_ids]
                skipped_in_use += len(used_ids)
                
                if safe_to_delete:
                    orders_to_delete = self.browse(safe_to_delete)
                    orders_to_delete.unlink()
                    total_deleted += len(safe_to_delete)
                    _logger.info(f"🗑️ ลบ {name} ที่ซ้ำ: {len(safe_to_delete)} รายการ (เก็บ ID {ids[0]})")
                
                if used_ids:
                    _logger.info(f"⏭️ ข้าม {name} ที่ซ้ำ: {len(used_ids)} รายการ (มี booking อ้างอิง)")
        
        if total_deleted > 0 or skipped_in_use > 0:
            _logger.info(f"🗑️ ลบรายการซ้ำ: {total_deleted} รายการ, ข้ามเพราะถูกใช้งาน: {skipped_in_use} รายการ")
        
        return total_deleted

    def _delete_tr_orders_safe(self):
        """ลบข้อมูล TR- แบบปลอดภัย - ข้าม record ที่มี vehicle_booking อ้างอิง"""
        tr_orders = self.search([('name', '=like', 'TR-%')])
        
        if not tr_orders:
            return 0, 0
        
        tr_ids = tr_orders.ids
        
        # ✅ เช็คว่ามี vehicle_booking อ้างอิงอยู่หรือไม่
        self.env.cr.execute("""
            SELECT transport_order_id 
            FROM vehicle_booking 
            WHERE transport_order_id = ANY(%s)
        """, (tr_ids,))
        used_ids = [row[0] for row in self.env.cr.fetchall()]
        
        # ✅ กรองเอาเฉพาะ id ที่ไม่ถูกใช้งาน
        safe_to_delete = [id for id in tr_ids if id not in used_ids]
        
        deleted_count = 0
        skipped_count = len(used_ids)
        
        if safe_to_delete:
            orders_to_delete = self.browse(safe_to_delete)
            deleted_count = len(orders_to_delete)
            orders_to_delete.unlink()
            _logger.info(f"🗑️ ลบข้อมูล TR- แล้ว {deleted_count} รายการ")
        
        if skipped_count > 0:
            _logger.info(f"⏭️ ข้าม TR- ที่มี booking อ้างอิง: {skipped_count} รายการ")
        
        return deleted_count, skipped_count

    def _sync_orders_from_odoo14(self, today_only=False):
        """ดึงข้อมูล Sale Orders จาก Odoo 14
           today_only=True: ดึงเฉพาะวันนี้ + อัพเดทข้อมูลที่มีอยู่
           today_only=False: ดึงทั้งหมด (Full Sync)
        """
        try:
            # 🗑️ ลบรายการซ้ำก่อน (ถ้า name ซ้ำกัน ลบให้เหลือแค่ 1)
            duplicate_deleted_count = self._remove_duplicate_orders()
            
            # 🔧 แก้ไขข้อมูล profit_per_trip_p ที่ผิด (> 1.0 หมายถึงยังไม่ได้หาร 100)
            wrong_profit_orders = self.search([('profit_per_trip_p', '>', 1.0)])
            if wrong_profit_orders:
                for order in wrong_profit_orders:
                    order.profit_per_trip_p = order.profit_per_trip_p / 100.0
                _logger.info(f"🔧 แก้ไขค่า profit_per_trip_p แล้ว {len(wrong_profit_orders)} รายการ")
            
            # 🗑️ ลบข้อมูล TR- แบบปลอดภัย (ข้าม record ที่มี booking อ้างอิง)
            tr_deleted_count, tr_skipped_count = self._delete_tr_orders_safe()
            
            session = requests.Session()

            # ✅ ปิด SSL warning (ถ้ามี cert issue)
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

            # 1. Authenticate
            auth_url = f"{ODOO14_CONFIG['url']}/web/session/authenticate"
            auth_data = {
                "jsonrpc": "2.0",
                "params": {
                    "db": ODOO14_CONFIG['database'],
                    "login": ODOO14_CONFIG['username'],
                    "password": ODOO14_CONFIG['password'],
                }
            }

            _logger.info(f"🔐 Authenticating to: {auth_url}")
            _logger.info(f"📝 Database: {ODOO14_CONFIG['database']}")
            _logger.info(f"👤 Username: {ODOO14_CONFIG['username']}")

            # ✅ เพิ่ม verify=False ถ้ามีปัญหา SSL
            auth_response = session.post(
                auth_url,
                json=auth_data,
                timeout=10,
                verify=False  # ✅ เพิ่มบรรทัดนี้ถ้ามีปัญหา SSL cert
            )

            # ✅ Debug response
            _logger.info(f"📡 Response Status: {auth_response.status_code}")
            _logger.info(f"📄 Response Body: {auth_response.text[:500]}")  # แสดง 500 ตัวอักษรแรก

            auth_result = auth_response.json()

            if not auth_result.get('result') or not auth_result['result'].get('uid'):
                error_detail = auth_result.get('error', {}).get('message', 'Unknown error')
                raise UserError(f'❌ ไม่สามารถ Login Odoo 14 ได้\n\nรายละเอียด: {error_detail}')

            _logger.info(f"✅ Authentication successful. User ID: {auth_result['result']['uid']}")

            # 2. Call API with Pagination
            api_url = f"{ODOO14_CONFIG['url']}/api/sale_orders"
            headers = {'Content-Type': 'application/json'}
            
            created_count = 0
            updated_count = 0
            skipped_count = 0
            error_count = 0
            all_orders = []
            
            # ✅ ดึงข้อมูลแบบ pagination
            offset = 0
            page_limit = 100  # ✅ เพิ่มเป็น 100 รายการต่อหน้า
            total_records = None
            
            # ✅ กรองวันที่ (ถ้า today_only=True → ดึงเฉพาะวันปัจจุบัน)
            from datetime import datetime, timedelta
            if today_only:
                today_date = fields.Date.context_today(self)
                date_start = today_date.strftime('%Y-%m-%d 00:00:00')
                date_end = today_date.strftime('%Y-%m-%d 23:59:59')
                _logger.info(f"📅 Sync Today: {date_start} ~ {date_end}")
            
            _logger.info(f"📡 Starting pagination from: {api_url} (today_only={today_only})")
            
            while True:
                api_params = {
                    "limit": page_limit,
                    "offset": offset,
                    "state": "sale",  # ✅ กรองเฉพาะ state = 'sale'
                }
                
                # ✅ เพิ่มการกรองวันที่ถ้าเป็น today_only (เฉพาะวันปัจจุบัน)
                if today_only:
                    api_params["date_from"] = date_start
                    api_params["date_to"] = date_end
                
                api_data = {
                    "jsonrpc": "2.0",
                    "method": "call",
                    "params": api_params,
                    "id": 1
                }
                
                _logger.info(f"📄 Fetching page: offset={offset}, limit={page_limit}")
                
                api_response = session.post(
                    api_url,
                    json=api_data,
                    headers=headers,
                    timeout=30,
                    verify=False
                )

                if api_response.status_code != 200:
                    raise UserError(f'❌ API Error: HTTP {api_response.status_code}\n{api_response.text}')

                api_result = api_response.json()

                if not api_result.get('result') or not api_result['result'].get('success'):
                    error_msg = api_result.get('result', {}).get('message', 'Unknown error')
                    raise UserError(f"❌ API Error: {error_msg}")

                result_data = api_result['result']
                orders_data = result_data.get('data', [])
                total_records = result_data.get('total', 0)
                
                # ✅ Debug: แสดงข้อมูลที่ได้จาก API
                _logger.info(f"📊 API Response Summary:")
                _logger.info(f"   - count (returned): {result_data.get('count', 0)}")
                _logger.info(f"   - total (available): {total_records}")
                _logger.info(f"   - message: {result_data.get('message', 'N/A')}")
                
                if not orders_data:
                    _logger.info(f"✅ No more records. Stopping pagination.")
                    break
                
                _logger.info(f"📦 Received {len(orders_data)} orders (offset {offset} of {total_records} total)")
                all_orders.extend(orders_data)
                
                # เพิ่ม offset สำหรับหน้าถัดไป
                offset += len(orders_data)
                
                # ถ้าดึงครบแล้วให้หยุด
                if offset >= total_records:
                    _logger.info(f"✅ Reached end of records ({offset} >= {total_records})")
                    break
            
            _logger.info(f"📦 Total orders fetched: {len(all_orders)} of {total_records}")

            # 3. ✅ กรองเฉพาะเลขเอกสารที่ขึ้นต้นด้วย "SO-"
            so_orders = [order for order in all_orders if order.get('name', '').startswith('SO-')]
            _logger.info(f"🔍 Filtered: {len(so_orders)} SO- orders from {len(all_orders)} total")
            
            # ✅ กรองวันที่ฝั่ง Odoo 18 ด้วย (กรณี API ไม่รองรับ date_from/date_to)
            if today_only:
                today_str = fields.Date.context_today(self).strftime('%Y-%m-%d')
                before_filter = len(so_orders)
                so_orders = [
                    order for order in so_orders
                    if order.get('date_order', '')[:10] == today_str
                ]
                _logger.info(f"📅 Date filter (today={today_str}): {len(so_orders)} orders from {before_filter}")

            # ✅ Debug: แสดง order แรกเพื่อดูโครงสร้างข้อมูล
            if so_orders:
                first_order = so_orders[0]
                _logger.info(f"📝 Sample Order: ID={first_order.get('id')}, Name={first_order.get('name')}, State={first_order.get('state')}")

            # 4. Process orders - สร้างใหม่หรืออัพเดทถ้ามีอยู่แล้ว
            for order_data in so_orders:
                try:
                    order_name = order_data.get('name')
                    existing = False
                    
                    # ✅ เช็คว่า name มีอยู่แล้วหรือไม่ (เช็คจาก name เป็นหลัก)
                    # กรองเฉพาะ record ที่มาจาก odoo14 (ไม่ยุ่งกับที่ส่งตรงจาก odoo18)
                    if order_name:
                        existing = self.search([
                            ('name', '=', order_name),
                            ('is_from_odoo18', '=', False),
                        ], limit=1)

                    # ✅ เช็คจาก odoo14_id ด้วย (กันซ้ำจาก ID)
                    if not existing:
                        existing = self.search([
                            ('odoo14_id', '=', order_data['id']),
                            ('is_from_odoo18', '=', False),
                        ], limit=1)
                    
                    if existing:
                        # ✅ อัพเดทข้อมูลที่มีอยู่แล้ว (แทนที่จะข้าม)
                        self._update_existing_order(existing, order_data)
                        updated_count += 1
                        _logger.debug(f"🔄 อัพเดท: {order_name}")
                    else:
                        # ✅ สร้างใหม่
                        self._process_order(order_data)
                        created_count += 1
                    
                except Exception as e:
                    error_count += 1
                    _logger.error(f"❌ Error processing order {order_data.get('name')}: {str(e)}")

            sync_mode = "เฉพาะวันนี้" if today_only else "ทั้งหมด"
            message = (
                f'✅ ซิงค์สำเร็จ! (โหมด: {sync_mode})\n\n'
                f'🗑️ ลบรายการซ้ำ: {duplicate_deleted_count} รายการ\n'
                f'🗑️ ลบข้อมูล TR-: {tr_deleted_count} รายการ\n'
                f'⏭️ ข้าม TR- (มี booking): {tr_skipped_count} รายการ\n'
                f'🔍 พบทั้งหมด: {total_records} รายการใน Odoo 14\n'
                f'📄 กรองเฉพาะ SO-: {len(so_orders)} รายการ\n'
                f'✨ นำเข้าใหม่: {created_count} รายการ\n'
                f'🔄 อัพเดท: {updated_count} รายการ\n'
                f'❌ ข้อผิดพลาด: {error_count} รายการ'
            )
            _logger.info(
                f"✅ Sync completed (today_only={today_only}): Duplicates={duplicate_deleted_count}, Deleted TR-={tr_deleted_count}, Skipped TR-={tr_skipped_count}, "
                f"Total={total_records}, Filtered={len(so_orders)}, New={created_count}, Updated={updated_count}, Errors={error_count}"
            )

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'ซิงค์สำเร็จ!',
                    'message': message,
                    'type': 'success',
                    'sticky': False,
                }
            }

        except requests.exceptions.ConnectionError as e:
            error_msg = f'❌ ไม่สามารถเชื่อมต่อกับ Odoo 14 ได้\n\nURL: {ODOO14_CONFIG["url"]}\nError: {str(e)}'
            _logger.error(error_msg)
            raise UserError(error_msg)
        except requests.exceptions.Timeout as e:
            error_msg = f'❌ Connection Timeout\n\nURL: {ODOO14_CONFIG["url"]}'
            _logger.error(error_msg)
            raise UserError(error_msg)
        except Exception as e:
            error_msg = f'❌ เกิดข้อผิดพลาด: {str(e)}'
            _logger.error(f'Sync error: {str(e)}', exc_info=True)
            raise UserError(error_msg)

    def _process_order(self, order_data):
        """ประมวลผลและบันทึก order (เรียกหลังจากเช็คซ้ำแล้ว)"""

        # ✅ เช็คว่าต้องมีเลขเอกสารจาก Odoo 14
        if not order_data.get('name'):
            _logger.error(f"❌ ไม่มีเลขเอกสาร (name) จาก Odoo 14 - ข้าม order ID: {order_data.get('id')}")
            return False

        # ✅ ค้นหาสาขาจากชื่อ
        branch_name_o14 = order_data.get('branch_id')
        branch_id = self._find_branch(branch_name_o14)

        # ค้นหา/สร้าง partner
        partner_id = False
        if order_data.get('partner_name'):
            partner_id = self._find_or_create_partner(
                order_data['partner_name'],
                order_data.get('partner_phone'),
                order_data.get('partner_email')
            )

        # ค้นหา company
        company_id = self._find_company(order_data.get('company_name'))

        # ✅ ดึงข้อมูล shipment_information
        shipment_info = order_data.get('shipment_information', {})
        basic = shipment_info.get('basic', {})
        vehicle_assignment = shipment_info.get('vehicle_assignment', {})
        fuel = shipment_info.get('fuel', {})
        depreciation = shipment_info.get('depreciation', {})
        annual_expenses = shipment_info.get('annual_expenses', {})
        labor = shipment_info.get('labor', {})

        cost_summary = shipment_info.get('cost_summary', {})

        # ✅ ตรวจสอบและใช้ค่า state จาก API (ต้องเป็น 'sale' เพราะกรองไว้แล้ว)
        order_state = order_data.get('state', 'sale')
        _logger.info(f"📝 Order {order_data.get('name')}: state from API = '{order_state}'")

        # เตรียมข้อมูล order
        order_vals = {
            'name': order_data['name'],  # ✅ ใช้เลขเอกสารจาก Odoo 14 โดยตรง (ไม่ต้อง default)
            'odoo14_id': order_data['id'],
            'branch_id': branch_id,
            'branch_name_o14': branch_name_o14,
            'state': order_state,  # ✅ ใช้ state ที่ตรวจสอบแล้ว
            'date_order': order_data.get('date_order') or fields.Datetime.now(),
            'validity_date': order_data.get('validity_date'),

            # ลูกค้า
            'partner_id': partner_id,
            'partner_name_o14': order_data.get('partner_name'),
            'partner_phone': order_data.get('partner_phone'),
            'partner_email': order_data.get('partner_email'),

            # 🚚 ข้อมูลการขนส่งพื้นฐาน
            'pickup_location': basic.get('pickup_location'),
            'destination': basic.get('destination'),
            'vehicle_type_id': basic.get('vehicle_type_id'),
            'vehicle_type_name': basic.get('vehicle_type_name'),
            'distance_km': basic.get('distance_km', 0.0),
            'shipping_cost_raw': basic.get('shipping_cost_raw', 0.0),
            'shipping_cost': basic.get('shipping_cost', 0.0),
            'delivery_type': basic.get('delivery_type'),
            'use_special_delivery_zero': basic.get('use_special_delivery_zero', 0.0),
            'shipping_cost_m': basic.get('shipping_cost_m', 0.0),

            # 👤 พนักงานและรถ
            'delivery_employee_id': vehicle_assignment.get('delivery_employee_id'),
            'delivery_employee_name': vehicle_assignment.get('delivery_employee_name'),
            'license_plate_id': vehicle_assignment.get('license_plate_id'),
            'license_plate_name': vehicle_assignment.get('license_plate_name'),

            # ⛽ ข้อมูลน้ำมัน
            'fuel_price_per_liter': fuel.get('fuel_price_per_liter', 0.0),
            'fuel_consumption_rate': fuel.get('fuel_consumption_rate', 0.0),
            'fuel_used_per_trip': fuel.get('fuel_used_per_trip', 0.0),
            'fuel_cost_per_trip': fuel.get('fuel_cost_per_trip', 0.0),

            # 📉 ค่าเสื่อมราคา
            'vehicle': depreciation.get('vehicle', 0.0),
            'vehicle_cost': depreciation.get('vehicle_cost', 0.0),
            'salvage_value': depreciation.get('salvage_value', 0.0),
            'depreciation_period': depreciation.get('depreciation_period', 0),
            'depreciation_per_trip': depreciation.get('depreciation_per_trip', 0.0),

            # 💰 ค่าใช้จ่ายประจำปี
            'annual_vehicle_tax_y': annual_expenses.get('annual_vehicle_tax_y', 0.0),
            'annual_vehicle_tax': annual_expenses.get('annual_vehicle_tax', 0.0),
            'annual_insurance_class2': annual_expenses.get('annual_insurance_class2', 0.0),
            'annual_insurance_class1': annual_expenses.get('annual_insurance_class1', 0.0),
            'annual_compulsory_insurance1': annual_expenses.get('annual_compulsory_insurance1', 0.0),
            'annual_compulsory_insurance': annual_expenses.get('annual_compulsory_insurance', 0.0),
            'total_depreciation_per_trip': annual_expenses.get('total_depreciation_per_trip', 0.0),

            # 👷 ค่าแรงงาน
            'labor_costs': labor.get('labor_costs', 0),
            'working_days_per_month': labor.get('working_days_per_month', 0),
            'driver_salary': labor.get('driver_salary', 0.0),
            'maintenance_cost': labor.get('maintenance_cost', 0.0),
            'trips_per_day': labor.get('trips_per_day', 0),
            'labor_cost_per_trip': labor.get('labor_cost_per_trip', 0.0),
            'total_labor_per_trip': labor.get('total_labor_per_trip', 0.0),

            # 📋 ค่าใช้จ่ายอื่นๆ
            'trip_allowance': basic.get('trip_allowance', 0.0),      # ✅ ดึงจาก basic
            'daily_allowance': basic.get('daily_allowance', 0.0),    # ✅ ดึงจาก basic

            # 📊 สรุปต้นทุนและกำไร
            'total_cost_per_trip': cost_summary.get('total_cost_per_trip', 0.0),
            'profit_per_trip': cost_summary.get('profit_per_trip', 0.0),
            'profit_per_trip_p': cost_summary.get('profit_per_trip_p', 0.0) / 100.0,  # ✅ หาร 100 เพราะ widget="percentage" คูณ 100 อัตโนมัติ

            # การเงิน
            'amount_untaxed': order_data.get('amount_untaxed', 0.0),
            'amount_tax': order_data.get('amount_tax', 0.0),
            'amount_total': order_data.get('amount_total', 0.0),
            'currency_name': order_data.get('currency', 'THB'),

            # เพิ่มเติม
            'salesperson_name': order_data.get('salesperson_name'),
            'company_id': company_id,
            'company_name_o14': order_data.get('company_name'),
            'note': order_data.get('note', ''),
            'is_renew_green_house': order_data.get('is_renew_green_house', False),

            # ซิงค์
            'sync_date': fields.Datetime.now(),
            'sync_status': 'synced',
        }

        # ✅ สร้าง order ใหม่
        order = self.create(order_vals)
        _logger.info(f"✅ นำเข้า: {order.name}")

        # ประมวลผลรายการสินค้า
        self._process_order_lines(order, order_data.get('order_lines', []))

        return order

    def _update_existing_order(self, existing_order, order_data):
        """อัพเดทข้อมูล order ที่มีอยู่แล้วจาก Odoo 14 (ไม่สร้างซ้ำ)"""

        # ✅ ค้นหาสาขาจากชื่อ (ถ้าหาไม่เจอ ให้คงค่าเดิมไว้)
        branch_name_o14 = order_data.get('branch_id')
        branch_id = self._find_branch(branch_name_o14, fallback=existing_order.branch_id.id)

        # ค้นหา/สร้าง partner
        partner_id = existing_order.partner_id.id
        if order_data.get('partner_name'):
            partner_id = self._find_or_create_partner(
                order_data['partner_name'],
                order_data.get('partner_phone'),
                order_data.get('partner_email')
            )

        # ค้นหา company
        company_id = self._find_company(order_data.get('company_name'))

        # ✅ ดึงข้อมูล shipment_information
        shipment_info = order_data.get('shipment_information', {})
        basic = shipment_info.get('basic', {})
        vehicle_assignment = shipment_info.get('vehicle_assignment', {})
        fuel = shipment_info.get('fuel', {})
        depreciation = shipment_info.get('depreciation', {})
        annual_expenses = shipment_info.get('annual_expenses', {})
        labor = shipment_info.get('labor', {})
        cost_summary = shipment_info.get('cost_summary', {})

        order_state = order_data.get('state', 'sale')

        # ✅ เตรียมข้อมูลสำหรับ update (ไม่ update name เพราะเป็น key)
        update_vals = {
            'odoo14_id': order_data['id'],
            'branch_id': branch_id,
            'branch_name_o14': branch_name_o14,
            'state': order_state,
            'date_order': order_data.get('date_order') or existing_order.date_order,
            'validity_date': order_data.get('validity_date'),

            # ลูกค้า
            'partner_id': partner_id,
            'partner_name_o14': order_data.get('partner_name'),
            'partner_phone': order_data.get('partner_phone'),
            'partner_email': order_data.get('partner_email'),

            # 🚚 ข้อมูลการขนส่งพื้นฐาน
            'pickup_location': basic.get('pickup_location'),
            'destination': basic.get('destination'),
            'vehicle_type_id': basic.get('vehicle_type_id'),
            'vehicle_type_name': basic.get('vehicle_type_name'),
            'distance_km': basic.get('distance_km', 0.0),
            'shipping_cost_raw': basic.get('shipping_cost_raw', 0.0),
            'shipping_cost': basic.get('shipping_cost', 0.0),
            'delivery_type': basic.get('delivery_type'),
            'use_special_delivery_zero': basic.get('use_special_delivery_zero', 0.0),
            'shipping_cost_m': basic.get('shipping_cost_m', 0.0),

            # 👤 พนักงานและรถ
            'delivery_employee_id': vehicle_assignment.get('delivery_employee_id'),
            'delivery_employee_name': vehicle_assignment.get('delivery_employee_name'),
            'license_plate_id': vehicle_assignment.get('license_plate_id'),
            'license_plate_name': vehicle_assignment.get('license_plate_name'),

            # ⛽ ข้อมูลน้ำมัน
            'fuel_price_per_liter': fuel.get('fuel_price_per_liter', 0.0),
            'fuel_consumption_rate': fuel.get('fuel_consumption_rate', 0.0),
            'fuel_used_per_trip': fuel.get('fuel_used_per_trip', 0.0),
            'fuel_cost_per_trip': fuel.get('fuel_cost_per_trip', 0.0),

            # 📉 ค่าเสื่อมราคา
            'vehicle': depreciation.get('vehicle', 0.0),
            'vehicle_cost': depreciation.get('vehicle_cost', 0.0),
            'salvage_value': depreciation.get('salvage_value', 0.0),
            'depreciation_period': depreciation.get('depreciation_period', 0),
            'depreciation_per_trip': depreciation.get('depreciation_per_trip', 0.0),

            # 💰 ค่าใช้จ่ายประจำปี
            'annual_vehicle_tax_y': annual_expenses.get('annual_vehicle_tax_y', 0.0),
            'annual_vehicle_tax': annual_expenses.get('annual_vehicle_tax', 0.0),
            'annual_insurance_class2': annual_expenses.get('annual_insurance_class2', 0.0),
            'annual_insurance_class1': annual_expenses.get('annual_insurance_class1', 0.0),
            'annual_compulsory_insurance1': annual_expenses.get('annual_compulsory_insurance1', 0.0),
            'annual_compulsory_insurance': annual_expenses.get('annual_compulsory_insurance', 0.0),
            'total_depreciation_per_trip': annual_expenses.get('total_depreciation_per_trip', 0.0),

            # 👷 ค่าแรงงาน
            'labor_costs': labor.get('labor_costs', 0),
            'working_days_per_month': labor.get('working_days_per_month', 0),
            'driver_salary': labor.get('driver_salary', 0.0),
            'maintenance_cost': labor.get('maintenance_cost', 0.0),
            'trips_per_day': labor.get('trips_per_day', 0),
            'labor_cost_per_trip': labor.get('labor_cost_per_trip', 0.0),
            'total_labor_per_trip': labor.get('total_labor_per_trip', 0.0),

            # 📋 ค่าใช้จ่ายอื่นๆ
            'trip_allowance': basic.get('trip_allowance', 0.0),
            'daily_allowance': basic.get('daily_allowance', 0.0),

            # 📊 สรุปต้นทุนและกำไร
            'total_cost_per_trip': cost_summary.get('total_cost_per_trip', 0.0),
            'profit_per_trip': cost_summary.get('profit_per_trip', 0.0),
            'profit_per_trip_p': cost_summary.get('profit_per_trip_p', 0.0) / 100.0,

            # การเงิน
            'amount_untaxed': order_data.get('amount_untaxed', 0.0),
            'amount_tax': order_data.get('amount_tax', 0.0),
            'amount_total': order_data.get('amount_total', 0.0),
            'currency_name': order_data.get('currency', 'THB'),

            # เพิ่มเติม
            'salesperson_name': order_data.get('salesperson_name'),
            'company_id': company_id,
            'company_name_o14': order_data.get('company_name'),
            'note': order_data.get('note', ''),
            'is_renew_green_house': order_data.get('is_renew_green_house', False),

            # ซิงค์
            'sync_date': fields.Datetime.now(),
            'sync_status': 'synced',
        }

        # ✅ อัพเดทข้อมูล
        existing_order.write(update_vals)
        _logger.info(f"🔄 อัพเดท: {existing_order.name}")

        # ✅ อัพเดทรายการสินค้าด้วย
        self._process_order_lines(existing_order, order_data.get('order_lines', []))

    def _process_order_lines(self, order, lines_data):
        """ประมวลผลรายการสินค้า"""
        TransportOrderLine = self.env['transport.order.line']
        order.order_line_ids.unlink()

        for line_data in lines_data:
            product_id = False
            if line_data.get('product_name'):
                product_id = TransportOrderLine._find_or_create_product(
                    line_data['product_name'],
                    line_data.get('product_code')
                )

            line_vals = {
                'order_id': order.id,
                'odoo14_id': line_data.get('id'),
                'product_id': product_id,
                'product_name_o14': line_data.get('product_name'),
                'product_code': line_data.get('product_code'),
                'description': line_data.get('description', ''),
                'quantity': line_data.get('quantity', 0.0),
                'uom_name': line_data.get('uom'),
                'price_unit': line_data.get('price_unit', 0.0),
                'discount': line_data.get('discount', 0.0),
                'price_subtotal': line_data.get('price_subtotal', 0.0),
                'price_tax': line_data.get('price_tax', 0.0),
                'price_total': line_data.get('price_total', 0.0),
                'total_weight': line_data.get('total_weight', 0.0),
            }
            TransportOrderLine.create(line_vals)

    def _find_or_create_partner(self, partner_name, partner_phone, partner_email):
        """ค้นหาหรือสร้างลูกค้าจากชื่อ"""
        if not partner_name:
            return False

        partner = self.env['res.partner'].search([('name', '=', partner_name)], limit=1)

        if not partner:
            partner = self.env['res.partner'].create({
                'name': partner_name,
                'phone': partner_phone,
                'email': partner_email,
                'customer_rank': 1,
            })
            _logger.info(f'✅ สร้างลูกค้าใหม่: {partner_name}')

        return partner.id

    def _find_branch(self, branch_name, fallback=False):
        """ค้นหาสาขา (res.branch) จากชื่อที่ได้จาก Odoo 14

        ⚠️ ต้องค้นหาแบบ sudo + bypass_branch_company_filter เพราะ res.branch
        ถูกจำกัดด้วย ir.rule ของ multi_branch_management_aagam ให้ user เห็น
        เฉพาะสาขาของตัวเอง (user.branch_ids) ถ้าค้นด้วยสิทธิ์ user ที่กดซิงค์
        order ของสาขาอื่นจะหาไม่เจอ → branch_id ว่าง ทั้งที่ชื่อสาขามีอยู่จริง
        (ฟิลด์ branch_name_o14 เป็น Char จึงยังแสดงค่าตามปกติ)
        """
        if not branch_name:
            return fallback

        if isinstance(branch_name, (list, tuple)):
            # เผื่อ API ส่งมาเป็น [id, name] แบบ many2one ของ Odoo
            branch_name = branch_name[1] if len(branch_name) > 1 else False
        if not branch_name:
            return fallback

        branch_name = branch_name.strip()
        Branch = self.env['res.branch'].sudo().with_context(bypass_branch_company_filter=True)
        branch = Branch.search([('name', '=', branch_name)], limit=1)
        if not branch:
            branch = Branch.search([('name', 'ilike', branch_name)], limit=1)

        if not branch:
            _logger.warning(f"⚠️ ไม่พบสาขา: {branch_name} ใน Odoo 18")
            return fallback

        return branch.id

    def _find_company(self, company_name):
        """ค้นหาบริษัทจากชื่อ"""
        if not company_name:
            return self.env.company.id

        company = self.env['res.company'].search([('name', '=', company_name)], limit=1)
        return company.id if company else self.env.company.id


class TransportOrderLine(models.Model):
    _name = 'transport.order.line'
    _description = 'Transport Order Line'

    order_id = fields.Many2one('transport.order', string='คำสั่งขนส่ง', required=True, ondelete='cascade', readonly=True)
    odoo14_id = fields.Integer('Odoo 14 Line ID', readonly=True)

    product_id = fields.Many2one('product.product', string='สินค้า', readonly=True)
    product_name_o14 = fields.Char('ชื่อสินค้า (Odoo14)', readonly=True)
    product_code = fields.Char('รหัสสินค้า', readonly=True)
    description = fields.Text('รายละเอียด', readonly=True)

    quantity = fields.Float('จำนวน', digits='Product Unit of Measure', default=1.0, readonly=True)
    uom_name = fields.Char('หน่วย', readonly=True)
    price_unit = fields.Float('ราคาต่อหน่วย', readonly=True)
    discount = fields.Float('ส่วนลด (%)', readonly=True)
    price_subtotal = fields.Float('ยอดย่อย', readonly=True)
    price_tax = fields.Float('ภาษี', readonly=True)
    price_total = fields.Float('ยอดรวม', readonly=True)
    total_weight = fields.Float('น้ำหนักรวม', digits=(10, 3), readonly=True)

    def _find_or_create_product(self, product_name, product_code):
        """ค้นหาหรือสร้างสินค้าจากชื่อ"""
        if not product_name:
            return False

        if product_code:
            product = self.env['product.product'].search([('default_code', '=', product_code)], limit=1)
            if product:
                return product.id

        product = self.env['product.product'].search([('name', '=', product_name)], limit=1)

        if not product:
            product = self.env['product.product'].create({
                'name': product_name,
                'default_code': product_code,
                'type': 'consu',  # ✅ เปลี่ยนจาก 'product' เป็น 'consu'
                'list_price': 0.0,
            })
            _logger.info(f'✅ สร้างสินค้าใหม่: {product_name}')

        return product.id