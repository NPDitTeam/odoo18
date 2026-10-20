/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { browser } from "@web/core/browser/browser";
import { cookie } from "@web/core/browser/cookie";
import { user } from "@web/core/user";
import { Many2OneField, many2OneField } from "@web/views/fields/many2one/many2one_field";

// ช่องค้นหาเลขเอกสาร: แสดงรายการมากขึ้น ไม่มีปุ่มสร้าง และเลือกแล้วเปิดเอกสารทันที
export class DocFinderMany2One extends Many2OneField {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.actionService = useService("action");
    }

    get Many2XAutocompleteProps() {
        return { ...super.Many2XAutocompleteProps, searchLimit: 15 };
    }

    async updateRecord(value) {
        const res = await super.updateRecord(value);
        if (value && value[0]) {
            await this.openDocument(value[0]);
        }
        return res;
    }

    async openDocument(id) {
        const action = await this.orm.call("npd.doc.finder.line", "action_open", [[id]]);
        const companyId = action.npd_company_id;
        delete action.npd_company_id;
        const active = user.context.allowed_company_ids || [];
        if (companyId && !active.includes(companyId)) {
            // เอกสารอยู่บริษัทที่ยังไม่ได้ติ๊กใช้งาน: เพิ่มบริษัทนั้นแล้วโหลดหน้าเอกสารใหม่
            cookie.set("cids", [...active, companyId].join("-"));
            browser.location.href = action.id
                ? `/odoo/action-${action.id}/${action.res_id}`
                : `/odoo/${action.res_model}/${action.res_id}`;
            return;
        }
        await this.actionService.doAction(action);
    }
}

registry.category("fields").add("npd_doc_finder", {
    ...many2OneField,
    component: DocFinderMany2One,
    extractProps() {
        const props = many2OneField.extractProps(...arguments);
        return {
            ...props,
            canOpen: false,
            canCreate: false,
            canQuickCreate: false,
            canCreateEdit: false,
        };
    },
});
