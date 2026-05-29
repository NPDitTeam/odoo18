# © 2017 Ecosoft (ecosoft.co.th).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError, ValidationError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    order_sequence = fields.Boolean(string="Order Sequence", readonly=True, index=True)
    quote_id = fields.Many2one(
        comodel_name="sale.order",
        string="Quotation",
        readonly=True,
        ondelete="restrict",
        copy=False,
        help="For Sales Order, this field references to its Quotation",
    )
    order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Order",
        readonly=True,
        ondelete="restrict",
        copy=False,
        help="For Quotation, this field references to its Sales Order",
    )
    quotation_state = fields.Selection(
        string="Quotation Status",
        readonly=True,
        related="state",
        help="Only relative quotation states",
    )

    # เพิ่มสถานะใหม่
    # ฟิลด์ใหม่สำหรับสถานะ
    state_sale = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('waiting_to_approve', 'Waiting To Approve'),
            ('approved', 'Approved'),
            ('reject', 'Reject'),
        ],
        string="สถานะการตรวจสอบ",
        default='draft',  # ค่าเริ่มต้น
        readonly=True,  # ล็อกไม่ให้แก้ไข
    )

    approver_id = fields.Many2one('res.users', string="Approver", readonly=True)
    # เพิ่มฟิลด์สำหรับการควบคุมการแสดงปุ่ม Approve
    button_visible = fields.Boolean(
        compute='_compute_button_visible',
        store=False  # ไม่ต้องบันทึกลงฐานข้อมูล
    )

    button_convert_visible_send = fields.Boolean(
        compute='_compute_button_convert_visible_send',
        string='Show Convert Button'
    )

    button_convert_visible_send_r = fields.Boolean(
        string='แสดงปุ่มส่วนลดค่าเช่า',
        compute='_compute_button_convert_visible_send_r'

    )

    button_convert_visible = fields.Boolean(
        compute='_compute_button_convert_visible',
        string='Show Convert Button'
    )

    button_visible_reject = fields.Boolean(
        compute='_compute_button_visible_reject',
        string='Show Convert Button'
    )

    pfb_amount_insurance = fields.Float('ค่าประกันสินค้า', digits=0)
    pfb_dis_amount_insurance = fields.Float('ส่วนลดประกันสินค้า', digits=0)
    discount_amt_line = fields.Monetary(string='- Line Discount')

    c_date = fields.Datetime(string="วันที่สั่งซื้อย้อนหลัง")

    @api.depends( "order_line.discount_amount", "discount_amt_line", "pfb_dis_amount_insurance", "pfb_dis_amount_insurance","quotation_state")
    def _compute_button_convert_visible(self):
        for rec in self:
            rec.button_convert_visible = True  # Default value to ensure assignment

            if rec.pfb_amount_insurance >0 and rec.pfb_dis_amount_insurance >0:

                if (rec.pfb_amount > rec.pfb_insurance_min  or rec.pfb_amount == rec.pfb_insurance_min)  and (rec.state == 'draft' or rec.state_sale == 'approved'):
                    rec.button_convert_visible = True

                elif (rec.pfb_amount < rec.pfb_insurance_min and rec.state_sale == 'approved') or rec.state_sale == 'approved' or rec.quotation_state == 'cancel' :
                    rec.button_convert_visible = True

                elif (rec.pfb_amount < rec.pfb_insurance_min and rec.state == 'draft') or rec.state_sale == 'approved' or rec.quotation_state == 'cancel' or rec.state_sale == 'reject' :
                    rec.button_convert_visible = False


            #
            # if rec.discount_amt_line or rec.total_rental_discount:
            #     max_discount = rec.amount_price_subtotal_without_discount * 0.5
            #     if rec.discount_amt_line > max_discount and rec.state_sale in ['draft', 'waiting_to_approve']:
            #         rec.button_convert_visible = False
            #     elif rec.discount_amt_line > max_discount and rec.state_sale == 'approved':
            #         rec.button_convert_visible = True
            #
            #     elif rec.total_rental_discount > max_discount and rec.state_sale in ['draft', 'waiting_to_approve']:
            #         rec.button_convert_visible = False
            #
            #     elif rec.total_rental_discount > max_discount and rec.state_sale == 'approved':
            #         rec.button_convert_visible = True
            #     else:
            #         rec.button_convert_visible = True  # Default assignment

            for line in rec.order_line:
                if line.discount_amount:
                    max_discount = line.price_subtotal_without_discount * 0.5  # 50% ของยอดรวมรายการสินค้า

                    if rec.state_sale == 'draft' or rec.state_sale == 'waiting_to_approve'or rec.state_sale == 'reject':
                        if line.discount_amount > max_discount:
                            rec.button_convert_visible = False

                    elif rec.state_sale == 'approved':
                        if line.discount_amount > max_discount:
                            rec.button_convert_visible = True

    @api.onchange("order_line.discount_amount", "discount_amt_line", "pfb_dis_amount_insurance", "quotation_state", "state_sale")
    def _compute_button_convert_visible_send_r(self):
        for order in self:
            # Default: always assign a value
            order.button_convert_visible_send_r = False

            current_db = self.env.cr.dbname

            if current_db in ['test_2025_01', 'TEST_New', 'test', 'NPD_S_Group_New_V2', 'NPD_S_Group_New',
                              'NPD_Bangkok_New', 'NPD_Intertrading_New', 'NPD_Intertrading_New_NonVat',
                              'NPD_Logistics_demo']:
                visible = bool(getattr(order, 'total_rental_discount', 0))
                for line in order.order_line:
                    if (
                        getattr(line, 'discount_amount', 0)
                        and getattr(line, 'discount_type_selection', '') == 'rental'
                        and order.state == 'sale'
                        and getattr(line, 'discount_method', '') == 'fix'
                    ):
                        if order.approver_id.id == self.env.uid and order.state_sale in ['waiting_to_approve', 'reject']:
                            visible = False
                        if order.approver_id.id == self.env.uid and order.state_sale == 'approved':
                            visible = True
                order.button_convert_visible_send_r = visible

    # @api.onchange("order_line.discount_amount","order_line.discount_method", "discount_amt_line", "pfb_dis_amount_insurance", "quotation_state")
    # def _compute_button_convert_visible_send_r(self):
    #     for rec in self:
    #         rec.button_convert_visible_send_r = False
    #         for line in rec.order_line:
    #             if line.discount_amount and line.discount_type_selection == 'rental':
    #                 total_difference = 0
    #                 total_rent = 0
    #
    #                 if (rec.state == 'sale' and line.discount_method == 'fix'):
    #
    #                     # ✅ ตรวจสอบสิทธิ์และสถานะ
    #                     if rec.approver_id.id == self.env.uid and rec.state_sale in ['waiting_to_approve',
    #                                                                                  'reject']:
    #                         rec.button_convert_visible_send_r = False

                    # ดึง stock ที่เกี่ยวข้อง
                    # stock_pickings = self.env['stock.picking'].sudo().search([
                    #     ('group_id.name', '=', rec.name),
                    #     ('state', '=', 'done'),
                    #     ('name', 'ilike', '%IN%'),
                    #     ('start_x_date', '!=', False),
                    #     ('end_x_date', '!=', False),
                    # ])
                    #
                    # for stock in stock_pickings:
                    #     days_used = (
                    #         1 if stock.force_date.date() == stock.start_x_date
                    #         else (stock.force_date.date() - stock.start_x_date).days
                    #     )
                    #
                    #     rental_days = (
                    #         1 if stock.end_x_date == stock.start_x_date else (
                    #                 stock.end_x_date - stock.start_x_date).days
                    #     )
                    #
                    #     rental_per_day = rec.amount_total / rental_days
                    #     total_rent += rental_per_day * days_used
                    #
                    # if stock_pickings:
                    #     total_difference = total_rent - rec.amount_total
                    #     max_discount1 = total_difference * 0.3  # ❗ ค่าตัวอย่าง

                        # 🧠 ถ้าสถานะเป็น sale และ discount_method เป็น fix เท่านั้น จึงกำหนดค่า default
                        # if rec.state == 'sale' and line.discount_method == 'fix':
                        #     # ✅ กรณียังไม่กรอก ให้ช่วยกรอก
                        #     if not line.discount_amount or line.discount_amount <= 0:
                        #         line.discount_amount = max_discount1

                        # ✅ ตรวจสอบว่าเกินหรือไม่
                        # if (line.discount_amount > max_discount1 and rec.state == 'sale' and line.discount_method == 'fix'):
                        #
                        #
                        #     # ✅ ตรวจสอบสิทธิ์และสถานะ
                        #     if rec.approver_id.id == self.env.uid and rec.state_sale in ['waiting_to_approve',
                        #                                                                  'reject']:
                        #         rec.button_convert_visible_send_r = False
                            # if rec.state_sale == 'approved':
                            #     rec.button_convert_visible_send_r = True

                    #         # ✅ แสดงคำเตือน
                    #         warning_result = self.check_discount_warning(max_discount1)
                    #         if warning_result:
                    #             return warning_result
                    #
                    #     else:
                    #         rec.button_convert_visible_send_r = False
                    #
                    # else:
                    #     raise UserError(_("ไม่พบข้อมูล หรือกรอกข้อมูลไม่ครบในหน้าคืนของ โปรดตรวจสอบข้อมูลอีกครั้ง"))

    # def check_discount_warning(self, max_discount1):
    #     self.ensure_one()
    #     return {
    #         'warning': {
    #             'title': _("แจ้งเตือน!"),
    #             'message': _(
    #                 "ส่วนลดไม่สามารถเกิน 30% ของยอดรวมสินค้าได้ (สูงสุด {:.2f} บาท)."
    #                 "\nโปรดส่งคำขออนุมัติจากผู้จัดการ.").format(max_discount1),
    #         }
    #     }

    @api.depends( "order_line.discount_amount", "discount_amt_line", "pfb_dis_amount_insurance")
    def _compute_button_convert_visible_send(self):
        for rec in self:
            # Set default value
            rec.button_convert_visible_send = False

            # Condition 1: Based on `pfb_amount_insurance`
            # แสดงปุ่มเมื่อค่าประกันสุทธิ < เกณฑ์ขั้นต่ำ (ไม่ต้องเช็ค pfb_dis_amount_insurance > 0)
            if rec.pfb_amount_insurance > 0 and rec.pfb_insurance_min > 0:
                if rec.pfb_amount < rec.pfb_insurance_min and rec.state_sale in ['draft', 'reject']:
                    rec.button_convert_visible_send = True
            if rec.c_date:
                self.date_order = rec.c_date


            # Condition 2: Based on `discount_amt_line`

            for line in rec.order_line:
                if line.discount_amount and line.discount_type_selection == 'product':

                    max_discount = line.price_subtotal_without_discount * 0.5  # 50% ของยอดรวมรายการสินค้า

                    if rec.state_sale == 'draft' or rec.state_sale == 'reject':
                        if line.discount_amount > max_discount:
                            rec.button_convert_visible_send = True





            # elif rec.discount_amt_line or rec.total_rental_discount:
            #     max_discount = rec.amount_price_subtotal_without_discount * 0.5
            #     if rec.discount_amt_line > max_discount and rec.state_sale in ['draft', 'reject']:
            #         rec.button_convert_visible_send = True
            #         print("discount_amt_line", rec.discount_amt_line)
            #
            #         print("max_discount", max_discount)
            #
            #     if rec.total_rental_discount > max_discount and rec.state_sale in ['draft', 'reject']:
            #         rec.button_convert_visible_send = True
            #         print("total_rental_discount", rec.total_rental_discount)



    def _compute_button_visible(self):
        for rec in self:
            # เงื่อนไข: แสดงปุ่มเมื่อ approver_id ตรงกับ user ปัจจุบัน
            if rec.approver_id.id == self.env.uid and rec.state_sale == 'waiting_to_approve':
                rec.button_visible = True
            else:
                rec.button_visible = False

    def _compute_button_visible_reject(self):
        for rec in self:
            # เงื่อนไข: แสดงปุ่มเมื่อ approver_id ตรงกับ user ปัจจุบัน
            if rec.approver_id.id != '' and rec.state_sale == 'waiting_to_approve':
                rec.button_visible_reject = True
            else:
                rec.button_visible_reject = False


    def action_waiting_to_approve(self):
        """เปิด Popup สำหรับเลือก Approver"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Select Approver'),
            'res_model': 'sale.order.approval.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_order_id': self.id,
            },
        }

    def action_waiting_to_approve_r(self):
        """เปิด Popup สำหรับเลือก Approver"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Select Approver'),
            'res_model': 'sale.order.approval.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_order_id': self.id,
            },
        }
    def action_open_approval_popup(self):
        """เปิด popup สำหรับการอนุมัติคำสั่งขาย"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Approve Sale Order'),
            'res_model': 'sale.order.approval.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('pfb_npd_all_customs.view_sale_order_approve_wizard_form_v2').id,  # ระบุ view ใหม่
            'target': 'new',
            'context': {
                'default_sale_order_id': self.id,
                'default_note': self.note,
                'default_approver_id': self.approver_id.id,
            },
        }

    def action_approve(self):
        """Logic for Sale Order approval"""
        if not self.approver_id:
            raise UserError(_('No approver selected!'))
        self.write({'state_sale': 'approved'})

        return True

    # def action_approve(self):
    #     if not self.approver_id:
    #         raise UserError(_('No approver selected!'))
    #     self.write({'state_sale': 'approved'})

    def action_reject(self):
        if not self.approver_id:
            raise UserError(_('No reject selected!'))
        self.write({'state_sale': 'reject'})

        # ฟังก์ชันตรวจสอบเงื่อนไขการแสดงปุ่ม

    @api.model
    def create(self, vals):
        order_sequence = vals.get("order_sequence") or self.env.context.get(
            "order_sequence"
        )
        if not order_sequence and vals.get("name", "/") == "/":
            vals["name"] = self.env["ir.sequence"].next_by_code("sale.quotation") or "/"
        return super().create(vals)

    def _prepare_order_from_quotation(self):
        return {
            "name": self.env["ir.sequence"].next_by_code("sale.order") or "/",
            "order_sequence": True,
            "quote_id": self.id,
            "client_order_ref": self.client_order_ref,
        }

    def action_convert_to_order(self):
        self.ensure_one()
        if self.order_sequence:
            raise UserError(_("Only quotation can convert to order"))
        order = self.copy(self._prepare_order_from_quotation())
        self.order_id = order.id  # Reference from this quotation to order
        if self.state == "draft":
            self._action_cancel()
        return self.open_duplicated_sale_order()

    @api.model
    def open_duplicated_sale_order(self):
        return {
            "name": _("Sales Order"),
            "view_mode": "form",
            "view_id": False,
            "res_model": "sale.order",
            "context": {"default_order_sequence": True, "order_sequence": True},
            "type": "ir.actions.act_window",
            "nodestroy": True,
            "target": "current",
            "domain": "[('order_sequence', '=', True)]",
            "res_id": self.order_id and self.order_id.id or False,
        }


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"
    discount_amount = fields.Float('Discount Amount')
