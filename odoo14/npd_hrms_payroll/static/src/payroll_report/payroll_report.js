/** @odoo-module **/

/*
 * หน้าจอรายงานเงินเดือน — แสดงตารางในหน้า Odoo เลย ไม่เด้งแท็บใหม่
 *
 * ทำแบบเดียวกับรายงานภาษีฝั่ง Odoo 14 ที่ผู้ใช้คุ้นอยู่ คือกดดูแล้วเห็นรายงาน
 * พร้อมแถบด้านบนที่ยังกดย้อนกลับไปเลือกงวดใหม่ได้ ต่างจากการเปิดแท็บใหม่
 * ที่หลุดออกจากระบบแล้วต้องกดย้อนเอง
 *
 * ตัว HTML ของตารางสร้างจากเทมเพลตฝั่งเซิร์ฟเวอร์ ที่นี่แค่ดึงมาแสดง
 * จะได้ไม่มีสูตรคำนวณซ้ำสองที่แล้วหลุดจากกันภายหลัง
 */

import { Component, onWillStart, useState, markup } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

export class PayrollReportAction extends Component {
    static template = "npd_hrms_payroll.PayrollReportAction";
    static components = { Layout };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ html: "", reportId: null });

        onWillStart(async () => {
            const context = this.props.action.context || {};
            const reportId = context.active_id;
            this.state.reportId = reportId;
            const html = await this.orm.call(
                "payroll.report", "get_report_html", [[reportId]]
            );
            // markup บอก OWL ว่าสตริงนี้เป็น HTML ที่เราสร้างเองฝั่งเซิร์ฟเวอร์
            // ไม่ใช่ข้อความจากผู้ใช้ จึงแสดงเป็นแท็กได้โดยไม่ต้องกังวลเรื่องความปลอดภัย
            this.state.html = markup(html);
        });
    }

    onPrint() {
        window.print();
    }

    async onExportExcel() {
        const action = await this.orm.call(
            "payroll.report", "action_export_excel", [[this.state.reportId]]
        );
        this.action.doAction(action);
    }
}

registry.category("actions").add("npd_payroll_report_backend", PayrollReportAction);
