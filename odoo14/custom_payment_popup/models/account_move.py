from odoo import models, _


class AccountMove(models.Model):
    _inherit = 'account.move'

    def use_wht_billing_sheet_invoice(self):
        """ใบสั่งขายต้นทางติ๊ก 'ใช้ภาษีหัก ณ ที่จ่ายใบแจ้งหนี้/ใบวางบิล หัก 5%' ไหม (เหมือน o14)
        ไม่มีฟิลด์ / ไม่ได้ออกจากใบสั่งขาย = ไม่ติ๊ก, รวมหลายใบสั่งขาย ติ๊กใบใดใบหนึ่ง = หัก 5%"""
        return any(getattr(order, 'use_wht_billing_sheet', False)
                   for order in self.line_ids.sale_line_ids.order_id)

    def _npd_rent_days(self):
        """จำนวนวันเช่าสำหรับหน้ารับชำระ: ของใบแจ้งหนี้ก่อน ไม่มีค่อยใช้ของใบสั่งขาย"""
        days = getattr(self, 'pfb_date_of_rent', 0) or 0
        if not days:
            days = max([getattr(o, 'pfb_date_of_rent', 0) or 0
                        for o in self.line_ids.sale_line_ids.order_id] or [0])
        return days

    def action_open_payment_form(self):
        """Open payment form pre-filled from invoice + auto search invoice"""
        self.ensure_one()

        # หาสมุดรายวันฝั่งรับชำระ สามชั้นตามลำดับ
        # 1) กฎที่ตั้งเองได้ไม่จำกัด (เมนู กฎสมุดรายวันรับชำระ)
        journal = self.env['npd.payment.journal.rule']._resolve(
            self.company_id, self.journal_id,
        )
        # 2) ค่าเดิมที่ผูกกับกรณีการออกใบแจ้งหนี้ 8 กรณี
        #    (เมนู การขาย > การกำหนดค่า > สมุดรายวันออกใบแจ้งหนี้)
        if not journal:
            journal = self.env['npd.invoice.journal.config']._get_payment_journal(
                self.company_id, self.journal_id,
            )

        if not journal:
            # ต้องล็อกบริษัทด้วย ไม่งั้นจะคว้าสมุดรายวันธนาคารของบริษัทอื่น
            # เวลาผู้ใช้เปิดหลายบริษัทพร้อมกัน
            journal = self.env['account.journal'].search([
                ('type', '=', 'bank'),
                ('company_id', '=', self.company_id.id),
            ], limit=1)

        # Determine payment type
        if self.move_type in ('out_invoice', 'in_refund'):
            payment_type = 'inbound'
            partner_type = 'customer'
        else:
            payment_type = 'outbound'
            partner_type = 'supplier'

        # ตั้งค่าเริ่มต้นตามการติ๊กภาษีหัก ณ ที่จ่ายบนใบสั่งขาย เหมือน o14
        #   ติ๊ก = ใบวางบิลหัก 5% ให้แล้ว -> หมายเหตุ "โอนเงินแบบหัก 5%" และติ๊ก Payment Multi ให้
        #   ไม่ติ๊ก = ยอดเต็ม -> หมายเหตุ "โอนเงินแบบหัก 7%"
        wht_5_percent = self.use_wht_billing_sheet_invoice()
        ctx = {
            'default_note': 'โอนเงินแบบหัก 5%' if wht_5_percent else 'โอนเงินแบบหัก 7%',
            'default_is_payment_multi': wht_5_percent,
            'default_pfb_date_of_rent': self._npd_rent_days(),
            'default_partner_id': self.partner_id.id,
            'default_date': self.invoice_date or False,
            'default_ref': self.name,
            'default_search_invoice_name': self.name,
            'default_payment_type': payment_type,
            'default_partner_type': partner_type,
            'default_currency_id': self.currency_id.id,
        }
        if journal:
            ctx['default_journal_id'] = journal.id

        return {
            'type': 'ir.actions.act_window',
            'name': _('ชำระเงิน'),
            'res_model': 'account.payment',
            'view_mode': 'form',
            'target': 'current',
            'context': ctx,
        }
