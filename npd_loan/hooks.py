# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID
import logging

_logger = logging.getLogger(__name__)


def recalculate_carried_interest(cr, registry):
    """คำนวณดอกค้างยกมา/ส่งต่อ สำหรับงวดเก่าที่มีอยู่แล้ว"""
    env = api.Environment(cr, SUPERUSER_ID, {})
    loans = env['npd.loan'].search([('installment_ids', '!=', False)])
    _logger.info('Recalculating carried interest for %s loans...', len(loans))
    
    for loan in loans:
        installments = loan.installment_ids.sorted('installment_no')
        if not installments:
            continue
        
        rate = (loan.interest_rate / 100) if loan.interest_rate else 0
        carry = 0
        prev_remaining = loan.loan_amount
        
        for inst in installments:
            inst.with_context(skip_propagate=True).write({
                'previous_remaining': prev_remaining,
                'carried_interest': carry,
            })
            carry = inst.carry_forward_interest or 0
            prev_remaining = inst.remaining_principal or prev_remaining
        
        _logger.info('  Loan %s: %s installments recalculated', loan.name, len(installments))
    
    _logger.info('Carried interest recalculation done.')


def cleanup_old_views(cr, registry):
    """ลบ view เก่าที่มี field ที่ไม่มีอยู่แล้ว"""
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    # ค้นหาและลบ view ที่มี expected_interest
    try:
        cr.execute("""
            DELETE FROM ir_ui_view 
            WHERE arch_db LIKE '%expected_interest%'
            RETURNING id, name
        """)
        deleted = cr.fetchall()
        if deleted:
            for view_id, view_name in deleted:
                _logger.info(f"Deleted old view: {view_name} (ID: {view_id})")
        cr.commit()
    except Exception as e:
        _logger.warning(f"Could not cleanup views: {e}")
    
    # ลบ field ที่ไม่มีอยู่แล้ว
    try:
        cr.execute("""
            DELETE FROM ir_model_fields 
            WHERE model = 'npd.loan' 
            AND name IN ('expected_interest', 'payment_proof', 'payment_proof_name')
            RETURNING id, name
        """)
        deleted_fields = cr.fetchall()
        if deleted_fields:
            for field_id, field_name in deleted_fields:
                _logger.info(f"Deleted old field: {field_name} (ID: {field_id})")
        cr.commit()
    except Exception as e:
        _logger.warning(f"Could not cleanup fields: {e}")
