/**
 * เสียงเตือนเมื่อ "ตัวช่วย AI-IT" ตอบกลับ บนจอมือถือ
 *
 * จอใหญ่: Odoo 18 เล่นเสียงให้เองทุกข้อความแชทใหม่ (mail.out_of_focus notify —
 * ข้อความบอทที่ไม่ใช่ "แก้เสร็จ" ดู out_of_focus/out_of_focus_patch.js ซึ่งคงเสียงไว้)
 * ถ้าเล่นซ้ำตรงนี้อีกจะดัง 2 ครั้ง (ของ o14 ต้องเล่นเองเพราะ o14 ดังเฉพาะตอนไม่โฟกัส)
 * จอมือถือ: Odoo ข้ามการแจ้งเตือนทั้งหมด (store_service_patch: ui.isSmall) จึงเล่นเองเฉพาะกรณีนี้
 * ส่งเสียงเฉพาะข้อความของบอทตัวนี้เท่านั้น แชทกับคนอื่นยังเป็นค่ามาตรฐาน
 */
import { registry } from "@web/core/registry";
import { session } from "@web/session";

import { isAiItBotMessage } from "./out_of_focus/out_of_focus_patch";

export const npdAiItBotSoundService = {
    dependencies: ["mail.sound_effects", "ui"],
    start(env, { "mail.sound_effects": soundEffects, ui }) {
        let warned = false;
        env.bus.addEventListener("discuss.channel/new_message", ({ detail }) => {
            try {
                if (!session.npd_ai_it_bot_partner_id) {
                    if (!warned) {
                        warned = true;
                        console.warn(
                            "npd_ai_it_assistant: ไม่พบ npd_ai_it_bot_partner_id ใน session " +
                                "— เพิ่มไฟล์ .py ใหม่แล้วต้อง restart Odoo ไม่ใช่แค่ -u"
                        );
                    }
                    return;
                }
                const { message, silent } = detail || {};
                if (silent || !ui.isSmall || !isAiItBotMessage(message)) {
                    return;
                }
                if (document.hasFocus()) {
                    soundEffects.play("new-message");
                }
            } catch (error) {
                // เสียงเตือนพังไม่ควรทำให้ข้อความไม่ขึ้น
                console.warn("npd_ai_it_assistant: เล่นเสียงแจ้งเตือนไม่สำเร็จ", error);
            }
        });
    },
};

registry.category("services").add("npd_ai_it_bot_sound", npdAiItBotSoundService);
