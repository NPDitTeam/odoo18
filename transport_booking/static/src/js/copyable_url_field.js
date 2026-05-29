/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class CopyableUrlField extends Component {
    static template = "transport_booking.CopyableUrlField";
    static props = {
        ...standardFieldProps,
    };

    get url() {
        return this.props.record.data[this.props.name] || "";
    }

    async copyToClipboard() {
        const url = this.url;
        if (!url) {
            this.env.services.notification.add(
                "ไม่มี Link ให้คัดลอก",
                { type: "warning" }
            );
            return;
        }

        try {
            await navigator.clipboard.writeText(url);
            this.env.services.notification.add(
                "📋 คัดลอก Link สำเร็จ!",
                { type: "success" }
            );
        } catch (err) {
            // Fallback สำหรับเบราว์เซอร์เก่า
            const textArea = document.createElement("textarea");
            textArea.value = url;
            textArea.style.position = "fixed";
            textArea.style.left = "-999999px";
            document.body.appendChild(textArea);
            textArea.select();
            
            try {
                document.execCommand('copy');
                this.env.services.notification.add(
                    "📋 คัดลอก Link สำเร็จ!",
                    { type: "success" }
                );
            } catch (err2) {
                this.env.services.notification.add(
                    "❌ ไม่สามารถคัดลอกได้ กรุณาเลือกและกด Ctrl+C",
                    { type: "danger" }
                );
            }
            
            document.body.removeChild(textArea);
        }
    }
}

registry.category("fields").add("copyable_url", {
    component: CopyableUrlField,
});
