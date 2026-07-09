from . import sale_order
from . import stock_confirm_wizard
from . import stock_confirm_line
# หมายเหตุ Odoo 18:
#  - ตัด stock_quant override ออก — core ของ Odoo 18 ทำ max(0, reserved+delta)
#    ใน _update_available_quantity อยู่แล้ว จึงไม่เกิด error "unreserve เกินสต๊อก"
#  - ตัด res_users (สิทธิ์คืนบ้านเขียว) ออก — เลิกใช้การเชื่อมต่อ MySQL/บ้านเขียวแล้ว
