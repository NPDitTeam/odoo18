odoo.define("l10n_th_tax_report_backend", function (require) {
    "use strict";

    var AbstractAction = require("web.AbstractAction");
    var core = require("web.core");
    var ReportWidget = require("web.Widget");
    var _t = core._t;
    var framework = require('web.framework');
    var ActionManager = require('web.ActionManager');

    var report_backend = AbstractAction.extend({
        hasControlPanel: true,
        events: {
            "click .o_l10n_th_tax_report_print": "print_report",
            "click .o_l10n_th_tax_report_export": "export_report",
            "click .o_l10n_th_tax_report_export_test_excel": "export_test_excel_report",
        },
        init: function (parent, action) {
            this._super.apply(this, arguments);
            this.actionManager = parent;
            this.given_context = {};
            this.odoo_context = action.context;
            this.controller_url = action.context.url;
            if (action.context.context) {
                this.given_context = action.context.context;
            }
            this.given_context.active_id =
                action.context.active_id || action.params.active_id;
            this.given_context.model = action.context.active_model || false;
            this.given_context.ttype = action.context.ttype || false;

            this.wizard_data = {
                company_id: this.odoo_context.wizard_company_id,
                tax_group_id: this.odoo_context.wizard_tax_group_id,
                tax_id: this.odoo_context.wizard_tax_id,
                date_range_id: this.odoo_context.wizard_date_range_id,
                branch_id: this.odoo_context.wizard_branch_id,
            };
        },
        willStart: function () {
            return Promise.all([this._super.apply(this, arguments), this.get_html()]);
        },
        set_html: function () {
            var self = this;
            var def = Promise.resolve();
            if (!this.report_widget) {
                this.report_widget = new ReportWidget(this, this.given_context);
                def = this.report_widget.appendTo(this.$el.find(".o_content"));
            }
            def.then(function () {
                self.report_widget.$el.html(self.html);
            });
        },
        start: function () {
            this.set_html();
            return this._super();
        },
        get_html: function () {
            var self = this;
            var defs = [];
            return this._rpc({
                model: this.given_context.model,
                method: "get_html",
                args: [self.given_context],
                context: self.odoo_context,
            }).then(function (result) {
                self.html = result.html;
                defs.push(self.update_cp());
                return Promise.all(defs);
            });
        },
        update_cp: function () {
            if (this.$buttons) {
                var status = {
                    breadcrumbs: this.actionManager.get_breadcrumbs(),
                    cp_content: {$buttons: this.$buttons},
                };
                return this.update_control_panel(status);
            }
        },
        do_show: function () {
            this._super();
            this.update_cp();
        },
        print_report: function () {
            var self = this;
            this._rpc({
                model: this.given_context.model,
                method: "print_report",
                args: [this.given_context.active_id, "qweb-pdf"],
                context: self.odoo_context,
            }).then(function (result) {
                self.do_action(result);
            });
        },
        export_report: function () {
            var self = this;
            this._rpc({
                model: this.given_context.model,
                method: "print_report",
                args: [this.given_context.active_id, "xlsx"],
                context: self.odoo_context,
            }).then(function (result) {
                self.do_action(result);
            });
        },

        export_test_excel_report: function () {
            var self = this;
            framework.blockUI();
            this._rpc({
                model: 'tax.report.wizard',
                method: 'create',
                args: [this.wizard_data],
            }).then(function(new_wizard_id) {
                return self._rpc({
                    model: 'tax.report.wizard',
                    method: 'button_export_test_xlsx',
                    args: [[new_wizard_id]],
                    context: self.odoo_context,
                });
            }).then(function (result) {
                // Odoo 14 ไม่รู้จัก 'download_report_binary' tag โดยตรง
                // เราจะไปลงทะเบียน action handler เอง
                if (result.type === 'ir.actions.client' && result.tag === 'download_report_binary') {
                    return self.actionManager.doAction(result, {
                        on_close: function () {
                            framework.unblockUI();
                        },
                    });
                } else {
                    return self.do_action(result);
                }
            }).catch(function(error) {
                console.error("Error creating or exporting test excel report:", error);
                self.do_warn(_t("Error"), _t("Could not generate the test Excel report. Please try again."));
            }).finally(function() {
                framework.unblockUI();
            });
        },
        canBeRemoved: function () {
            return Promise.resolve();
        },
    });

    // *** NEW: ลงทะเบียน Client Action Handler สำหรับ 'download_report_binary' ***
    ActionManager.include({
        _executeClientAction: function (action) {
            if (action.tag === 'download_report_binary') {
                var self = this;
                var def = $.Deferred();
                framework.blockUI();

                // ใช้ window.location.origin เพื่อสร้าง URL ที่ถูกต้อง (scheme + host + port)
                // เพื่อหลีกเลี่ยงปัญหา unsafe port หรือการเดา port ผิดพลาด
                var downloadUrl = window.location.origin + '/l10n_th_tax_report/download_binary_file_post';

                var form = $('<form/>', {
                    action: downloadUrl, // ใช้ URL ที่สมบูรณ์
                    method: 'POST',
                    target: '_blank', // ดาวน์โหลดในแท็บใหม่
                }).appendTo('body');
                form.append($('<input/>', {
                    type: 'hidden',
                    name: 'csrf_token',
                    value: core.csrf_token,
                }));
                form.append($('<input/>', {
                    type: 'hidden',
                    name: 'filename',
                    value: action.context.report_file,
                }));
                form.append($('<input/>', {
                    type: 'hidden',
                    name: 'data',
                    value: action.context.data, // ข้อมูล Base64 encoded
                }));
                form.submit();

                framework.unblockUI();
                def.resolve();
                return def;
            }
            return this._super.apply(this, arguments);
        },
    });
    // *** END NEW ***

    core.action_registry.add("l10n_th_tax_report_backend", report_backend);
    return report_backend;
});