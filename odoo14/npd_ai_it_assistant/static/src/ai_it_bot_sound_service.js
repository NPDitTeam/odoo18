/**
 * มีเสียงเตือนทุกครั้งที่ "ตัวช่วย AI-IT" ตอบกลับ
 *
 * Odoo ส่งเสียงเฉพาะตอนที่หน้าต่างไม่ได้โฟกัส (out_of_focus_service) แต่งานนี้
 * พนักงานนั่งจ้องแชทรออยู่ และบางขั้นตอน (ตัดสต๊อก/ยกเลิกเอกสาร) ใช้เวลาหลายวินาที
 * จึงเล่นเสียงเพิ่มตอนที่หน้าต่างโฟกัสอยู่ (ตอนไม่โฟกัส Odoo เล่นให้เองแล้ว จะได้ไม่ดังซ้ำ)
 * ส่งเสียงเฉพาะข้อความของบอทตัวนี้เท่านั้น แชทกับคนอื่นยังเป็นค่ามาตรฐาน
 */
import { registry } from "@web/core/registry";
import { session } from "@web/session";

export const npdAiItBotSoundService = {
    dependencies: ["mail.sound_effects"],
    start(env, { "mail.sound_effects": soundEffects }) {
        let warned = false;
        env.bus.addEventListener("discuss.channel/new_message", ({ detail }) => {
            try {
                const botId = session.npd_ai_it_bot_partner_id;
                if (!botId) {
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
                const author = message?.author;
                if (silent || !author || author.type !== "partner" || author.id !== botId) {
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
