/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Dialog } from "@web/core/dialog/dialog";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

// popup ค้นหาข้อมูลบริษัทจากกรมสรรพากร
export class RdLookupDialog extends Component {
    static template = "npd_partner_rd_lookup.RdLookupDialog";
    static components = { Dialog };
    static props = {
        vat: { type: String, optional: true },
        branch: { type: String, optional: true },
        partnerId: { optional: true },
        onApply: Function,
        close: Function,
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({
            vat: this.props.vat || "",
            branch: this.props.branch || "00000",
            loading: false,
            result: null,
        });
        if (this.state.vat) {
            this.search();
        }
    }

    async search() {
        this.state.loading = true;
        try {
            this.state.result = await this.orm.call("res.partner", "npd_rd_lookup_values", [
                this.state.vat,
                this.state.branch,
                this.props.partnerId || false,
            ]);
        } finally {
            this.state.loading = false;
        }
    }

    onKeydown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.search();
        }
    }

    async apply() {
        if (this.state.result && this.state.result.ok) {
            await this.props.onApply(this.state.result.values);
            this.props.close();
        }
    }
}

// ปุ่มใต้เลขผู้เสียภาษี (แสดงเฉพาะบริษัท) — เติมลงฟอร์มโดยไม่ต้องบันทึกผู้ติดต่อก่อน
export class RdLookupWidget extends Component {
    static template = "npd_partner_rd_lookup.RdLookupWidget";
    static props = { ...standardWidgetProps };

    setup() {
        this.dialog = useService("dialog");
    }

    open() {
        const record = this.props.record;
        this.dialog.add(RdLookupDialog, {
            vat: record.data.vat || "",
            branch: record.data.branch || "00000",
            partnerId: record.resId || false,
            onApply: (values) => this.apply(values),
        });
    }

    async apply(values) {
        const record = this.props.record;
        const changes = {};
        for (const [fname, value] of Object.entries(values)) {
            if (!(fname in record.fields)) {
                continue;
            }
            changes[fname] = value;  // many2one = [id, display_name]
        }
        await record.update(changes);
    }
}

registry.category("view_widgets").add("npd_rd_lookup", { component: RdLookupWidget });
