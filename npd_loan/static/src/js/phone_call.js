/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// Client action สำหรับโทรออกและ reload wizard
async function makePhoneCall(env, action) {
    const phone = action.params.phone;
    const wizardId = action.params.wizard_id;
    
    if (phone) {
        // สร้าง <a> tag แล้ว click เพื่อ trigger phone link
        const telLink = document.createElement('a');
        telLink.href = 'tel:' + phone;
        telLink.style.display = 'none';
        document.body.appendChild(telLink);
        telLink.click();
        document.body.removeChild(telLink);
        
        console.log('NPD Loan: Phone call triggered to:', phone);
        
        // รอ 500ms แล้ว reload wizard
        await new Promise(resolve => setTimeout(resolve, 500));
        
        // เปิด wizard ใหม่
        if (wizardId) {
            return env.services.action.doAction({
                type: 'ir.actions.act_window',
                res_model: 'npd.loan.call.wizard',
                res_id: wizardId,
                views: [[false, 'form']],
                target: 'new',
            });
        }
    }
    
    return Promise.resolve();
}

registry.category("actions").add("npd_loan_make_call", makePhoneCall);

console.log('NPD Loan: Phone Call Action Loaded');
