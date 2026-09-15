# -*- coding: utf-8 -*-
"""ตัวเชื่อม Gemini สำหรับ "ตัวช่วย AI-IT"

ใช้ API key ตัวเดียวกับโมดูล AI เดิมของ NPD (advance_clear_ai_check)
เพื่อไม่ต้องตั้งค่า key ซ้ำอีกที่

ขอบเขตงานของ AI ในโมดูลนี้ = "อ่านข้อความพนักงานให้เป็นข้อมูลที่มีโครงสร้าง"
เท่านั้น (เลขเอกสาร / จำนวนสต๊อกจริงของสินค้าแต่ละตัว)
AI ไม่ได้เขียน SQL และไม่ได้ตัดสินใจว่าจะแก้ฐานข้อมูลอะไร — SQL ทั้งหมด
เขียนไว้ล่วงหน้าแล้วใน ai_it_stock_fix.py
"""
import json
import logging

import requests

from odoo import api, models

_logger = logging.getLogger(__name__)

GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)
# ใช้ key ร่วมกับโมดูล AI เดิม (advance_clear_ai_check / npd_doc_number / payment_slip_date_ai)
GEMINI_API_KEY_PARAM = 'advance_clear_ai_check.gemini_api_key'
GEMINI_TIMEOUT = 20  # วินาที — สั้น เพราะทำงานคาอยู่ในจังหวะที่พนักงานกดส่งข้อความ


class NpdAiItGemini(models.AbstractModel):
    _name = 'npd.ai.it.gemini'
    _description = 'ตัวช่วย AI-IT : ตัวเชื่อม Gemini'

    @api.model
    def _get_api_key(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            GEMINI_API_KEY_PARAM, default='',
        ) or ''

    @api.model
    def is_available(self):
        """มี key พร้อมใช้งานหรือไม่ (ถ้าไม่มี ระบบจะ fallback ไปใช้การอ่านด้วย regex)"""
        return bool(self._get_api_key())

    @api.model
    def extract_json(self, prompt, max_output_tokens=1024):
        """ยิง Gemini แล้วคืนผลเป็น dict

        คืน {} เมื่อเรียกไม่สำเร็จ — ตั้งใจให้ "ไม่ raise" เพราะฟังก์ชันนี้ถูก
        เรียกระหว่างที่พนักงานส่งข้อความในแชท ถ้าโยน error ข้อความของพนักงาน
        จะถูก rollback หายไปทั้งข้อความ ผู้เรียกต้องมีทางสำรอง (regex) เสมอ
        """
        api_key = self._get_api_key()
        if not api_key:
            _logger.info('ตัวช่วย AI-IT: ยังไม่ได้ตั้งค่า %s — ใช้การอ่านข้อความแบบ regex แทน',
                         GEMINI_API_KEY_PARAM)
            return {}

        payload = {
            'contents': [{'parts': [{'text': prompt}]}],
            'generationConfig': {
                'temperature': 0,
                'maxOutputTokens': max_output_tokens,
                'responseMimeType': 'application/json',
                # ปิดโหมด thinking: งานนี้เป็นการสกัดค่าสั้น ๆ ถ้าเปิดไว้
                # token จะถูกใช้ไปกับการคิดจนไม่เหลือข้อความตอบกลับ
                'thinkingConfig': {'thinkingBudget': 0},
            },
        }
        try:
            response = requests.post(
                '%s?key=%s' % (GEMINI_API_URL, api_key),
                headers={'content-type': 'application/json'},
                json=payload,
                timeout=GEMINI_TIMEOUT,
            )
            response.raise_for_status()
            result = response.json()
        except Exception as exc:  # noqa: BLE001 - ต้องไม่ทำให้แชทพัง
            _logger.warning('ตัวช่วย AI-IT: เรียก Gemini ไม่สำเร็จ (%s)', exc)
            return {}

        block_reason = (result.get('promptFeedback') or {}).get('blockReason')
        if block_reason:
            _logger.warning('ตัวช่วย AI-IT: Gemini บล็อก prompt (%s)', block_reason)
            return {}

        candidates = result.get('candidates') or []
        if not candidates:
            return {}

        parts = (candidates[0].get('content') or {}).get('parts') or []
        text = ''.join(p.get('text', '') for p in parts if not p.get('thought')).strip()
        if not text:
            return {}

        return self._loads(text)

    @api.model
    def _loads(self, text):
        """แปลงข้อความเป็น dict แบบยืดหยุ่น (เผื่อโมเดลห่อด้วย ```json ... ```)"""
        text = text.strip()
        if text.startswith('```'):
            text = text.strip('`')
            if text.lower().startswith('json'):
                text = text[4:]
            text = text.strip()
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            start, end = text.find('{'), text.rfind('}')
            if start == -1 or end <= start:
                _logger.warning('ตัวช่วย AI-IT: อ่านคำตอบ Gemini เป็น JSON ไม่ได้: %s', text[:200])
                return {}
            try:
                data = json.loads(text[start:end + 1])
            except (ValueError, TypeError):
                _logger.warning('ตัวช่วย AI-IT: อ่านคำตอบ Gemini เป็น JSON ไม่ได้: %s', text[:200])
                return {}
        return data if isinstance(data, dict) else {}
