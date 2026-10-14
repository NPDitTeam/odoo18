from odoo import _, models
from odoo.exceptions import UserError

# เลขที่ยังไม่ได้ออกจริง (ค่าเริ่มต้นของแต่ละเอกสารก่อนยืนยัน)
UNNUMBERED = (False, '', '/', 'New', 'new', 'Draft')


def _npd_block_numbered_unlink(records, number_field, label):
    """เอกสารที่ได้เลขแล้วห้ามลบ ไม่ว่าสถานะไหน (ร่างที่ถูกรีเซต / ยกเลิกแล้ว)

    ลบ = เลขนั้นหายไปจากระบบ เลขรันขาดช่วงตรวจย้อนไม่ได้ ให้ "ยกเลิก" แทน
    เอกสารยังอยู่พร้อมเลขเดิมในสถานะยกเลิก
    งานระบบที่จำเป็นต้องลบจริงส่ง context npd_allow_unlink=True
    """
    if records.env.context.get('npd_allow_unlink'):
        return
    for rec in records:
        number = rec[number_field]
        if number not in UNNUMBERED:
            raise UserError(_(
                'ลบ%(label)s %(number)s ไม่ได้ เพราะเอกสารนี้ได้เลขไปแล้ว\n'
                'ถ้าลบ เลขนี้จะหายไปจากระบบ เลขรันจะขาดช่วง\n'
                'ถ้าไม่ใช้เอกสารนี้แล้ว ให้กด "ยกเลิก" แทน เอกสารจะยังอยู่พร้อมเลขเดิม',
                label=label, number=number))


class AccountMove(models.Model):
    _inherit = 'account.move'

    def unlink(self):
        if not self.env.context.get('npd_allow_unlink'):
            for move in self:
                # เคยลงรายการแล้ว = ได้เลขแล้ว (ตัวรันเลขเก็บเลขเดิมไว้แม้รีเซตเป็นร่าง/ยกเลิก)
                numbered = move.posted_before or (
                    getattr(move, 'sequence_generated', False) and move.name not in UNNUMBERED)
                if numbered:
                    raise UserError(_(
                        'ลบรายการบัญชี %(name)s ไม่ได้ เพราะเคยลงรายการและได้เลขไปแล้ว\n'
                        'ถ้าลบ เลขนี้จะหายไปจากระบบ เลขรันจะขาดช่วง\n'
                        'ถ้าไม่ใช้แล้ว ให้กด "ยกเลิก" แทน เอกสารจะยังอยู่พร้อมเลขเดิม',
                        name=move.name))
        return super().unlink()


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def unlink(self):
        _npd_block_numbered_unlink(self, 'name', _('ใบรับ/จ่ายชำระ'))
        return super().unlink()


class AccountVoucher(models.Model):
    _inherit = 'account.voucher'

    def unlink(self):
        _npd_block_numbered_unlink(self, 'number', _('ใบสำคัญ'))
        return super().unlink()


class AccountAdvance(models.Model):
    _inherit = 'account.advance'

    def unlink(self):
        _npd_block_numbered_unlink(self, 'name', _('ใบเบิกเงินทดรอง'))
        return super().unlink()

    def cancel(self):
        """ยกเลิกเงินทดรองด้วยการกลับรายการ (เดิมรีเซตแล้วลบรายการบัญชีทิ้ง เลข JV ข้าม)"""
        for advance in self:
            if advance.move_id:
                advance.move_id._npd_cancel_by_reverse(_('ยกเลิกเงินทดรอง %s') % (advance.name or ''))
            advance.state = 'cancel'
        return True


class AccountAdvanceClear(models.Model):
    _inherit = 'account.advance.clear'

    def unlink(self):
        _npd_block_numbered_unlink(self, 'name', _('Advance Clear'))
        return super().unlink()


class AccountAdvanceRequest(models.Model):
    _inherit = 'account.advance.request'

    def unlink(self):
        _npd_block_numbered_unlink(self, 'name', _('ใบขอเบิกเงินทดรอง'))
        return super().unlink()


class CashPayment(models.Model):
    _inherit = 'cash.payment'

    def unlink(self):
        _npd_block_numbered_unlink(self, 'name', _('รับชำระเงินสด'))
        return super().unlink()


class RefundPayment(models.Model):
    _inherit = 'refund.payment'

    def unlink(self):
        _npd_block_numbered_unlink(self, 'name', _('โอนคืนเงินลูกค้า'))
        return super().unlink()
