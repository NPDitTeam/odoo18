/** @odoo-module **/
/**
 * ใบสั่งขาย: เลือกลูกค้าที่เป็นบริษัทแต่ยังไม่มีรหัสสาขา (Tax Branch)
 * → เด้งหน้าต่างให้กรอกทันที แล้วบันทึกกลับไปที่ลูกค้า
 *
 * patch ที่ Many2OneField (ตัวแม่ของ res_partner_many2one ที่ฟอร์มใบสั่งขายใช้)
 * แล้วกรองเฉพาะช่อง partner_id ของ sale.order — ไม่ผูกกับว่าวิวไหนตั้ง widget อะไร
 */
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { Many2OneField } from "@web/views/fields/many2one/many2one_field";

patch(Many2OneField.prototype, {
    async updateRecord() {
        const result = await super.updateRecord(...arguments);
        if (this.props.record.resModel === "sale.order" && this.props.name === "partner_id") {
            await this._npdCheckTaxBranch();
        }
        return result;
    },

    async _npdCheckTaxBranch() {
        const record = this.props.record;
        const value = record.data.partner_id;
        const partnerId = Array.isArray(value) ? value[0] : value && value.id;
        if (!partnerId || this._npdTaxBranchOpen) {
            return;
        }
        const missing = await this.orm.call("res.partner", "npd_tax_branch_missing", [partnerId]);
        if (!missing) {
            return;
        }
        this._npdTaxBranchOpen = true;
        await this.action.doAction("npd_partner_tax_branch.npd_tax_branch_wizard_action", {
            additionalContext: { default_partner_id: partnerId },
            onClose: async (infos) => {
                this._npdTaxBranchOpen = false;
                if (infos && infos.npd_tax_branch_saved) {
                    return;
                }
                // ปิดหน้าต่างโดยไม่กรอก: ไม่ให้ใช้ลูกค้ารายนี้ต่อจนกว่าจะมีรหัสสาขา
                await record.update({ partner_id: false });
                this.notification.add(
                    _t("ต้องกรอกรหัสสาขา (Tax Branch) ของลูกค้าบริษัทก่อน จึงจะเลือกลูกค้ารายนี้ได้"),
                    { title: _t("ยังไม่ได้กรอกรหัสสาขา"), type: "warning" }
                );
            },
        });
    },
});
