/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { CompanySelector } from "@web/webclient/switch_company_menu/switch_company_menu";

/*
 * บังคับโหมด "บริษัทเดียว" (single-company)
 *
 * เดิม navbar ให้ติ๊กเลือกได้หลายบริษัทพร้อมกัน (mode 'toggle')
 * patch นี้ทำให้ทุกการคลิกบริษัท = ล้างของเดิมทั้งหมดแล้วเลือกบริษัทที่คลิก
 * เพียงบริษัทเดียว จากนั้น apply + ปิด dropdown ทันที
 */
patch(CompanySelector.prototype, {
    switchCompany(mode, companyId) {
        this.selectedCompaniesIds.splice(0, this.selectedCompaniesIds.length, companyId);
        this.apply();
        this.dropdownState.close?.();
    },
});
