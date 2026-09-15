import base64
import json
import logging
import re
import requests
from datetime import datetime
from difflib import SequenceMatcher

from odoo import fields, models, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"


class AccountPaymentSlipDate(models.Model):
    _inherit = 'account.payment'

    slip_date_extracted = fields.Char(
        string='วันที่จากสลิป (AI)',
        readonly=True,
        copy=False,
        help='วันที่ที่ AI อ่านได้จากสลิปการโอนเงิน',
    )

    slip_date_checked = fields.Boolean(
        string='ตรวจสอบวันที่จากสลิปแล้ว',
        default=False,
        readonly=True,
        copy=False,
        help='ต้องกดปุ่ม "ใช้วันที่จากสลิป" ก่อน จึงจะยืนยันเอกสารได้',
    )

    def _get_gemini_api_key(self):
        """Get Gemini API key from system parameters (shared with advance_clear_ai_check)."""
        api_key = self.env['ir.config_parameter'].sudo().get_param(
            'advance_clear_ai_check.gemini_api_key', default=''
        )
        if not api_key:
            raise UserError(_(
                "Gemini API Key is not configured.\n"
                "Please set it in Settings > Technical > System Parameters\n"
                "Key: advance_clear_ai_check.gemini_api_key"
            ))
        return api_key

    def _get_slip_attachments(self):
        """Get image attachments from chatter (เอกสารแนบ)."""
        self.ensure_one()
        image_mimes = ['image/png', 'image/jpeg', 'image/jpg', 'image/gif', 'image/webp']

        # Get attachments linked directly to this payment
        attachments = self.env['ir.attachment'].search([
            ('res_model', '=', 'account.payment'),
            ('res_id', '=', self.id),
        ])

        # Also get attachments from mail messages (chatter)
        if hasattr(self, 'message_ids') and self.message_ids:
            msg_attachments = self.env['ir.attachment'].search([
                ('res_model', '=', 'mail.message'),
                ('res_id', 'in', self.message_ids.ids),
            ])
            attachments |= msg_attachments

        # Filter only image files
        image_attachments = attachments.filtered(
            lambda a: a.mimetype in image_mimes and a.datas
        )
        return image_attachments

    def _call_gemini_for_slip_info(self, attachments, company_names=None):
        """Call Gemini API to extract date AND recipient name from payment slip images.

        company_names: รายชื่อบริษัทที่ระบบใช้งานอยู่ (ไทย/อังกฤษ) เพื่อให้ AI
        ช่วยตัดสินว่าผู้รับในสลิปเป็นบริษัทเดียวกันหรือไม่ (เทียบข้ามภาษาได้)

        Returns dict: {
            'date': 'DD/MM/YYYY',
            'found': True/False,
            'recipient_name': 'ชื่อผู้รับเงิน',
            'recipient_found': True/False,
            'recipient_matches_company': True/False,  # AI ช่วยเทียบข้ามภาษา
        }
        """
        api_key = self._get_gemini_api_key()

        parts = []
        for idx, att in enumerate(attachments, 1):
            if att.datas:
                mime_type = att.mimetype or 'image/jpeg'
                image_data = att.datas.decode('utf-8') if isinstance(att.datas, bytes) else att.datas
                parts.append({
                    "text": "[รูปที่ %d] ชื่อไฟล์: %s" % (idx, att.name or 'unknown'),
                })
                parts.append({
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": image_data,
                    }
                })

        prompt = (
            "คุณเป็นผู้เชี่ยวชาญในการอ่านสลิปการโอนเงิน/ใบเสร็จ/สลิปธนาคาร/"
            "ใบแจ้งการชำระเงิน (Payment Advice)\n"
            "กรุณาอ่านข้อมูลต่อไปนี้จากเอกสารในรูปภาพ:\n\n"
            "1. วันที่ทำรายการ (Transaction Date)\n"
            "2. ชื่อผู้รับเงิน (Recipient Name / To)\n\n"
            "กฎ:\n"
            "1. หาวันที่ทำรายการ (Transaction Date) จากเอกสาร\n"
            "2. ถ้ามีหลายวันที่ ให้เลือกตามลำดับความสำคัญ:\n"
            "   (ก) 'วันที่ทำรายการ' หรือ 'Transaction Date' — ใช้ค่านี้เป็นอันดับแรกเสมอ\n"
            "   (ข) ถ้าไม่มี (ก) ใช้ 'Received Date' หรือวันที่ใต้หัวข้อผลลัพธ์รายการ เช่น "
            "'Transfer Completed' / 'โอนเงินสำเร็จ' / 'จ่ายบิลสำเร็จ' / 'ชำระบิลสำเร็จ' / "
            "'ชำระเงินสำเร็จ' (สลิป KBIZ/K BANK/K PLUS/K+)\n"
            "       *** สลิป K+ (K PLUS) วันที่ทำรายการอยู่ 'ด้านบนสุด' ใต้หัวข้อผลลัพธ์ "
            "(เช่น 'Transfer Completed', 'โอนเงินสำเร็จ', 'จ่ายบิลสำเร็จ') โดยมีได้ 2 แบบ:\n"
            "         - แบบอังกฤษ: 'DD Mon YY HH:MM AM/PM' เช่น '13 Jun 26 11:45 AM' → "
            "ใช้ '13 Jun 26' (ตัดเวลา 11:45 AM ทิ้ง)\n"
            "         - แบบไทย: 'DD <เดือนย่อไทย> YY HH:MM น.' เช่น '21 ก.ค. 69 15:35 น.' → "
            "ใช้วันที่ '21 ก.ค. 69' (= 21/07/2026) โดยตัดเวลา '15:35 น.' ทิ้ง\n"
            "           อีกตัวอย่าง: '9 ก.ค. 69 10:47 น.' → ใช้ '9 ก.ค. 69' "
            "(ก.ค.=เดือน 07, ปี 69 เป็น พ.ศ. 2569 = ค.ศ. 2026 → ตอบ '09/07/2026')\n"
            "         อ่านเลข 'วัน' ที่อยู่ 'หน้าชื่อเดือน' ให้ชัดเจน และห้ามนำตัวเลขจาก "
            "'เวลา (HH:MM)', 'เลขที่รายการ/Transaction No', 'จำนวนเงิน', 'ค่าธรรมเนียม' "
            "มาปนเป็นเลขวัน/เดือน/ปีเด็ดขาด\n"
            "         นี่คือวันที่ทำรายการ ให้ set found=true เสมอ ***\n"
            "   (ค) ถ้าไม่มี (ก)(ข) ค่อยใช้ 'วันที่' / 'Date' ทั่วไป\n"
            "   (ง) ถ้าสลิปแสดงว่าทำรายการสำเร็จ/โอนเงินมีผลทันที (เช่น 'ทำรายการเสร็จสมบูรณ์', "
            "'โอนต่างธนาคารมีผลทันที', สลิปกรุงไทย/KTB/พร้อมเพย์) และมีเพียง 'วันที่มีผล' "
            "เป็นวันที่เดียวในสลิป ให้ใช้ 'วันที่มีผล' เป็นวันที่ทำรายการได้\n"
            "   *** หลีกเลี่ยง 'วันที่รายการมีผล / Value Date', 'อัปเดตล่าสุด / Last Updated', "
            "'วันที่พิมพ์ / Print Date' เมื่อมี (ก)(ข)(ค) ให้ใช้อยู่แล้ว — แต่ถ้า 'วันที่มีผล' "
            "เป็นวันเดียวในสลิปโอนสำเร็จ ให้ใช้ได้ตามข้อ (ง) ***\n"
            "3. แปลงรูปแบบวันที่ให้เป็น DD/MM/YYYY (ปี 4 หลัก) เสมอก่อนตอบกลับ:\n"
            "   - ตัดเวลา (เช่น '11:45 AM', '13.23 น.') ออกจากวันที่เสมอ เอาเฉพาะ วัน/เดือน/ปี\n"
            "   - ถ้าเดือนเป็นชื่อภาษาอังกฤษย่อ (Jan/Feb/.../Dec) → แปลงเป็นเลข 01-12\n"
            "     เช่น '1 Jun 26' → ใช้เดือน 06\n"
            "   - ถ้าปีบนสลิปเป็น 2 หลัก (เช่น '26', '69') → ขยายเป็น 4 หลัก ตามกฎนี้:\n"
            "     * ลอง 2000+YY ก่อน — ถ้าเป็นปีปัจจุบันหรืออดีต (ไม่เกินปีปัจจุบัน+1) ใช้ค่านี้\n"
            "       ตัวอย่าง (ปัจจุบัน ค.ศ. 2026): '26' → 2026 (ค.ศ.)\n"
            "     * ถ้า 2000+YY เป็นอนาคต แปลว่าเป็นปี พ.ศ. ใช้ (2500+YY)-543\n"
            "       ตัวอย่าง: '69' → 2569 พ.ศ. → 2026 ค.ศ. (เพราะ 2069 เป็นอนาคต)\n"
            "   - ถ้าปี 4 หลัก ≥ 2500 → เป็น พ.ศ. ลบ 543 เป็น ค.ศ.\n"
            "4. หาชื่อผู้รับเงิน (To / ไปยัง / ผู้รับ / Recipient) ให้ดึงชื่อเต็มทั้งภาษาไทยและอังกฤษ\n"
            "   - สำหรับ Payment Advice / ใบแจ้งการชำระเงิน: ผู้รับเงินอาจอยู่ในส่วน "
            "'รายละเอียดผู้รับเงิน / Recipient Details / Beneficiary' หรือ 'เรียน'\n"
            "   - สำหรับสลิป KBIZ/K BANK: ผู้รับอยู่ในส่วน 'To' หรือบล็อกสีม่วงล่าง 'From' \n"
            "5. ตอบกลับเป็น JSON format เท่านั้น\n\n"
            "ตอบกลับ JSON:\n"
            "{\n"
            '  "date": "DD/MM/YYYY",\n'
            '  "found": true,\n'
            '  "recipient_name": "ชื่อผู้รับเงินที่อ่านได้ (ทั้งไทยและอังกฤษ คั่นด้วย / ถ้ามีทั้งสองภาษา)",\n'
            '  "recipient_found": true,\n'
            '  "recipient_matches_company": true\n'
            "}\n\n"
            "ถ้าไม่พบวันที่หรือชื่อผู้รับ ให้ set found/recipient_found เป็น false\n\n"
            "หมายเหตุ: DD/MM/YYYY เป็นรูปแบบ วัน/เดือน/ปี ค.ศ. เช่น 24/03/2026"
        )

        # เพิ่มข้อมูลบริษัทที่ระบบใช้งานอยู่ ให้ AI ช่วยเทียบว่าผู้รับเป็นบริษัทเดียวกันไหม
        # (เทียบข้ามภาษาไทย/อังกฤษได้ เช่น NOPPADOL INTERTRADING = นภดล อินเตอร์เทรดดิ้ง)
        names = [n for n in (company_names or []) if n]
        if names:
            prompt += (
                "\n\n6. ตรวจสอบชื่อบริษัทผู้รับเงิน:\n"
                "   บริษัทที่ระบบกำลังใช้งานอยู่ (ชื่อที่ถูกต้อง) มีดังนี้:\n"
                + ''.join("   - %s\n" % n for n in names) +
                "   ให้ตั้ง recipient_matches_company = true ถ้าชื่อผู้รับเงินในสลิป "
                "เป็นบริษัทเดียวกันกับรายชื่อข้างต้น โดยถือว่าเป็นบริษัทเดียวกันได้แม้:\n"
                "   - ชื่อเป็นคนละภาษา (สลิปเป็นอังกฤษ แต่รายชื่อเป็นไทย หรือกลับกัน)\n"
                "   - สะกด/อ่านผิดเล็กน้อย, มี/ไม่มีคำว่า บริษัท/จำกัด/CO.,LTD/(สำนักงานใหญ่)\n"
                "   ให้ตั้งเป็น false ถ้าเป็นคนละบริษัทกันจริง ๆ (ชื่อหลักคนละชื่อ)\n"
                "   ถ้าอ่านชื่อผู้รับไม่ได้เลย ให้ตั้งเป็น false\n"
            )

        parts.append({"text": prompt})

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0,
                # gemini-2.5-flash เป็น thinking model — token ที่ใช้ "คิด" นับรวมใน
                # maxOutputTokens ด้วย ถ้าตั้งไว้น้อย (เดิม 1024) thinking อาจกินหมด
                # จน finishReason=MAX_TOKENS ไม่มี JSON ออกมา → parse fail → found=false
                # จึงเพิ่มโควตา และปิด thinking (thinkingBudget=0) เพราะงานนี้เป็น OCR
                # อ่านค่าตรง ๆ ไม่ต้องใช้การให้เหตุผลหลายขั้น
                "maxOutputTokens": 2048,
                "responseMimeType": "application/json",
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }

        headers = {"content-type": "application/json"}
        url = "%s?key=%s" % (GEMINI_API_URL, api_key)

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            result = response.json()

            candidates = result.get('candidates', [])
            if candidates:
                finish_reason = candidates[0].get('finishReason', '')
                content = candidates[0].get('content', {})
                parts_resp = content.get('parts', [])
                if parts_resp:
                    text_result = parts_resp[0].get('text', '')
                    _logger.info(
                        "Gemini slip info response (finishReason=%s): %s",
                        finish_reason, text_result,
                    )
                    try:
                        parsed = json.loads(text_result)
                        return parsed
                    except (json.JSONDecodeError, TypeError):
                        _logger.warning(
                            "Failed to parse Gemini response as JSON "
                            "(finishReason=%s): %s", finish_reason, text_result,
                        )
                else:
                    # ไม่มีส่วน text กลับมา (เช่น finishReason=MAX_TOKENS จาก thinking
                    # กินโควตาหมด หรือโดน safety block) — log ให้เห็นสาเหตุจริง
                    _logger.warning(
                        "Gemini returned no text part (finishReason=%s). "
                        "usageMetadata=%s safetyRatings=%s",
                        finish_reason,
                        result.get('usageMetadata'),
                        candidates[0].get('safetyRatings'),
                    )
            else:
                # ไม่มี candidate เลย — มักโดน promptFeedback block ที่ระดับ prompt
                _logger.warning(
                    "Gemini returned no candidates. promptFeedback=%s",
                    result.get('promptFeedback'),
                )

            return {'date': '', 'found': False, 'recipient_name': '', 'recipient_found': False}

        except requests.exceptions.Timeout:
            raise UserError(_("Gemini API request timed out. Please try again."))
        except requests.exceptions.ConnectionError:
            raise UserError(_("Cannot connect to Gemini API. Please check your internet connection."))
        except requests.exceptions.HTTPError as e:
            error_msg = str(e)
            try:
                error_detail = e.response.json()
                error_msg = error_detail.get('error', {}).get('message', str(e))
            except Exception:
                pass
            raise UserError(_("Gemini API Error: %s") % error_msg)
        except Exception as e:
            raise UserError(_("Unexpected error calling Gemini API: %s") % str(e))

    _MONTH_NAME_MAP = {
        'january': '01', 'february': '02', 'march': '03', 'april': '04',
        'may': '05', 'june': '06', 'july': '07', 'august': '08',
        'september': '09', 'october': '10', 'november': '11', 'december': '12',
        'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
        'jun': '06', 'jul': '07', 'aug': '08', 'sep': '09', 'sept': '09',
        'oct': '10', 'nov': '11', 'dec': '12',
    }

    # ชื่อเดือนภาษาไทย (เต็ม + ย่อแบบมีจุด) → เลข 2 หลัก
    # ใช้เป็น safety net เผื่อ AI คืนค่าวันที่เป็นภาษาไทย เช่น "12 มิ.ย. 2026"
    _THAI_MONTH_MAP = {
        'มกราคม': '01', 'กุมภาพันธ์': '02', 'มีนาคม': '03', 'เมษายน': '04',
        'พฤษภาคม': '05', 'มิถุนายน': '06', 'กรกฎาคม': '07', 'สิงหาคม': '08',
        'กันยายน': '09', 'ตุลาคม': '10', 'พฤศจิกายน': '11', 'ธันวาคม': '12',
        'ม.ค.': '01', 'ก.พ.': '02', 'มี.ค.': '03', 'เม.ย.': '04',
        'พ.ค.': '05', 'มิ.ย.': '06', 'ก.ค.': '07', 'ส.ค.': '08',
        'ก.ย.': '09', 'ต.ค.': '10', 'พ.ย.': '11', 'ธ.ค.': '12',
    }

    def _resolve_year(self, y):
        """แปลงค่าปีที่อ่านได้ให้เป็น ค.ศ. (4 หลัก).

        - ปี 4 หลัก ≥ 2500 → พ.ศ. ลบ 543
        - ปี 2 หลัก (< 100) → ลอง 2000+YY ก่อน ถ้าเป็นอนาคต (เกินปีปัจจุบัน+1)
          ตีเป็น พ.ศ. 25YY แล้วแปลงเป็น ค.ศ. ((2500+YY)-543 = 1957+YY)
        """
        if y < 100:
            current = datetime.now().year
            ce_guess = 2000 + y
            if ce_guess <= current + 1:
                return ce_guess
            return 1957 + y  # เทียบเท่า (2500+y) - 543
        if y > 2500:
            return y - 543
        return y

    def _parse_slip_date(self, date_str):
        u"""Parse date string to a Python date object.

        รองรับรูปแบบ:
        - DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD
        - DD/MM/YY, DD-MM-YY (ปี 2 หลัก auto-detect ค.ศ./พ.ศ.)
        - DD MMM YYYY / DD-MMM-YYYY / DD MMM YY / DD-MMM-YY
          (เดือนเป็นชื่อภาษาอังกฤษย่อ เช่น "1 Jun 2026", "1 Jun 26")
        - ปี พ.ศ. 4 หลัก (≥ 2500) → ลบ 543
        - ปี พ.ศ. 2 หลัก (เช่น "69") → auto-detect เป็น 2569 พ.ศ. = 2026 ค.ศ.
        """
        if not date_str:
            return None
        date_str = date_str.strip()

        # ตัดเวลาออกก่อน เช่น "13 Jun 26 11:45 AM" / "12/06/2026 13.23 น."
        # ลบ HH:MM(:SS), AM/PM และคำว่า "น." ที่บอกเวลา
        s = date_str
        s = re.sub(r'\d{1,2}:\d{2}(:\d{2})?', ' ', s)          # 11:45 / 11:45:30
        s = re.sub(r'\b[AaPp]\.?[Mm]\.?\b', ' ', s)            # AM / PM
        s = s.replace('น.', ' ')                               # เวลาไทย "น."

        # Normalize Thai month name/abbrev → /MM/ (เผื่อ AI คืนค่าเป็นวันที่ไทย)
        # แทนชื่อยาวก่อนชื่อย่อ และครอบจุดของชื่อย่อทั้งหมด เช่น "มิ.ย." → "/06/"
        for name in sorted(self._THAI_MONTH_MAP, key=len, reverse=True):
            if name in s:
                s = s.replace(name, '/' + self._THAI_MONTH_MAP[name] + '/')
                break

        # Normalize English month name/abbrev → 2-digit number
        s = s.lower()
        for name, num in self._MONTH_NAME_MAP.items():
            s = re.sub(r'\b' + name + r'\b', num, s, count=1)
        # Collapse separators (space/dash/slash/dot) → single '/'
        s = re.sub(r'[\s/\-\.]+', '/', s).strip('/')

        parts = s.split('/')
        # เผื่อมี token เวลาหลงเหลือต่อท้าย ใช้เฉพาะ 3 ส่วนแรก (วัน/เดือน/ปี)
        if len(parts) > 3:
            parts = parts[:3]
        if len(parts) != 3:
            return None

        # Try day-first (Thai/European): DD/MM/Y*
        try:
            d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
            if 1 <= d <= 31 and 1 <= m <= 12:
                return datetime(self._resolve_year(y), m, d).date()
        except (ValueError, OverflowError):
            pass

        # Try ISO order: YYYY/MM/DD
        try:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            if y >= 100 and 1 <= m <= 12 and 1 <= d <= 31:
                return datetime(self._resolve_year(y), m, d).date()
        except (ValueError, OverflowError):
            pass

        return None

    # คำที่ตัดทิ้งตอน normalize ชื่อบริษัท (รูปแบบทางกฎหมาย/คำนำหน้า)
    # ตัดทั้งภาษาไทยและอังกฤษ เพื่อเทียบเฉพาะ "แก่นชื่อ" ที่แยกแยะบริษัทได้
    _COMPANY_NAME_STOPWORDS = {
        'บริษัท', 'บมจ', 'หจก', 'จำกัด', 'จํากัด', 'มหาชน',
        'ห้างหุ้นส่วนจำกัด', 'ห้างหุ้นส่วนจํากัด', 'ห้างหุ้นส่วน',
        'co', 'ltd', 'company', 'limited', 'public', 'inc',
        'corp', 'corporation', 'the', 'and',
        # ตัวระบุสาขา — ไม่ใช่ส่วนของชื่อบริษัท ต้องตัดทิ้งก่อนเทียบ
        'สำนักงานใหญ่', 'สำนักงานใหญ', 'สํานักงานใหญ่', 'สํานักงานใหญ',
        'สนงใหญ่', 'สนงใหญ', 'สาขา', 'head', 'office', 'branch', 'hq',
    }

    # เกณฑ์ความคล้าย (0-1) ขั้นต่ำที่ถือว่าชื่อ "ตรงบางส่วน" — ปรับได้ผ่าน
    # System Parameter: payment_slip_date_ai.name_match_threshold
    _DEFAULT_NAME_MATCH_THRESHOLD = 0.65

    def _normalize_company_name(self, name):
        u"""ย่อชื่อบริษัทให้เหลือเฉพาะ "แก่นชื่อ" สำหรับเปรียบเทียบ.

        - ตัดคำนำหน้า/รูปแบบทางกฎหมาย (บริษัท, จำกัด, CO.,LTD ฯลฯ)
        - ตัดช่องว่างและเครื่องหมายวรรคตอนทั้งหมด
        - แปลงเป็นตัวพิมพ์เล็ก
        คืนค่าเป็นสตริงกระชับ เช่น "บริษัท นภดล เอสกรุ๊ป จำกัด" -> "นภดลเอสกรุ๊ป"
        """
        if not name:
            return ''
        s = name.lower()
        # เปลี่ยนเครื่องหมายวรรคตอนเป็นช่องว่าง เพื่อแยก token
        s = re.sub(r'[.,()\[\]{}\-_/\\&"\'`:;|+]', ' ', s)
        s = re.sub(r'\s+', ' ', s).strip()
        tokens = [
            t for t in s.split(' ')
            if t and t not in self._COMPANY_NAME_STOPWORDS and not t.isdigit()
        ]
        return ''.join(tokens)

    def _name_similarity(self, a, b):
        u"""คืนคะแนนความคล้าย 0-1 ระหว่างชื่อที่ normalize แล้ว 2 ชื่อ.

        ใช้ค่าที่สูงกว่าระหว่าง
        - อัตราส่วนความคล้ายแบบ SequenceMatcher (ทนต่อการอ่านผิดบางตัว)
        - คะแนน "เป็นส่วนหนึ่งของกัน" (ชื่อสั้นเป็น substring ของชื่อยาว)
          โดยถ่วงด้วยสัดส่วนความยาว เพื่อกันไม่ให้แค่คำร่วม (เช่น "นภดล")
          ทำให้บริษัทพี่น้องผ่านกันเอง
        """
        if not a or not b:
            return 0.0
        ratio = SequenceMatcher(None, a, b).ratio()
        shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
        contain = (len(shorter) / len(longer)) if shorter in longer else 0.0
        return max(ratio, contain)

    def _get_company_name_candidates(self):
        u"""รวมรายชื่อที่ยอมรับได้ของบริษัทปัจจุบัน (ชื่อหลัก + ชื่อสำรอง)."""
        self.ensure_one()
        company = self.company_id or self.env.company
        names = [company.name or '']
        extra = company.slip_verify_extra_names or ''
        for line in re.split(r'[\r\n]+', extra):
            line = line.strip()
            if line:
                names.append(line)
        return names

    def _verify_recipient_company(self, recipient_name):
        u"""ตรวจว่าชื่อผู้รับเงินจากสลิปตรงกับบริษัทปัจจุบัน (แบบ partial match).

        คืน dict: {'matched': bool, 'score': float, 'company': str, 'best': str}
        - แยกชื่อผู้รับที่ AI อ่านได้เป็นหลายท่อน (คั่นด้วย / หรือขึ้นบรรทัดใหม่)
          เผื่อมีทั้งไทยและอังกฤษ แล้วเทียบทุกท่อนกับทุกชื่อของบริษัท
        - ผ่านถ้าคะแนนสูงสุด >= threshold
        """
        self.ensure_one()
        threshold = self._DEFAULT_NAME_MATCH_THRESHOLD
        param = self.env['ir.config_parameter'].sudo().get_param(
            'payment_slip_date_ai.name_match_threshold', default=''
        )
        if param:
            try:
                threshold = float(param)
            except (ValueError, TypeError):
                pass

        company = self.company_id or self.env.company
        # แยกชื่อผู้รับเป็นหลายท่อน (ทั้งท่อนรวม และแต่ละท่อนที่คั่นด้วย / หรือ newline)
        recipient_parts = [recipient_name or '']
        recipient_parts += re.split(r'[/\r\n]+', recipient_name or '')
        norm_recipients = [
            n for n in (self._normalize_company_name(p) for p in recipient_parts) if n
        ]

        norm_companies = [
            n for n in (self._normalize_company_name(c) for c in self._get_company_name_candidates()) if n
        ]

        best_score = 0.0
        best_pair = ('', '')
        for nr in norm_recipients:
            for nc in norm_companies:
                score = self._name_similarity(nr, nc)
                if score > best_score:
                    best_score = score
                    best_pair = (nr, nc)

        return {
            'matched': best_score >= threshold,
            'score': best_score,
            'company': company.name or '',
            'best': best_pair[1],
        }

    def action_post(self):
        """Block confirmation unless the slip date has been extracted/checked first.

        The user MUST press the "ใช้วันที่จากสลิป" button (which runs
        action_extract_slip_date and sets slip_date_checked=True) before the
        payment can be posted/confirmed.

        Callers that auto-create+post payments programmatically (เช่นโมดูล
        account_voucher_npd ฟังก์ชันคืนเงินประกันค่าเช่า) สามารถข้ามการตรวจ
        ได้โดยส่ง context `skip_slip_date_check=True` เนื่องจากกรณีเหล่านี้
        ไม่มีสลิปแยกให้ AI อ่าน (เกิดจากการหักยอดในระบบ ไม่ใช่การโอนเงินจริง)

        Payment Method ที่ไม่มีสลิปจริง (ไม่ใช่การโอนเงิน) ก็ข้ามการตรวจอัตโนมัติ:
        - ประเภท 'cash' (เงินสด)
        - ชื่อ 'หักเงินประกันค่าเช่า' (หักจากเงินประกัน — ไม่มีสลิป)

        สมุดรายวันที่เป็นการ 'ลดหนี้' (เช่น 'สมุดรายวันรับชำระลดหนี้') ก็ข้ามได้
        เพราะเป็นการตัดหนี้ในระบบ ไม่ใช่การรับโอนเงินจริงที่มีสลิป

        นอกจากนี้ ผู้ใช้ที่มีสิทธิ์ allow_skip_slip_date_check (ตั้งที่หน้า User)
        สามารถ post ได้เลย ใช้เป็น escape hatch กรณี AI อ่านสลิปไม่ได้
        """
        # สิทธิ์ระดับผู้ใช้: ข้ามการตรวจทั้งหมด
        if self.env.user.allow_skip_slip_date_check:
            return super(AccountPaymentSlipDate, self).action_post()
        if not self.env.context.get('skip_slip_date_check'):
            for payment in self:
                pm = payment.payment_method_one_id
                # จ่ายเงินสด / หักจากเงินประกัน → ไม่มีสลิป ข้ามได้
                if pm and (pm.type == 'cash' or pm.name == 'หักเงินประกันค่าเช่า'):
                    continue
                # สมุดรายวันรับชำระลดหนี้ (ตัดหนี้ในระบบ ไม่มีสลิป) → ข้ามได้
                if payment.journal_id and 'ลดหนี้' in (payment.journal_id.name or ''):
                    continue
                if not payment.slip_date_checked:
                    raise UserError(_(
                        "กรุณากดปุ่ม \"ใช้วันที่จากสลิป\" เพื่อตรวจสอบวันที่จากสลิปก่อน\n"
                        "จึงจะสามารถยืนยันเอกสารได้"
                    ))
        return super(AccountPaymentSlipDate, self).action_post()

    def action_draft(self):
        """Reset the slip check flag so the button must be pressed again
        before the payment can be confirmed once more."""
        res = super(AccountPaymentSlipDate, self).action_draft()
        self.write({'slip_date_checked': False})
        return res

    def action_extract_slip_date(self):
        """Main action: extract date from payment slip using AI and verify recipient."""
        self.ensure_one()

        # Step 1: Get image attachments
        attachments = self._get_slip_attachments()
        if not attachments:
            raise UserError(_(
                "ไม่พบรูปภาพสลิปในเอกสารแนบ\n"
                "กรุณาอัปโหลดรูปสลิปการโอนเงินในส่วนเอกสารแนบ (Log/Chatter) ก่อน"
            ))

        if len(attachments) > 1:
            raise UserError(_(
                "พบรูปภาพสลิป %d ไฟล์ในเอกสารแนบ\n"
                "กรุณาอัปโหลดสลิปการโอนเงินเพียง 1 ไฟล์เท่านั้น\n"
                "กรุณาลบสลิปที่ไม่ต้องการออกก่อนแล้วลองใหม่อีกครั้ง"
            ) % len(attachments))

        # Step 2: Call Gemini API to get date + recipient. ส่งชื่อบริษัทที่ใช้งานอยู่
        # เข้าไปด้วย เพื่อให้ AI ช่วยเทียบว่าผู้รับเป็นบริษัทเดียวกันไหม (เทียบข้ามภาษาได้)
        company_names = self._get_company_name_candidates()
        result = self._call_gemini_for_slip_info(attachments, company_names)

        # Step 3: Validate date
        if not result.get('found', False) or not result.get('date'):
            raise UserError(_(
                "AI ไม่สามารถอ่านวันที่จากสลิปได้\n"
                "กรุณาตรวจสอบว่ารูปสลิปชัดเจนและมีวันที่ปรากฏอยู่"
            ))

        date_str = result.get('date', '')
        parsed_date = self._parse_slip_date(date_str)

        if not parsed_date:
            raise UserError(_(
                "AI อ่านวันที่ได้เป็น '%s' แต่ไม่สามารถแปลงเป็นวันที่ได้\n"
                "กรุณาตรวจสอบรูปสลิปอีกครั้ง"
            ) % date_str)

        recipient_name = result.get('recipient_name', '')
        _logger.info("AI read recipient name: %s", recipient_name)

        # Step 3.5: Verify the recipient company on the slip matches the
        # company currently in use. Uses partial/fuzzy matching so a few
        # mis-read characters from the AI don't cause a false rejection.
        company = self.company_id or self.env.company
        if not result.get('recipient_found', False) or not recipient_name:
            raise UserError(_(
                "อ่านชื่อผู้รับเงินจากสลิปไม่ได้ กรุณาใช้สลิปที่ชัดเจนกว่านี้"
            ))

        verify = self._verify_recipient_company(recipient_name)
        # AI ช่วยเทียบข้ามภาษา (ไทย/อังกฤษ) — ผ่านถ้า fuzzy match ตัวอักษร
        # หรือ AI ยืนยันว่าเป็นบริษัทเดียวกัน อย่างใดอย่างหนึ่ง
        ai_match = bool(result.get('recipient_matches_company', False))
        matched = verify['matched'] or ai_match
        _logger.info(
            "Company name verify: recipient='%s' company='%s' score=%.2f "
            "fuzzy_matched=%s ai_matched=%s -> matched=%s",
            recipient_name, verify['company'], verify['score'],
            verify['matched'], ai_match, matched,
        )
        if not matched:
            raise UserError(_(
                "ชื่อบริษัทในสลิปไม่ตรงกับบริษัทที่ใช้งานอยู่ ยืนยันไม่ได้\n"
                "บริษัท: %s\n"
                "ชื่อในสลิป: %s"
            ) % (verify['company'] or '-', recipient_name or '-'))

        # Step 4: All checks passed — mark as checked.
        # Only overwrite the payment date while still in draft. Once the payment
        # is posted, its date is locked to the posted journal entries and writing
        # it would raise "You cannot delete an item linked to a posted entry".
        vals = {
            'slip_date_extracted': date_str,
            'slip_date_checked': True,
        }
        if self.state == 'draft':
            vals['date'] = parsed_date
            message = _('อ่านวันที่จากสลิปสำเร็จ: %s (ผู้รับ: %s)') % (date_str, recipient_name or '-')
        else:
            message = _(
                'อ่านวันที่จากสลิปได้: %s (ผู้รับ: %s)\n'
                'เอกสารถูกลงบันทึกแล้ว จึงไม่เปลี่ยนวันที่ในเอกสาร'
            ) % (date_str, recipient_name or '-')
        self.write(vals)

        # Return success notification
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('สำเร็จ'),
                'message': message,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }
