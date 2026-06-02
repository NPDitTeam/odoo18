from odoo import fields, models, api, exceptions
from datetime import timedelta
from odoo.exceptions import UserError, ValidationError
from datetime import date
import logging
_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    pfb_date_of_rent = fields.Integer(string="Day of Rent")
    start_rent_date = fields.Date(string="วันที่เริ่มต้นการเช่า", default=fields.Date.context_today)
    end_rent_date = fields.Date(string="วันที่สิ้นสุดการเช่า")
    on_site = fields.Char('หน้างาน', required=True)

    is_past_due = fields.Boolean(string="Is Past Due", compute="_compute_is_past_due", store=True)

    contact_type = fields.Selection([
        ('branch', 'สาขา'),
        ('sale', 'Sales')
    ], string="การติดต่อของลูกค้า", required=True, default=False)

    pfb_so_type = fields.Selection([
        ('sale', 'Sales'),
        ('rent', 'Rent')],
        string="Sale Type",
        index=True, default='sale', required=True)

    date_order_x = fields.Date(string="วันที่สั่งซื้อ")

    # deposit_return_status from npd_deposit_return_status module (Odoo 14)
    deposit_return_status = fields.Selection([
        ('not_returned', 'ลูกค้ายังไม่คืนสินค้า'),
        ('no_voucher', 'สาขายังไม่สร้างการคืนเงินประกัน'),
        ('waiting_finance', 'รอคืนเงินประกันจากการเงิน'),
        ('done', 'เสร็จสิ้น'),
    ], string='สถานะคืนเงินประกัน', tracking=True)

    user_lock_rent = fields.Boolean(string="User Lock Rent", compute="_compute_user_lock_rent", store=False)

    @api.depends('state')
    def _compute_user_lock_rent(self):
        for record in self:
            record.user_lock_rent = self.env.user.lock_rent

    @api.onchange('date_order', 'partner_id')
    def _onchange_date_order_x(self):
        self.date_order_x = self.date_order


    @api.constrains('contact_type')
    def _check_contact_type(self):
        for record in self:
            if not record.contact_type:
                raise exceptions.ValidationError("กรุณาเลือกช่องทางการติดต่อ!")

    sales_contact = fields.Many2one('res.users', string="Sales ที่ติดต่อ")

    @api.onchange('contact_type')
    def _onchange_contact_type(self):
        """ กำหนดค่าฟิลด์ Sales ที่ติดต่อ ตาม contact_type """
        if self.contact_type == 'branch':
            self.sales_contact = self.env.user  # ตั้งค่าให้เป็น User ที่ล็อกอินอยู่
            return {
                'domain': {'sales_contact': [('id', '=', self.env.user.id)]}  # บังคับเลือกเฉพาะผู้ใช้ที่ล็อกอิน
            }
        elif self.contact_type == 'sale':
            sales_users = self.env['hr.employee'].search([
                ('department_id.name', '=', 'Sales'),
                ('user_id', '!=', False)
            ]).mapped('user_id')

            if sales_users:
                self.sales_contact = False  # ล้างค่าที่เลือกไว้ก่อนหน้า
                return {'domain': {'sales_contact': [('id', 'in', sales_users.ids)]}}
            else:
                self.sales_contact = False
                return {
                    'warning': {
                        'title': "ไม่มีพนักงานขาย",
                        'message': "ไม่พบพนักงานในแผนก Sales กรุณาเพิ่มพนักงานก่อน!"
                    },
                    'domain': {'sales_contact': [('id', '=', False)]}  # ปิดการเลือก
                }

    # menu_name = fields.Char(string="Menu Name", compute="_compute_menu_name", store=False)
    #
    # def _compute_menu_name(self):
    #     for record in self:
    #         try:
    #             # ตรวจสอบและดึงค่า context params
    #             context_params = self.env.context.get('params', {})
    #             if not isinstance(context_params, dict):
    #                 print("Context params is not a valid dictionary")
    #                 record.menu_name = ''
    #                 continue
    #
    #             # ดึงค่า menu_id จาก context
    #             menu_id = context_params.get('menu_id')
    #             print(f"Context params: {context_params}, Menu ID: {menu_id}")
    #
    #             if menu_id:
    #                 menu = self.env['ir.ui.menu'].sudo().browse(menu_id)
    #                 if menu.exists():
    #                     record.menu_name = menu.name.strip() if menu.name else ''
    #                     print(f"Menu found: {record.menu_name}")
    #                 else:
    #                     record.menu_name = ''
    #                     print("Menu not found")
    #             else:
    #                 record.menu_name = ''
    #                 print("No menu_id found in context")
    #
    #         except Exception as e:
    #             record.menu_name = ''
    #             print(f"Error fetching menu name: {e}")



    @api.depends('end_rent_date')
    def _compute_is_past_due(self):
        today = date.today()
        for record in self:
            record.is_past_due = record.end_rent_date and record.end_rent_date < today

    pricelist_id = fields.Many2one(
        comodel_name="product.pricelist",
        string="รายการราคา",
        required=True,
        domain=lambda self: (
            [('pricelist_branch_id', '=', self.env.user.branch_id.id)]
            if 'pricelist_branch_id' in self.env['product.pricelist']._fields
               and hasattr(self.env.user, 'branch_id')
            else []
        ),
    )
    @api.onchange('pfb_date_of_rent', 'start_rent_date','end_rent_date')
    def _onchange_rent_days(self):
        """คำนวณ end_rent_date เมื่อระบุ pfb_date_of_rent และ start_rent_date"""
        for record in self:
            if record.pfb_date_of_rent and record.start_rent_date:
                # เพิ่มจำนวนวันโดยตรง รวมถึงวันที่เริ่มต้น
                record.end_rent_date = record.start_rent_date + timedelta(days=record.pfb_date_of_rent)
            else:
                record.end_rent_date = False





    rental_status = fields.Selection([
        ('due_date', 'ครบกำหนด'),
        ('nearly_due', 'ใกล้ครบกำหนด'),
        ('overdue', 'เกินกำหนด'),
        ('in_rent', 'อยู่ระหว่างการเช่า'),
        ('ready', 'ทำราคา'),
        ('done', 'ปิดบิล')
    ], string="สถานะการเช่า", compute="_compute_rental_status", store=True, default='ready')

    is_due_date = fields.Boolean(compute="_compute_status_flags", store=True)
    is_nearly_due = fields.Boolean(compute="_compute_status_flags", store=True)
    is_overdue = fields.Boolean(compute="_compute_status_flags", store=True)
    is_in_rent = fields.Boolean(compute="_compute_status_flags", store=True)
    is_ready = fields.Boolean(compute="_compute_status_flags", store=True)
    is_done = fields.Boolean(compute="_compute_status_flags", store=True)

    @api.depends('invoice_ids', 'end_rent_date', 'origin', 'pfb_so_type')
    def _compute_rental_status(self):
        today = fields.Date.today()
        for record in self:

            # ข้าม record ที่คืนเงินประกันเสร็จสิ้นแล้ว (ห้ามเปลี่ยน rental_status กลับ)
            if record.deposit_return_status == 'done':
                continue

            # ถ้ามีใบแจ้งหนี้อย่างน้อย 1 รายการ
            if record.rental_status != 'returned':
                # print("pfb_date_of_rent", record.pfb_date_of_rent," rent_days_overdue", record.rent_days_overdue)
                rent_days = record.pfb_date_of_rent or 0
                remaining_days = 0
                overdue_days = 0
                if record.rent_days_overdue <= 30:
                    if record.end_rent_date:
                        try:
                            end_date = fields.Date.from_string(record.end_rent_date)
                            remaining_days = max((end_date - today).days, 0)
                            overdue_days = max((today - end_date).days, 0) if today > end_date else 0
                        except Exception as e:
                            print(f"Error parsing end_rent_date for record {record.id}: {e}")

                    # ใช้ sudo() เพื่ออัปเดตค่าที่ต้องการ
                    record.sudo().write({
                        'rent_days_remaining': f"{rent_days}/{remaining_days}",
                        'rent_days_overdue': overdue_days
                    })

                if record.invoice_ids and all(inv.payment_state == 'paid' for inv in record.invoice_ids):
                    record.sudo().write({
                        'rental_status': 'in_rent'
                    })

                    # print("+++++++++++++++++++++record.invoice_ids", record.invoice_ids)

                    if record.pricelist_id.name == 'เรทวัน':

                        if remaining_days == 1:
                            record.rental_status = 'nearly_due'

                        if rent_days == remaining_days:
                            record.rental_status = 'in_rent'

                    if record.pricelist_id.name == 'เรทเดือน':

                        if remaining_days <= 3 and remaining_days != 0:
                            record.rental_status = 'nearly_due'

                        if rent_days == remaining_days:
                            record.rental_status = 'in_rent'

                    if remaining_days == 0:
                        # print("มาๆๆๆๆๆๆๆๆๆๆๆๆๆๆ-----------------------------------------------------")
                        record.rental_status = 'due_date'


    # @api.depends('invoice_ids', 'end_rent_date', 'origin')
    # def _compute_rental_status(self):
    #     today = fields.Date.today()
    #     for record in self:
    #         # ถ้าไม่มีใบแจ้งหนี้ (No records)
    #         if not record.invoice_ids or len(record.invoice_ids) == 0:
    #             record.rental_status = 'ready'  # ทำราคา
    #
    #         # ถ้ามีใบแจ้งหนี้อย่างน้อย 1 รายการ และตรวจสอบ end_rent_date
    #         elif len(
    #                 record.invoice_ids) >= 1 and record.end_rent_date and record.end_rent_date > today and record.check_state != 'done':
    #             record.rental_status = 'in_rent'  # อยู่ระหว่างการเช่า
    #
    #
    #         # Check if record is in rent and end_rent_date is equal to today's date
    #
    #         elif record.check_state == 'in_rent' and record.end_rent_date == today:
    #
    #              record.rental_status = 'due_date'
    #
    #         # กรณีวันสิ้นสุดการเช่าเกินวันปัจจุบัน
    #         # elif record.end_rent_date and record.end_rent_date <= today:
    #         #     record.rental_status = 'overdue'  # เกินกำหนด
    #         # elif record.rental_status == 'in_rent' and record.rent_days_overdue > 0:
    #         #     record.rental_status = 'overdue'  # เกินกำหนด
    #
    #
    #         # ใบแจ้งหนี้ถูกชำระ
    #         elif record.check_state == 'done':
    #             record.rental_status = 'done'  # ปิดบิล
    #
    #         else:
    #             record.rental_status = 'ready'  # ค่าเริ่มต้นเป็น "ทำราคา"

    @api.depends('rental_status')
    def _compute_status_flags(self):
        for record in self:
            record.is_due_date = record.rental_status == 'due_date'
            record.is_nearly_due = record.rental_status == 'nearly_due'
            record.is_overdue = record.rental_status == 'overdue'
            record.is_in_rent = record.rental_status == 'in_rent'
            record.is_ready = record.rental_status == 'ready'
            record.is_done = record.rental_status == 'done'

    @api.onchange('start_rent_date', 'end_rent_date')
    def _onchange_dates(self):
        """คำนวณ pfb_date_of_rent เมื่อระบุ start_rent_date และ end_rent_date"""
        for record in self:
            if record.start_rent_date and record.end_rent_date:
                # นับจำนวนวันโดยไม่นับวันที่สิ้นสุด (รวมวันที่เริ่มต้นเท่านั้น)
                delta = (record.end_rent_date - record.start_rent_date).days
                record.pfb_date_of_rent = delta if delta > 0 else 0
            else:
                record.pfb_date_of_rent = 0

    # @api.onchange('pricelist_id')
    # def _onchange_date_order(self):
    #     if self.partner_id:
    #         # print("self.date_order", self.partner_id)
    #         # ดึง branch_id ของผู้ใช้งานปัจจุบัน
    #         user_branch_id = self.env.user.branch_id.id
    #         # print("user_branch_id", user_branch_id)
    #         if not user_branch_id:
    #             raise UserError("ไม่สามารถระบุสาขาของผู้ใช้งานได้ กรุณาตรวจสอบข้อมูลสาขา")
    #
    #         # ค้นหา Pricelist ที่ตรงกับ branch_id ของผู้ใช้งาน
    #         pricelist = self.env['product.pricelist'].search([
    #             ('pricelist_branch_id', '=', user_branch_id)
    #         ], limit=1)
    #
    #         if pricelist:
    #             self.pricelist_id = pricelist.id  # กำหนดค่า Pricelist
    #         else:
    #             self.pricelist_id = False  # หากไม่พบ Pricelist จะเคลียร์ค่าออก
    #             raise UserError("ไม่พบ Pricelist ที่เชื่อมโยงกับสาขาของคุณ กรุณาตรวจสอบข้อมูล")

    rent_days_remaining = fields.Char(
        string="วันเช่า/เหลือ",
        compute="_compute_rent_days_remaining",
        store=True
    )

    @api.depends('pfb_date_of_rent', 'end_rent_date')
    def _compute_rent_days_remaining(self):
        for record_c in self:

            today = fields.Date.today()  # ใช้ fields.Date เพื่อความถูกต้องใน Odoo
            rent_days = record_c.pfb_date_of_rent or 0  # ดึงค่าจำนวนวันที่เช่า หากไม่มีให้เป็น 0
            remaining_days = 0  # กำหนดค่าเริ่มต้น

            # ตรวจสอบว่า end_rent_date มีค่าและอยู่ในรูปแบบที่ถูกต้อง
            if record_c.end_rent_date:
                try:
                    start_date = fields.Date.from_string(record_c.start_rent_date)
                    end_date = fields.Date.from_string(record_c.end_rent_date)
                    remaining_days = max((end_date - start_date).days, 0)
                    if record_c.rent_days_overdue >= 1:
                        remaining_days = 0

                except Exception as e:
                    remaining_days = 0

            # กำหนดค่าให้ฟิลด์ rent_days_remaining เป็นรูปแบบที่ต้องการ
            record_c.rent_days_remaining = f"{rent_days}/{remaining_days}"


    rent_days_overdue = fields.Integer(
        string="วันเกิน",
        compute="_compute_rent_days_overdue",
        store=True
    )

    cash = fields.Char(
        string="ยอดถืออยู่",
        default='',
        store=True
    )
    deposit_ref = fields.Char(string='เลขอ้างอิงเงินประกัน')
    debt_payment_type = fields.Selection([
        ('rental', 'รับชำระหนี้ค่าเช่า'),
        ('lost', 'รับชำระหนี้ค่าปรับหาย'),
        ('damaged', 'รับชำระหนี้ค่าปรับชำรุด'),
    ], string='ประเภทการรับชำระหนี้', default='', required=False)

    return_greenhome_state = fields.Selection([
        ('none', '—'),
        ('processing', 'กำลังคืนบ้านเขียว'),
        ('done', 'คืนสำเร็จ'),
        ('error', 'คืนล้มเหลว'),
    ], string='สถานะการคืนบ้านเขียว', default='none', tracking=True)


    # Odoo 18: ใช้ copy_data() แทน copy() เพราะ sale.order core เปลี่ยนแล้ว
    def copy_data(self, default=None):
        default = dict(default or {})

        # ตรวจสอบว่าเป็นการ Convert QT → SO หรือไม่
        is_convert_to_order = default.get('order_sequence', False)

        # บริษัท เอ็นพีดี โลจิสติกส์ (company_registry '5') และ เอ็นพีดี สตีลเทค ('4')
        # ไม่ใช้ฟังก์ชันสะสมเลขอ้างอิงเงินประกัน (deposit_ref) ต่อกันเมื่อกดซ้ำ
        skip_deposit_ref = self.company_id.company_registry in ('4', '5')

        # กรองเฉพาะค่าใน deposit_ref ที่ขึ้นต้นด้วย "SO"
        deposit_list = []
        if self.deposit_ref and not skip_deposit_ref:
            deposit_list = [x.strip() for x in self.deposit_ref.split(',') if x.strip().startswith('SO')]

        # เพิ่ม self.name ถ้าเป็น SO เช่นกัน
        if self.name.startswith('SO'):
            if not skip_deposit_ref:
                deposit_list.append(self.name)

            self.pfb_amount_insurance_c = self.pfb_amount_insurance
            self.pfb_amount_c = self.pfb_amount

        # สร้าง deposit_ref ใหม่ (ว่างสำหรับบริษัทที่ยกเว้น)
        default['deposit_ref'] = ",".join(deposit_list)

        # ตั้งค่าอื่นๆ
        default['start_rent_date'] = fields.Date.today()
        default['end_rent_date'] = False
        default['pfb_date_of_rent'] = 0
        default['return_greenhome_state'] = 'none'

        if is_convert_to_order:
            # Convert QT → SO: ส่งค่าอนุมัติจาก QT มาด้วย
            default['state_sale'] = self.state_sale
            default['approver_id'] = self.approver_id.id
            default['note_approver'] = self.note_approver or ''
            default['pfb_dis_amount_insurance'] = self.pfb_dis_amount_insurance
            default['pfb_required_insurance_premium'] = self.pfb_required_insurance_premium
            default['pfb_amount_insurance_c'] = self.pfb_amount_insurance
            default['pfb_amount_c'] = self.pfb_amount
        else:
            # ซ้ำรายการปกติ: เคลียร์ประวัติการอนุมัติ
            default['state_sale'] = 'draft'
            default['approver_id'] = False
            default['note_approver'] = ''
            default['cancel_summary'] = ''
            default['pfb_dis_amount_insurance'] = 0.0
            default['pfb_required_insurance_premium'] = 0.0

        return super().copy_data(default)

    def copy(self, default=None):
        """Override copy เพื่อจัดการ post-copy logic (อัปเดต rental_status)"""
        new_order = super().copy(default)

        # อัปเดต rental_status ของ SO เดิมที่ถูกอ้างอิง
        if new_order.deposit_ref:
            deposit_list = [x.strip() for x in new_order.deposit_ref.split(',') if x.strip().startswith('SO')]
            if deposit_list:
                so_orders = self.env['sale.order'].search([('name', 'in', deposit_list)])
                for so in so_orders:
                    if so.rental_status != 'done':
                        so.sudo().write({'rental_status': 'done'})
                        _logger.info("อัปเดต rental_status → 'done' ให้ %s จาก deposit_ref ของ %s", so.name, new_order.name)

        return new_order



    @api.depends('pfb_date_of_rent', 'end_rent_date')
    def _compute_rent_days_overdue(self):
        today = fields.Date.today()  # ใช้ฟังก์ชัน Odoo เพื่อความแม่นยำ
        for record in self:
            overdue_days = 0

            if record.end_rent_date:
                try:
                    end_date = fields.Date.from_string(record.end_rent_date)
                    # ตรวจสอบว่าหากวันนี้มากกว่าวันสิ้นสุด จะคำนวณ overdue
                    overdue_days = max((today - end_date).days, 0)
                except Exception as e:
                    overdue_days = 0  # ในกรณีที่เกิดปัญหาการแปลงวันที่
                    print(f"Error parsing end_rent_date for record {record.id}: {e}")

            record.rent_days_overdue = overdue_days

            # print(f"Record {record.id}: Overdue days calculated as {record.rent_days_overdue}")

    related_returns = fields.One2many(
        comodel_name='stock.picking',
        inverse_name='origin',
        string="Related Return Transfers",
        compute="_compute_related_returns",
        store=False
    )
    check_state = fields.Char(store=True)

    @api.depends('origin')
    def _compute_related_returns(self):
        for record in self:
            if not record.related_returns:
                record.related_returns = False

    #         # print(f"Checking for related documents of: {record.name}")
    #         if record.name:
    #             picking_out = self.env['stock.picking'].search([('origin', '=', record.name)])
    #             if picking_out:
    #                 # related_docs = self.env['stock.picking'].search([('origin', '=', f'Return of {picking_out.name}')])
    #                 related_docs = self.env['stock.picking'].search([
    #                     '|', '|',
    #                     ('origin', '=', f'Return of {picking_out.name}'),
    #                     ('origin', '=', f'การส่งคืนของ {picking_out.name}'),
    #                     ('origin', '=', f'Returned from {picking_out.name}')
    #                 ])
    #
    #                 if related_docs:
    #                     # ตรวจสอบสถานะเอกสารและเก็บค่าลงในฟิลด์ related_returns
    #                     record.related_returns = related_docs
    #                     for doc in related_docs:
    #                         print(f"Document: {doc.name}, State: {doc.deposit_return_state}")
    #                         if doc.deposit_return_state == 'returned':
    #                             print(f"{doc.name} is Done")
    #                             self.check_state = 'done'
    #                             self.rental_status = 'done'
    #                         else:
    #                             print(f"{doc.name} is Not Done")
    #                 else:
    #                     # print(f"No return pickings found for {record.name}")
    #                     record.related_returns = False
    #             else:
    #                 # print(f"No outbound picking found for {record.name}")
    #                 record.related_returns = False
    #         else:
    #             record.related_returns = False

    @api.depends('origin')
    def _compute_related_returns(self):
        for record in self:
            if record.name:
                picking_out = self.env['stock.picking'].search([('origin', '=', record.name)])
                picking_names = picking_out.mapped('name')  # ดึงชื่อออกมาเป็น List

                if picking_names:
                    related_docs = self.env['stock.picking'].search([
                        '|', '|',
                        ('origin', 'in', [f'Return of {name}' for name in picking_names]),
                        ('origin', 'in', [f'การส่งคืนของ {name}' for name in picking_names]),
                        ('origin', 'in', [f'Returned from {name}' for name in picking_names])
                    ])
                    # print("related_docs*********************",related_docs.name)
                    # print("related_docs*********************", related_docs.deposit_return_state)
                    if related_docs:
                        record.related_returns = related_docs
                        if any(doc.deposit_return_state == 'returned' for doc in related_docs):
                            record.check_state = 'done'
                            record.rental_status = 'done'
                    else:
                        record.related_returns = False
                else:
                    record.related_returns = False
            else:
                record.related_returns = False

        for record_c in self:
            # print("Processing record:", record_c.id)

            today = fields.Date.today()  # ใช้ fields.Date เพื่อความถูกต้องใน Odoo
            rent_days = record_c.pfb_date_of_rent or 0  # ดึงค่าจำนวนวันที่เช่า หากไม่มีให้เป็น 0
            remaining_days = 0  # กำหนดค่าเริ่มต้น

            # ตรวจสอบว่า end_rent_date มีค่าและอยู่ในรูปแบบที่ถูกต้อง
            if record_c.end_rent_date:
                try:
                    end_date = fields.Date.from_string(record_c.end_rent_date)
                    remaining_days = max((end_date - today).days, 0)  # ป้องกันค่าลบ
                except Exception as e:
                    print(f"Error parsing end_rent_date for record {record_c.id}: {e}")
                    remaining_days = 0

            # กำหนดค่าให้ฟิลด์ rent_days_remaining เป็นรูปแบบที่ต้องการ
            record_c.rent_days_remaining = f"{rent_days}/{remaining_days}"

            # print(f"Updated rent_days_remaining for record {record_c.id}: {record_c.rent_days_remaining}")

            today1 = fields.Date.today()  # ใช้ฟังก์ชัน Odoo เพื่อความแม่นยำ
            for record_r in self:
                overdue_days = 0

                if record_r.end_rent_date:
                    try:
                        end_date = fields.Date.from_string(record_r.end_rent_date)
                        # ตรวจสอบว่าหากวันนี้มากกว่าวันสิ้นสุด จะคำนวณ overdue
                        overdue_days = max((today1 - end_date).days, 0)
                    except Exception as e:
                        overdue_days = 0  # ในกรณีที่เกิดปัญหาการแปลงวันที่
                        # print(f"Error parsing end_rent_date for record {record_r.id}: {e}")

                record_r.rent_days_overdue = overdue_days

                # print(f"Record {record_r.id}: Overdue days calculated as {record_r.rent_days_overdue}")

    # @api.model
    # def search(self, args, offset=0, limit=None, order=None, count=False):
    #     # ตรวจสอบ context เพื่อป้องกันการเรียกซ้ำ
    #     if self.env.context.get('no_recursive_update'):
    #         return super(SaleOrder, self).search(args, offset, limit, order, count)
    #
    #     # ดึงชื่อเมนูจาก context
    #     menu_name = self.env.context.get('menu_name')
    #
    #
    #     # ดึง params จาก context (Odoo Web Client ใส่มา)
    #     params = self.env.context.get('params', {})
    #     view_type = params.get('view_type')  # 'list', 'form', 'kanban' ฯลฯ
    #     # print("Context params:", params)
    #     # print("view_type:", view_type)
    #
    #     if (view_type in [None, 'list']) and menu_name == 'Sales Orders Rent':
    #         # print("Executing custom function for Sales Orders Rent page")
    #         self.with_context(no_recursive_update=True)._custom_function()
    #
    #     return super(SaleOrder, self).search(args, offset, limit, order, count)
    #
    # def _custom_function(self):
    #     today = fields.Date.today()
    #     user_branch_id = self.env.user.branch_id.id
    #
    #     records = self.search([
    #         ('state', 'not in', ('draft', 'sent', 'cancel')),
    #         ('pfb_so_type', '=', 'rent'),
    #         ('name', 'like', 'SO%'),
    #         ('branch_id', '=', user_branch_id)
    #     ], limit=50)
    #
    #     for record in records:
    #         # print(f"Processing record: {record.id}")
    #         if record.rental_status == 'returned':
    #             continue  # ข้ามรายการที่คืนแล้ว
    #
    #         rent_days = record.pfb_date_of_rent or 0
    #         remaining_days = 0
    #         overdue_days = 0
    #
    #         if record.end_rent_date:
    #             try:
    #                 end_date = fields.Date.from_string(record.end_rent_date)
    #                 remaining_days = max((end_date - today).days, 0)
    #                 overdue_days = max((today - end_date).days, 0) if today > end_date else 0
    #             except Exception as e:
    #                 _logger.warning(f"Error parsing end_rent_date for record {record.id}: {e}")
    #                 continue  # ข้าม record นี้หากเกิด error
    #
    #         # ✅ อัปเดตวันคงเหลือและวันเกิน
    #         record.sudo().write({
    #             'rent_days_remaining': f"{rent_days}/{remaining_days}",
    #             'rent_days_overdue': overdue_days
    #         })
    #
    #         # ✅ เงื่อนไขสถานะเช่าที่คงไว้ตามที่คุณใช้
    #         r_status = record.rental_status  # ลดการเข้าถึง field หลายครั้ง
    #
    #         if remaining_days == 0 and r_status == 'nearly_due':
    #             record.sudo().write({'rental_status': 'overdue'})
    #
    #         if record.end_rent_date == date.today() and r_status == 'in_rent':
    #             record.sudo().write({'rental_status': 'due_date'})
    #
    #         if remaining_days == 1 and r_status == 'in_rent':
    #             record.sudo().write({'rental_status': 'nearly_due'})
    #
    #         if overdue_days > 0 and r_status == 'in_rent':
    #             record.sudo().write({'rental_status': 'overdue'})


    # def _custom_function(self):
    #     today = fields.Date.today()
    #     # print("Custom function executed when opening the Sales Orders Rent page")
    #     user_branch_id = self.env.user.branch_id.id
    #     # print("user_branch_id", user_branch_id)
    #     # ค้นหาเฉพาะรายการที่มีเงื่อนไขตามที่กำหนด
    #     # records = self.search([('name', 'like', 'SO-%')])
    #     records = self.search([
    #         ('state', 'not in', ('draft', 'sent', 'cancel')),
    #         ('pfb_so_type', '=', 'rent'),
    #         ('name', 'like', 'SO%'),
    #         # ('partner_id.name', '=', 'ห้างหุ้นส่วนจำกัด ศรัญญาก่อสร้าง')
    #         ('branch_id', '=', user_branch_id),
    #         ('rental_status', '!=', 'done')
    #         ], limit=50)
    #
    #     for record in records:
    #         print(f"Processing record: {record.id}")
    #
    #         if record.rental_status != 'returned':
    #             # print("pfb_date_of_rent", record.pfb_date_of_rent," rent_days_overdue", record.rent_days_overdue)
    #             rent_days = record.pfb_date_of_rent or 0
    #             remaining_days = 0
    #             overdue_days = 0
    #             if record.rent_days_overdue <=30:
    #                 if record.end_rent_date:
    #                     try:
    #                         end_date = fields.Date.from_string(record.end_rent_date)
    #                         remaining_days = max((end_date - today).days, 0)
    #                         overdue_days = max((today - end_date).days, 0) if today > end_date else 0
    #                     except Exception as e:
    #                         print(f"Error parsing end_rent_date for record {record.id}: {e}")
    #
    #                 # ใช้ sudo() เพื่ออัปเดตค่าที่ต้องการ
    #                 record.sudo().write({
    #                     'rent_days_remaining': f"{rent_days}/{remaining_days}",
    #                     'rent_days_overdue': overdue_days
    #                 })
    #
    #
    #                 if record.invoice_ids and all(inv.payment_state == 'paid' for inv in record.invoice_ids):
    #                     record.sudo().write({
    #                         'rental_status': 'in_rent'
    #                     })
    #
    #                     if record.pricelist_id.name == 'เรทวัน':
    #
    #                         if remaining_days == 1 :
    #
    #                             record.sudo().write({
    #                                 'rental_status': 'nearly_due'
    #                             })
    #
    #                         if rent_days == remaining_days :
    #                             record.sudo().write({
    #                                 'rental_status': 'in_rent'
    #                             })
    #
    #                     if record.pricelist_id.name == 'เรทเดือน':
    #
    #                         if remaining_days == 3 :
    #
    #                             record.sudo().write({
    #                                 'rental_status': 'nearly_due'
    #                             })
    #
    #                         if rent_days == remaining_days :
    #                             record.sudo().write({
    #                                 'rental_status': 'in_rent'
    #                             })
    #
    #                     if remaining_days == 0:
    #                         print("g-hk-----------------------------------------------------")
    #                         record.sudo().write({
    #                             'rental_status': 'due_date'
    #                         })


                # if remaining_days == 1 and record.rental_status == 'in_rent':
                #
                #     record.sudo().write({
                #         'rental_status': 'nearly_due'
                #     })
                #
                # if record.end_rent_date == date.today()  and record.rental_status == 'in_rent':
                #
                #     record.sudo().write({
                #         'rental_status': 'due_date'
                #     })
                #
                # if remaining_days == 0 and record.rental_status == 'nearly_due':
                #
                #     record.sudo().write({
                #         'rental_status': 'overdue'
                #     })
                # print("record.end_rent_date", record.end_rent_date)
                # print("due_date", date.today())
                # print(f"Updated rent_days_remaining for record {record.id}: {record.rent_days_remaining}")
                # print(f"Updated rent_days_overdue for record {record.id}: {record.rent_days_overdue}")

    def custom_function_update_overdue(self):
        today = fields.Date.today()
        # print("Custom function executed when opening the Sales Orders Rent page")
        # user_branch_id = self.env.user.branch_id.id
        # print("user_branch_id", user_branch_id)
        # ค้นหาเฉพาะรายการที่มีเงื่อนไขตามที่กำหนด
        # records = self.search([('name', 'like', 'SO-%')])
        records = self.search([
            ('state', 'not in', ('draft', 'sent', 'cancel')),
            ('pfb_so_type', '=', 'rent'),
            ('name', 'like', 'SO%'),
            # ('partner_id.name', '=', 'ห้างหุ้นส่วนจำกัด ศรัญญาก่อสร้าง')
            ('rental_status', 'not in', ('overdue', 'done'))

        ])

        for record in records:
            # print(f"Processing record: {record.id}")

            if record.rental_status != 'returned':
                # print("pfb_date_of_rent", record.pfb_date_of_rent," rent_days_overdue", record.rent_days_overdue)
                # rent_days = record.pfb_date_of_rent or 0
                remaining_days = 0
                overdue_days = 0
                if record.rent_days_overdue <= 300:
                    if record.end_rent_date:
                        try:
                            end_date = fields.Date.from_string(record.end_rent_date)
                            remaining_days = max((end_date - today).days, 0)
                            overdue_days = max((today - end_date).days, 0) if today > end_date else 0
                        except Exception as e:
                            print(f"Error parsing end_rent_date for record {record.id}: {e}")

                    # ใช้ sudo() เพื่ออัปเดตค่าที่ต้องการ
                    # record.sudo().write({
                    #     'rent_days_remaining': f"{rent_days}/{remaining_days}",
                    #     'rent_days_overdue': overdue_days
                    # })
                    # print("record.name", record.name)
                    # print("remaining_days", remaining_days)
                    # print("overdue_days", overdue_days)

                    if remaining_days == 0 and overdue_days >= 1:
                        record.sudo().write({
                            'rental_status': 'overdue'
                        })

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # product_uom_qty = fields.Float(string="Quantity", store=True )  # ไม่ให้แก้ไข
    product_uom_qty = fields.Float(string="Quantity", store=True)

    pfb_quantity = fields.Integer(string="Quantity Rent", store=True)  # บังคับให้ใส่ข้อมูล

    # discount_npd = fields.Float(string="ส่วนลดค่าเช่า", readonly=True, store=True)
    product_uom_qty_npd = fields.Float(string="Quantity NPD", store=True)

    pfb_quantity_readonly = fields.Boolean(compute="_compute_field_access", store=True)
    product_uom_qty_readonly = fields.Boolean(compute="_compute_field_access", store=True)

    @api.depends("order_id.pfb_so_type")
    def _compute_field_access(self):
        for line in self:
            if line.order_id:
                print(f"🔍 Sale Type from Order: {line.order_id.pfb_so_type}")

                if line.order_id.pfb_so_type == 'rent':
                    line.pfb_quantity_readonly = False  #  สามารถแก้ไขได้
                    line.product_uom_qty_readonly = True  #  ห้ามแก้ไข
                    print("✅ Rental Order: pfb_quantity = Editable, product_uom_qty = Readonly")
                    # 🚨 ตรวจสอบ Pricelist Name
                    if line.order_id.pricelist_id.name == "Public Pricelist":
                        raise UserError("❌ คุณยังไม่เลือก รายการราคา 'เรทวัน' หรือ 'เรทเดือน'")


                elif line.order_id.pfb_so_type == 'sale':
                     line.pfb_quantity_readonly = True  #  ห้ามแก้ไข
                     line.product_uom_qty_readonly = False  #  สามารถแก้ไขได้
                     print("✅ Sales Order: pfb_quantity = Readonly, product_uom_qty = Editable")

                else:
                    line.pfb_quantity_readonly = False
                    line.product_uom_qty_readonly = False
                    print(" No Sale Type Selected")

    @api.constrains('pfb_quantity')
    def _check_pfb_quantity(self):
        for record in self:
            if record.order_id.pfb_so_type == 'rent':
                if record.pfb_quantity <= 0:
                    raise ValidationError("กรุณาระบุ Quantity Rent ที่มากกว่า 0")

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.order_id and not self.order_id.pricelist_id:
            raise UserError("กรุณาเลือก Pricelist(รายการราคา) ใน Sale Order ก่อนเลือกสินค้า!")
