/** @odoo-module **/
/**
 * Field widget: npd_repair_countdown  (Odoo 18 / OWL)
 * ===================================================
 * นับถอยหลัง SLA การซ่อมแบบเรียลไทม์ — พอร์ตจาก widget legacy ของ Odoo 14
 *
 * ใช้ได้ 2 แบบ
 *   1) วางบนฟิลด์ datetime ที่เก็บ "เวลาครบกำหนด" โดยตรง
 *        <field name="repair_deadline" widget="npd_repair_countdown"
 *               options="{'done_field': 'repair_end_date'}"/>
 *   2) วางบนฟิลด์ char ที่เซิร์ฟเวอร์คำนวณข้อความมาให้แล้ว แล้วชี้ไปฟิลด์เวลา
 *      ครบกำหนดผ่าน option deadline_field (ถ้า JS ยังไม่โหลด ผู้ใช้จะยังเห็น
 *      ข้อความที่ถูกต้อง ณ ตอนโหลดหน้า แทนที่จะเห็นค่าดิบ)
 *
 * การแสดงผล
 *   - มีค่าใน done_field (ซ่อมเสร็จแล้ว)
 *       * เสร็จก่อนครบกำหนด -> "ซ่อมสำเร็จ"          (เขียว หยุดนิ่ง)
 *       * เสร็จหลังครบกำหนด -> "เกินกำหนด HH:MM:SS"  (แดง ค้างค่าที่เกินจริง)
 *   - ยังไม่เสร็จ (ลดทุกวินาที)
 *       * เหลือ > warn_minutes -> เขียว   * เหลือ <= warn_minutes -> เหลือง
 *       * เลยกำหนด -> "เกินกำหนด HH:MM:SS" (แดง วิ่งเพิ่มทุกวินาที)
 *
 * ภาระเซิร์ฟเวอร์ = 0 : ใช้ค่าที่โหลดมากับแถวอยู่แล้ว ไม่ยิง RPC เพิ่ม
 * และทั้งหน้าจอใช้ setInterval "ตัวเดียว" ร่วมกัน (ดู Ticker) แม้จะมีหลายร้อยแถว
 */
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, onWillDestroy, useState } from "@odoo/owl";

const TICK_INTERVAL = 1000;
// เหลือเวลามากกว่าเท่านี้ = เขียว, น้อยกว่าหรือเท่ากับ = เหลือง
const DEFAULT_WARN_MINUTES = 24 * 60;

// ---------------------------------------------------------------------------
// ตัวจับเวลากลาง: 1 หน้าจอ = setInterval 1 ตัว
// ---------------------------------------------------------------------------
const Ticker = {
    components: new Set(),
    handle: null,
    subscribe(comp) {
        this.components.add(comp);
        if (!this.handle) {
            this.handle = setInterval(() => this.tick(), TICK_INTERVAL);
        }
    },
    unsubscribe(comp) {
        this.components.delete(comp);
        if (!this.components.size && this.handle) {
            clearInterval(this.handle);
            this.handle = null;
        }
    },
    tick() {
        for (const comp of Array.from(this.components)) {
            comp.refresh();
        }
    },
};

function formatClock(totalSeconds) {
    const secs = Math.max(0, Math.floor(totalSeconds));
    const days = Math.floor(secs / 86400);
    const hours = Math.floor((secs % 86400) / 3600);
    const minutes = Math.floor((secs % 3600) / 60);
    const seconds = secs % 60;
    const pad = (n) => String(n).padStart(2, "0");
    const clock = `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
    return days ? `${days} วัน ${clock}` : clock;
}

export class RepairCountdown extends Component {
    static template = "npd_scrap_buttons.RepairCountdown";
    static props = {
        ...standardFieldProps,
        deadlineField: { type: String, optional: true },
        doneField: { type: String, optional: true },
        countField: { type: String, optional: true },
        warnMinutes: { type: Number, optional: true },
    };

    setup() {
        this.state = useState({ text: "", className: "" });
        this.refresh();
        Ticker.subscribe(this);
        onWillDestroy(() => Ticker.unsubscribe(this));
    }

    /** ค่าเวลาในฟอร์ม Odoo 18 เป็น luxon DateTime — ใช้ .ts เป็น epoch ms */
    _ts(fieldName) {
        if (!fieldName) {
            return null;
        }
        const value = this.props.record.data[fieldName];
        return value && value.ts ? value.ts : null;
    }

    get deadlineTs() {
        // ถ้าไม่ได้ระบุ deadline_field แปลว่า widget วางอยู่บนฟิลด์ deadline เอง
        return this._ts(this.props.deadlineField || this.props.name);
    }

    get warnSeconds() {
        return (this.props.warnMinutes || DEFAULT_WARN_MINUTES) * 60;
    }

    get suffix() {
        const field = this.props.countField;
        if (!field) {
            return "";
        }
        const count = this.props.record.data[field];
        return count && count > 1 ? ` (${count} ใบ)` : "";
    }

    refresh() {
        const deadline = this.deadlineTs;
        if (!deadline) {
            this.state.text = "";
            this.state.className = "";
            return;
        }
        const done = this._ts(this.props.doneField);
        if (done) {
            const late = Math.floor((done - deadline) / 1000);
            if (late > 0) {
                this.state.text = `เกินกำหนด ${formatClock(late)}${this.suffix}`;
                this.state.className = "text-danger fw-bold";
            } else {
                this.state.text = `ซ่อมสำเร็จ${this.suffix}`;
                this.state.className = "text-success";
            }
            return;
        }
        const left = Math.floor((deadline - Date.now()) / 1000);
        if (left <= 0) {
            this.state.text = `เกินกำหนด ${formatClock(-left)}${this.suffix}`;
            this.state.className = "text-danger fw-bold";
        } else {
            this.state.text = `${formatClock(left)}${this.suffix}`;
            this.state.className =
                left > this.warnSeconds ? "text-success" : "text-warning fw-bold";
        }
    }
}

export const repairCountdownField = {
    component: RepairCountdown,
    displayName: "นับถอยหลังซ่อม",
    supportedTypes: ["datetime", "char"],
    extractProps: ({ options }) => ({
        deadlineField: options.deadline_field,
        doneField: options.done_field,
        countField: options.count_field,
        warnMinutes: options.warn_minutes,
    }),
};

registry.category("fields").add("npd_repair_countdown", repairCountdownField);
