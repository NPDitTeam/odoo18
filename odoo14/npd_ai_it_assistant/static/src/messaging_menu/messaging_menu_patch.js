/**
 * เพิ่มแท็บ "ตัวช่วย AI-IT" เข้าไปในเมนูสนทนา (ข้าง ๆ ทั้งหมด / แชท / ช่อง)
 *
 * แท็บนี้ไม่ได้แสดงรายการห้องแชท แต่แสดง "หัวข้อปัญหา" ที่ให้ AI ช่วยแก้ได้
 * เมื่อกดหัวข้อ ระบบจะเปิดห้องแชทกับ "ตัวช่วย AI-IT" ให้อัตโนมัติ
 *
 * Odoo 18: แท็บที่เลือกเก็บไว้ที่ store.discuss.activeTab (ใช้ร่วมกับหน้า Discuss)
 */
import { MessagingMenu } from "@mail/core/public_web/messaging_menu";

import { useEffect, useState } from "@odoo/owl";

import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

export const AI_IT_TAB_ID = "ai_it";

patch(MessagingMenu.prototype, {
    setup() {
        super.setup();
        this.aiItOrm = useService("orm");
        this.aiItNotification = useService("notification");
        this.aiIt = useState({ topics: [], isLoading: false, isLoaded: false, opening: false });

        // โหลดหัวข้อเมื่อสลับมาที่แท็บนี้ (ทั้งปุ่มบนเดสก์ท็อปและแถบล่างบนมือถือ)
        useEffect(
            (activeTab) => {
                if (activeTab === AI_IT_TAB_ID) {
                    this.loadAiItTopics();
                }
            },
            () => [this.store.discuss.activeTab]
        );
        // ปิดเมนูแล้วคืนแท็บเป็น "ทั้งหมด" — activeTab ใช้ร่วมกับหน้า Discuss
        // ถ้าค้างเป็น ai_it หน้า Discuss บนมือถือจะไม่รู้จักแท็บนี้
        useEffect(
            (isOpen) => {
                if (!isOpen && this.store.discuss.activeTab === AI_IT_TAB_ID && !this.env.inDiscussApp) {
                    this.store.discuss.activeTab = "main";
                }
            },
            () => [this.dropdown.isOpen]
        );
    },

    get aiItTabId() {
        return AI_IT_TAB_ID;
    },

    get aiItTabLabel() {
        return _t("ตัวช่วย AI-IT");
    },

    get tabs() {
        const tabs = super.tabs;
        if (this.env.inDiscussApp) {
            return tabs;
        }
        return [...tabs, { icon: "fa fa-magic", id: AI_IT_TAB_ID, label: this.aiItTabLabel }];
    },

    onClickAiItTab() {
        this.store.discuss.activeTab = AI_IT_TAB_ID;
    },

    /** ดึงรายการหัวข้อจากเซิร์ฟเวอร์ (โหลดครั้งเดียวต่อการเปิดเมนูหนึ่งครั้ง) */
    async loadAiItTopics() {
        if (this.aiIt.isLoading || this.aiIt.isLoaded) {
            return;
        }
        this.aiIt.isLoading = true;
        try {
            this.aiIt.topics = (await this.aiItOrm.silent.call(
                "npd.ai.it.topic",
                "get_available_topics",
                []
            )) || [];
            this.aiIt.isLoaded = true;
        } finally {
            this.aiIt.isLoading = false;
        }
    },

    /** เลือกหัวข้อ -> เปิดห้องแชทกับตัวช่วย AI-IT */
    async onClickAiItTopic(topic) {
        if (this.aiIt.opening) {
            return;
        }
        this.aiIt.opening = true;
        let result;
        try {
            result = await this.aiItOrm.call("npd.ai.it.session", "action_start_topic", [topic.id]);
        } finally {
            this.aiIt.opening = false;
        }
        if (!result || result.error) {
            this.aiItNotification.add((result && result.error) || _t("เปิดหัวข้อไม่สำเร็จ"), {
                type: "danger",
            });
            return;
        }
        // เปิด "ห้องแชท" ตรง ๆ ไม่ใช่ openChat({partnerId}) เพราะ Odoo ห้ามแชทกับ
        // partner ที่ไม่มี res.users ("You can only chat with partners that have a
        // dedicated user.") ส่วนบอทของเราจงใจไม่มี user
        this.store.insert(result.store_data);
        const thread = await this.store.Thread.getOrFetch({
            model: "discuss.channel",
            id: result.channel_id,
        });
        this.dropdown.close();
        thread?.open({ fromMessagingMenu: true });
    },
});
