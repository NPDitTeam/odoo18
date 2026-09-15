/**
 * ไฟสถานะของ "ตัวช่วย AI-IT" ในกล่องแชท
 *   เขียว = เรียก AI ได้ (ตั้งค่า Gemini API key แล้ว) / แดง = เรียก AI ไม่ได้
 * ค่าที่ใช้คือ im_status ของ partner บอท ซึ่งเซิร์ฟเวอร์คำนวณให้ (models/res_partner.py)
 * ที่นี่แค่บอกเทมเพลตว่าตัวไหนคือบอท เพื่อย้อมสี/เปลี่ยน tooltip เฉพาะของบอท
 *
 * Odoo 18 แสดงจุดสถานะสองที่: ImStatus (รายการ/รูปโปรไฟล์) และ ThreadIcon (หัวหน้าต่างแชท)
 */
import { ImStatus } from "@mail/core/common/im_status";
import { ThreadIcon } from "@mail/core/common/thread_icon";

import { session } from "@web/session";
import { patch } from "@web/core/utils/patch";

function isBotPersona(persona) {
    const botId = session.npd_ai_it_bot_partner_id;
    return Boolean(botId && persona && persona.type === "partner" && persona.id === botId);
}

patch(ImStatus.prototype, {
    get isNpdAiItBot() {
        return isBotPersona(this.persona);
    },
});

patch(ThreadIcon.prototype, {
    get isNpdAiItBot() {
        return isBotPersona(this.correspondent?.persona);
    },
});
