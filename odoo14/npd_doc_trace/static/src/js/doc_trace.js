/** @odoo-module **/

import { registry } from "@web/core/registry";
import { DocFinderMany2One } from "@npd_doc_finder/js/doc_finder";

// เลือกเลขเอกสารแล้วให้เซิร์ฟเวอร์สร้างผลตรวจ แล้วเปิด popup ผล (แทนการเปิดหน้าเอกสาร)
export class DocTraceMany2One extends DocFinderMany2One {
    async openDocument(id) {
        const action = await this.orm.call("npd.doc.trace.wizard", "action_start", [id]);
        await this.actionService.doAction(action);
    }
}

registry.category("fields").add("npd_doc_trace", {
    ...registry.category("fields").get("npd_doc_finder"),
    component: DocTraceMany2One,
});
