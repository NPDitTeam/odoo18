/**
 * popup แจ้งเตือนของ "ตัวช่วย AI-IT" เด้งเฉพาะตอนแก้เสร็จ และแสดงข้อความสั้น ๆ
 *
 * Odoo 18 เด้ง popup (หรือแจ้งเตือนของเบราว์เซอร์) พร้อมเสียง ทุกครั้งที่มีข้อความแชทใหม่
 * โดยยกเนื้อหาข้อความมาทั้งก้อน แต่บอทคุยหลายขั้น (แนะนำหัวข้อ ถามเลขเอกสาร ขอยืนยัน ...)
 * popup จึงขึ้นรกทุกขั้นและยาวอ่านไม่ทัน
 *
 * - ข้อความ "แก้เสร็จ": เซิร์ฟเวอร์แนบข้อความสั้นแบบซ่อนไว้ใน <span class="o_npd_ai_it_done d-none">
 *   (_post_bot(done=...) ใน models/ai_it_session.py) -> popup แสดงแค่ข้อความนั้น
 * - ข้อความอื่นของบอท: มีแค่เสียง ไม่เด้ง popup
 * แชทกับคนอื่นยังเป็นค่ามาตรฐานของ Odoo
 */
import { OutOfFocusService } from "@mail/core/common/out_of_focus_service";

import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";

/** ต้องตรงกับ DONE_MESSAGE_CLASS ใน models/ai_it_session.py */
export const AI_IT_DONE_CLASS = "o_npd_ai_it_done";

export function isAiItBotMessage(message) {
    const botId = session.npd_ai_it_bot_partner_id;
    const author = message?.author;
    return Boolean(botId && author && author.type === "partner" && author.id === botId);
}

/** ข้อความสั้นสำหรับ popup ถ้าเป็นข้อความ "แก้เสร็จ" ไม่ใช่ก็คืน null */
export function getAiItDoneText(message) {
    const body = String(message?.body || "");
    if (!body.includes(AI_IT_DONE_CLASS)) {
        return null;
    }
    const doc = new DOMParser().parseFromString(body, "text/html");
    const text = doc.querySelector(`.${AI_IT_DONE_CLASS}`)?.textContent.trim();
    return text || "✅ แก้เรียบร้อยแล้ว";
}

patch(OutOfFocusService.prototype, {
    notify(message) {
        if (!isAiItBotMessage(message)) {
            return super.notify(...arguments);
        }
        const doneText = getAiItDoneText(message);
        if (!doneText) {
            this._playSound();
            return;
        }
        this.sendNotification({
            message: doneText,
            sound: true,
            title: message.author.name,
            type: "success",
            icon: message.author.avatarUrl,
        });
    },
});
