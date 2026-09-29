# -*- coding: utf-8 -*-
"""แกลเลอรีรูปแบบ HTML — กดแล้วเห็นรูปอย่างเดียว

เคยลองใช้ kanban ฝังในฟิลด์ x2many แต่ Odoo ดักคลิกบนการ์ดไว้เปิดฟอร์มของ
ir.attachment (หน้าที่มีชื่อไฟล์ ประเภท Mime ฯลฯ) ซึ่งไม่ใช่สิ่งที่คนดูงาน
ต้องการเลย และปิดพฤติกรรมนั้นจากฝั่ง XML ไม่ได้ตรง ๆ

วาดเป็น HTML เองจึงคุมได้ว่าคลิกแล้วไปไหน — เปิด URL ของรูปตรง ๆ
ได้รูปเต็มอย่างเดียว ไม่มีฟอร์มมาคั่น
"""
from odoo import api, fields, models
from odoo.tools import html_escape


def _render_gallery(attachments, thumb_height):
    """สร้าง HTML รูปเรียงกัน กดแล้วเปิดรูปเต็มในแท็บใหม่"""
    if not attachments:
        return False
    parts = [
        '<div style="display:flex;flex-wrap:wrap;gap:8px;align-items:flex-start;">'
    ]
    for att in attachments:
        url = '/web/image/ir.attachment/%d/datas' % att.id
        parts.append(
            '<a href="%s" target="_blank" title="กดเพื่อดูรูปเต็ม">'
            '<img src="%s" alt="%s" '
            'style="height:%s;border-radius:6px;border:1px solid #dee2e6;'
            'object-fit:cover;cursor:zoom-in;"/></a>'
            % (url, url, html_escape(att.name or ''), thumb_height)
        )
    parts.append('</div>')
    return ''.join(parts)


class VehicleBookingPhotoGallery(models.Model):
    _inherit = 'vehicle.booking'

    start_check_photo_html = fields.Html(
        string='รูปก่อนขนส่ง', compute='_compute_photo_gallery_html',
        sanitize=False)
    delivery_photo_html = fields.Html(
        string='รูปหลักฐานการส่ง', compute='_compute_photo_gallery_html',
        sanitize=False)

    @api.depends('start_check_photo_ids', 'delivery_photo_ids')
    def _compute_photo_gallery_html(self):
        for record in self:
            record.start_check_photo_html = _render_gallery(
                record.start_check_photo_ids, '200px')
            record.delivery_photo_html = _render_gallery(
                record.delivery_photo_ids, '200px')
