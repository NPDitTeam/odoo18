/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";
import { session } from "@web/session";
import { Popover } from "@web/core/popover/popover";
import { renderToElement } from "@web/core/utils/render";
import { browser } from "@web/core/browser/browser";
import { useService } from "@web/core/utils/hooks";
import { SearchView } from "@ks_list_view_manager/component/search_view";
import { rpc } from "@web/core/network/rpc";
import { getCurrency } from "@web/core/currency";
import { _t } from "@web/core/l10n/translation";
import { formatFloat,formatInteger } from "@web/views/fields/formatters";
import {ksuseMagicColumnWidths} from "./ks_custom_hook";
const { useRef, onMounted , onWillStart , useExternalListener , onWillUpdateProps , Component,onPatched } = owl;
//ListRenderer.useMagicColumnWidths = false;

patch(Popover.prototype,{
    setup() {
        $(".ks_list_view_dropdown_container").removeClass("show")
        super.setup()
    },
});
patch(ListRenderer.prototype,  {
    setup() {
        super.setup();
         var self = this;
         this.ks_serial_number = session.ks_serial_number;
         this.ks_allow_search = true;
         this.ksDomain = [];
         this.datepicker;
         this.ks_datepicker_flag = 0
         this.mydomain = null;
        this.ks_autocomplete_data = {};
        this.ks_autocomplete_data_result = {};
        this.ks_lvm_mode = true;
        this.ks_remove_popup_flag = false;
        this.ks_key_fields = [];
        this.ks_field_domain_list = [];
        this.ks_field_domain_dict = {};
        this.ksBaseDomain = [];
        this.ks_advance_search_refresh = false;
        this.ks_start_date = undefined;
        this.ks_end_date = undefined;
        this.ks_start_date_id = undefined;
        this.ks_end_date_id = undefined;
        this.ks_editable = false;
        if (this.props.list.domain){
        this.default_domain = [...this.props.list.domain]
        this.ks_search_domain = [...this.props.list.domain]
        };
        if(this.env.searchModel && this.env.searchModel.globalDomain){
        this.search_default=[...this.env.searchModel.globalDomain]
        };
        this.ks_list_data = this.props.list_data ? this.props.list_data : session.list_data
        var ks_is_list_renderer = true ? this.ks_list_data : false;

        this.tableRef = useRef("table");
        this.ks_is_lines = true;
        if (this.props.activeActions.type == 'view' && this.isX2Many== false &&  ks_is_list_renderer) {
            this.ks_is_lines = false;
        }

        if(this.__owl__.name !== 'ListEditorRenderer'){
        onMounted(this._mounted);
        }
        if(this.__owl__.name !== 'ListEditorRenderer'){
        onPatched(()=>{
        if (this.isX2Many== false){
            this.ks_apply_properties();
        }
        })
        }


        if (!this.ks_is_lines){
            this.columnWidths = ksuseMagicColumnWidths(this.tableRef, () => {
                return {
                    columns: this.columns,
                    isEmpty: !this.props.list.records.length || this.props.list.model.useSampleModel,
                    hasSelectors: this.hasSelectors,
                    hasOpenFormViewColumn: this.hasOpenFormViewColumn,
                    hasActionsColumn: this.hasActionsColumn,
                    ks_list_data: this.ks_list_data,
                    Ks_initialize_lvm_data: this.props.Ks_initialize_lvm_data,
                    Ks_update_field_data:this.props.Ks_update_field_data,
                    useMagicColumnWidths:true,
                    ks_serial_number_enable:this.ks_serial_number
                };
            });
        }
    },

    ks_apply_properties(){
        var self = this
         var table = this.tableRef
        if (session.ks_header_text_color !="white"){
            var ks_header_text_color = session.ks_header_text_color;
            (table.el.querySelectorAll("thead .bg-primary th")).forEach((item) =>{item.style.setProperty("color", session.ks_header_text_color, "important")})
        }
        if (session.ks_header_color){
            var ks_header_color = session.ks_header_color;
            (table.el.querySelectorAll("thead .bg-primary th")).forEach((item,index) =>{
                if (index === 0){
                    item.style.setProperty("background-color", session.ks_header_color, "important")
                    const formCheckInput = item.querySelector('.form-check-input');
                    if (formCheckInput) {
                        // If it exists, set the border color
                        formCheckInput.style.setProperty("border-color", session.ks_header_text_color, "important");
                    }
                }else{
                    item.style.setProperty("background-color", session.ks_header_color, "important")
                }
            })
        }
        table.el.querySelectorAll(".o_list_sortable_caret ").forEach((item)=>{
            item.style.background = "none";
        });

    },
    async _mounted() {
        if (this.isX2Many== false){
            var self = this
            var table = this.tableRef
            this.ks_allow_search = true;
            self.ks_call_flag = 1;
            $($(table.el.querySelectorAll("thead tr"))[0]).addClass("bg-primary");
             this.ks_apply_properties();
        }
    },
    get hasActionsColumn(){
        if (this.isX2Many == false){
            return false
        }else{
        return true
        }

    },

     get nbCols() {
        let nbCols = this.columns.length;
        if (this.hasSelectors) {
            nbCols++;
        }
        if (this.hasActionsColumn) {
            nbCols++;
        }
        if (this.hasOpenFormViewColumn) {
            nbCols++;
        }
        if (this.ks_serial_number === 'True') {
            nbCols++;
        }
        return nbCols;
    },


    getActiveColumns(list) {
        if(this.isX2Many == true){
            return super.getActiveColumns(...arguments);
        }
        return this.allColumns.filter((col) => {
            if (list.isGrouped && col.widget === "handle") {
                return false; // no handle column if the list is grouped
            }
            if (col.optional === "hide") {
                return false;
            }
            if (this.evalColumnInvisible(col.column_invisible)) {
                return false;
            }
            return true;
        });
    },

        get ks_field_popup(){
            var self = this;
            var ks_field_popup = {};
            if (self.ksDomain != []) {
                for (var i = 0; i < self.ksDomain.length; i++) {
                    if (!(self.ksDomain[i] === '|')) {
                        if (ks_field_popup[self.ksDomain[i][0]] === undefined) {
                            ks_field_popup[self.ksDomain[i][0]] = [self.ksDomain[i][2]]
                        } else {
                            ks_field_popup[self.ksDomain[i][0]].push(self.ksDomain[i][2])
                        }
                    }
                }
            }
            return ks_field_popup

        },

        Ks_update_advance_search_controller(ks_options) {
             var self = this;
             if (ks_options !=false){
            let rec_ids = [];
                for (let i = 0; i < this.props.list.records.length; i++) {
                    rec_ids.push(this.props.list.records[i].resId);
                }
            ks_options['rec_ids'] = [...rec_ids]
            }

        if (this.ks_lvm_mode) {
            var self = this;
            if (self.ks_remove_popup_flag === true) {
                var ks_advance_search_params = {};
                ks_advance_search_params["modelName"] = self.props.resModel;
                ks_advance_search_params["context"] = self.props.context;
                ks_advance_search_params["ids"] = ks_options.res_ids;
                ks_advance_search_params["offset"] = self.props.list.model.root.offset;
                //                    ks_advance_search_params["currentId"] = self.renderer.state.res_id;
                ks_advance_search_params["selectRecords"] = self.props.list.model.root.selection;
                ks_advance_search_params["groupBy"] = self.props.list.model.root.groupBy;
                self.ks_field_domain_list = [];

                for (var j = 0; j < self.ks_key_fields.length; j++) {
                    self.ks_field_domain_list = self.ks_field_domain_list.concat(self.ks_field_domain_dict[self.ks_key_fields[j]]);
                }
                self.ks_remove_popup_flag = false;
                ks_advance_search_params["ksDomain"] = self.ks_field_domain_list;
                if (self.ks_search_domain.length === 0) {
                    self.ksBaseDomain = []
                }
                if (self.ksBaseDomain === null && (self.ksDomain === null || self.ksDomain.length === 0) && self.ks_search_domain.length) {
                    self.ksBaseDomain = self.ks_search_domain
                }
                if (self.ksBaseDomain.length !== 0 || self.ks_field_domain_list.length !== 0) {
                    ks_advance_search_params["domain"] = self.ksBaseDomain.concat(self.ks_field_domain_list)
                } else {
                    ks_advance_search_params["domain"] = []
                }
                self.ksDomain = ks_advance_search_params["ksDomain"]
                self.mydomain = ks_advance_search_params["ksDomain"]
                self.ks_update(self.mydomain);

            } else {
                var ks_val_flag = false;
                if (ks_options.ks_val) {
                    ks_val_flag = ks_options.ks_val.trim() !== 0
                } else {
                    if (ks_options.ksfieldtype == "selection") {
                        ks_val_flag = $(".custom-control-searchbar-change[data-name=" + ks_options.KsSearchId + "]").val().trim() !== 0
                    } else {
                        ks_val_flag = $(".custom-control-searchbar-advance[data-name=" + ks_options.KsSearchId + "]").val() !== 0
                    }
                }

                if (Number(ks_val_flag)) {
                    self.ks_advance_search_refresh = true;
                    if (ks_options.ksfieldtype == "selection") {
                        var ks_search_value = ks_options.ks_val || $(".custom-control-searchbar-change[data-name=" + ks_options.KsSearchId + "]").val();
                    } else {
                        if(ks_options.KsSearchId === "level_progress"){
                            var ks_search_value = (ks_options.ks_val || $(".custom-control-searchbar-advance[data-name=" + ks_options.KsSearchId + "]").val())/100;
                        }else{
                        var ks_search_value = ks_options.ks_val || $(".custom-control-searchbar-advance[data-name=" + ks_options.KsSearchId + "]").val();
                        }
                    }
                    //                        var ks_search_value = ks_options.data.ks_val || $(".custom-control-searchbar-advance[data-name=" + ks_options.data.KsSearchId + "]").val();
                    var ks_advance_search_type = ks_options.ksfieldtype;
                    var ks_selection_values = [];
                    var ks_advance_search_params = {};
                    self.ks_field_domain_list = [];
                    self.ks_key_insert_flag = false;
                    var ks_data_insert_flag = false;
                    var ks_value = ks_options.KsSearchId.split("_lvm_start_date")
                    ks_advance_search_params["groupBy"] = self.props.list.model.root.groupBy
                    ks_advance_search_params["modelName"] = self.props.resModel;
                    ks_advance_search_params["context"] = self.props.context;
                    ks_advance_search_params["ids"] = ks_options.res_ids;
                    ks_advance_search_params["offset"] = self.props.list.model.root.offset;
                    //                        ks_advance_search_params["currentId"] = self.renderer.state.res_id;
                    ks_advance_search_params["selectRecords"] = self.props.list.model.root.selection

                    if (ks_value.length === 1) {
                        ks_value = ks_options.KsSearchId.split("_lvm_end_date")
                        if (ks_value.length === 2)
                            ks_options.KsSearchId = ks_value[0];
                    } else {
                        ks_options.KsSearchId = ks_value[0];
                    }

                    for (var ks_sel_check = 0; ks_sel_check < self.ks_key_fields.length; ks_sel_check++) {
                        if (ks_options.KsSearchId === self.ks_key_fields[ks_sel_check]) {
                            ks_data_insert_flag = true;
                        }
                    }

                    if ((ks_data_insert_flag === false) || (ks_data_insert_flag === true && (ks_advance_search_type === "many2one" || ks_advance_search_type === "many2many" || ks_advance_search_type === "char"))) {
                        if (!(ks_advance_search_type === "datetime" || ks_advance_search_type === "date")) {
                            if (this.ks_key_fields.length === 0) {
                                if (ks_advance_search_type === 'monetary' || ks_advance_search_type === 'integer' || ks_advance_search_type === 'float') {
                                    try {
                                        //Fixme currency
                                        var currency = getCurrency(self.props.list_data.currency);
                                        var parsed_value = parseFloat(ks_search_value);
                                        if (isNaN(parsed_value)) {
                                            throw new Error('Invalid number');
                                        }
//                                        var formatted_value = formatFloat(parsed_value || 0, {
//                                            digits: currency && currency.digits
//                                        });
                                        ks_search_value = parsed_value
                                        self.ks_key_fields.push(ks_options.KsSearchId);
                                    } catch {
                                        this.env.services.notification.add(_t("Please enter a valid number"), {
                                            title: _t("Notification"),
                                            sticky: false,
                                            type: "info",
                                        });
                                    }
                                } else {
                                    self.ks_key_fields.push(ks_options.KsSearchId);
                                }
                            } else {
                                for (var key_length = 0; key_length < self.ks_key_fields.length; key_length++) {
                                    if ((self.ks_key_fields[key_length] === ks_options.KsSearchId)) {
                                        self.ks_key_insert_flag = true;
                                        break;
                                    }
                                }
                                if (!(self.ks_key_insert_flag)) {
                                    if (ks_advance_search_type === 'monetary' || ks_advance_search_type === 'integer' || ks_advance_search_type === 'float') {
                                        try {
                                            // Fixme currency
                                             var currency = getCurrency(self.props.list_data.currency);
                                             var parsed_value = parseFloat(ks_search_value);
                                             if (isNaN(parsed_value)) {
                                                throw new Error('Invalid number');
                                             }
//                                             var formatted_value = formatFloat(parsed_value || 0, {
//                                                digits: currency && currency.digits
//                                             });
                                             ks_search_value = parsed_value
                                             self.ks_key_fields.push(ks_options.KsSearchId);
                                        } catch {
                                            this.env.services.notification.add(_t("Please enter a valid number"), {
                                                title: _t("Notification"),
                                                sticky: false,
                                                type: "info",
                                            });
                                        }
                                    } else {
                                        self.ks_key_fields.push(ks_options.KsSearchId);
                                    }
                                }
                            }
                        }

                        if (ks_advance_search_type === "datetime" || ks_advance_search_type === "date") {
                            if (ks_options.ksFieldIdentity === ks_options.KsSearchId + '_lvm_start_date lvm_start_date') {
                                self.ks_start_date = ks_search_value;
                                self.ks_start_date_id = ks_options.KsSearchId;
                            } else {
                                self.ks_end_date = ks_search_value;
                                self.ks_end_date_id = ks_options.KsSearchId
                            }

                            if (ks_advance_search_type === "datetime" || ks_advance_search_type === "date") {
                                if (ks_options.ksFieldIdentity === ks_options.KsSearchId + '_lvm_end_date lvm_end_date') {
                                    if (self.ks_start_date_id === self.ks_end_date_id) {
                                        self.ks_field_domain_dict[self.ks_start_date_id] = [
                                            [self.ks_start_date_id, '>=', self.ks_start_date],
                                            [self.ks_end_date_id, '<=', self.ks_end_date]
                                        ]
                                        if (self.ks_key_fields.length === 0) {
                                            self.ks_key_fields.push(self.ks_start_date_id);
                                        } else {
                                            for (var key_length = 0; key_length < self.ks_key_fields.length; key_length++) {
                                                if (!(self.ks_key_fields[key_length] === ks_options.KsSearchId)) {
                                                    self.ks_key_fields.push(self.ks_start_date_id);
                                                    break;
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        } else if (ks_advance_search_type === 'selection') {
                            if (ks_search_value === "Select a Selection") {
                                for (var j = 0; j < self.ks_key_fields.length; j++) {
                                    self.ks_field_domain_list = self.ks_field_domain_list.concat(self.ks_field_domain_dict[self.ks_key_fields[j]]);
                                }
                                ks_advance_search_params["ksDomain"] = self.ks_field_domain_list;
                                if (self.ks_search_domain.length === 0) {
                                    self.ksBaseDomain = []
                                }
                                ks_advance_search_params["domain"] = self.ksBaseDomain.concat(self.ks_field_domain_list)
                                self.ksDomain = ks_advance_search_params["ksDomain"]
                                self.mydomain = ks_advance_search_params["ksDomain"]
                                self.ks_update(self.mydomain);
                                //                                    self.update(ks_advance_search_params, undefined);
                            } else {

                                // obtaining values of selection
                                ks_selection_values = self.props.list.fields[ks_options.KsSearchId].selection;

                                //setting values for selection
                                for (var i = 0; i < ks_selection_values.length; i++) {
                                    if (ks_selection_values[i][1] === ks_search_value) {
                                        ks_search_value = ks_selection_values[i][0];
                                    }
                                }
                                self.ks_field_domain_dict[ks_options.KsSearchId] = [
                                    [ks_options.KsSearchId, '=', ks_search_value]
                                ]
                            }
                        } else if (ks_advance_search_type === "many2one" || ks_advance_search_type === "many2many") {
                            if (self.ks_field_domain_dict[ks_options.KsSearchId] === undefined)
                                self.ks_field_domain_dict[ks_options.KsSearchId] = [
                                    [ks_options.KsSearchId, "ilike", ks_search_value]
                                ]
                            else
                                self.ks_field_domain_dict[ks_options.KsSearchId].push([ks_options.KsSearchId, "ilike", ks_search_value])

                            if (self.ks_field_domain_dict[ks_options.KsSearchId].length > 1) {
                                self.ks_field_domain_dict[ks_options.KsSearchId].unshift("|")
                            }
                            //                                ks_advance_search_params["ids"] = self.initialState.res_id;
                        } else if (ks_advance_search_type === 'monetary' || ks_advance_search_type === 'integer' || ks_advance_search_type === 'float') {
                            self.ks_field_domain_dict[ks_options.KsSearchId] = [
                                [ks_options.KsSearchId, '=', ks_search_value]
                            ]

                        }
                        else if (ks_advance_search_type === 'char') {
                            if (self.ks_field_domain_dict[ks_options.KsSearchId] === undefined) {
                                self.ks_field_domain_dict[ks_options.KsSearchId] = [
                                    [ks_options.KsSearchId, 'ilike', ks_search_value]
                                ]
                            }
                            else { self.ks_field_domain_dict[ks_options.KsSearchId].push([ks_options.KsSearchId, 'ilike', ks_search_value]) }
                            if (self.ks_field_domain_dict[ks_options.KsSearchId].length > 1) {
                                self.ks_field_domain_dict[ks_options.KsSearchId].unshift("|")
                            }
                        }

                        else {
                            self.ks_field_domain_dict[ks_options.KsSearchId] = [
                                [ks_options.KsSearchId, "ilike", ks_search_value]
                            ]
                        }

                        if (ks_advance_search_type === "datetime" || ks_advance_search_type === "date") {
                            if (ks_options.ksFieldIdentity === ks_options.KsSearchId + '_lvm_end_date lvm_end_date') {
                                for (var j = 0; j < self.ks_key_fields.length; j++) {
                                    this.ks_field_domain_list = self.ks_field_domain_list.concat(self.ks_field_domain_dict[self.ks_key_fields[j]]);
                                }
                                ks_advance_search_params["ksDomain"] = self.ks_field_domain_list;
                                if (self.ks_search_domain.length === 0) {
                                    self.ksBaseDomain = []
                                }
                                ks_advance_search_params["domain"] = self.ksBaseDomain.concat(self.ks_field_domain_list)
                                self.ksDomain = ks_advance_search_params["ksDomain"]
                                self.mydomain = ks_advance_search_params["ksDomain"]
                                self.ks_update(self.mydomain);
                                // Fixme update
                                //                                    self.update(ks_advance_search_params, undefined);
                                self.ks_start_date = undefined;
                                self.ks_end_date = undefined;
                                self.ks_start_date_id = undefined;
                                self.ks_end_date_id = undefined;
                            }
                        } else {
                            if (ks_advance_search_type === 'monetary' || ks_advance_search_type === 'integer' || ks_advance_search_type === 'float') {
                                if (!(isNaN(ks_search_value))) {
                                    for (var j = 0; j < self.ks_key_fields.length; j++) {
                                        self.ks_field_domain_list = self.ks_field_domain_list.concat(self.ks_field_domain_dict[self.ks_key_fields[j]]);
                                    }
                                    ks_advance_search_params["ksDomain"] = self.ks_field_domain_list;
                                    if (self.ks_search_domain.length === 0) {
                                        self.ksBaseDomain = []
                                    }
                                    ks_advance_search_params["domain"] = self.ksBaseDomain.concat(self.ks_field_domain_list)
                                    self.ksDomain = ks_advance_search_params["ksDomain"]
                                    self.mydomain = ks_advance_search_params["ksDomain"]
                                    self.ks_update(self.mydomain);
                                    // FIXME update
                                    //                                        self.update(ks_advance_search_params, undefined);
                                } else {
                                    if (self.ks_search_domain.length === 0) {
                                        self.ksBaseDomain = []
                                    }
                                    ks_advance_search_params["domain"] = self.ksDomain || []
                                    self.mydomain = ks_advance_search_params["domain"]
                                    self.ks_update(self.mydomain);
                                    // Fixme update
                                    //                                        self.update(ks_advance_search_params, undefined);
                                }
                            } else {
                                for (var j = 0; j < self.ks_key_fields.length; j++) {
                                    self.ks_field_domain_list = self.ks_field_domain_list.concat(self.ks_field_domain_dict[self.ks_key_fields[j]]);
                                }
                                ks_advance_search_params["ksDomain"] = self.ks_field_domain_list;
                                if (self.ks_search_domain.length === 0) {
                                    self.ksBaseDomain = []
                                }
                                ks_advance_search_params["domain"] = self.ksBaseDomain.concat(self.ks_field_domain_list)
                                self.ksDomain = ks_advance_search_params["ksDomain"];
                                self.mydomain = ks_advance_search_params["ksDomain"]
                                self.ks_update(self.mydomain);
                                // Fixme update
                                //                                    self.update(ks_advance_search_params, undefined);
                            }
                        }
                    } else {
                        for (var j = 0; j < self.ks_key_fields.length; j++) {
                            self.ks_field_domain_list = self.ks_field_domain_list.concat(self.ks_field_domain_dict[self.ks_key_fields[j]]);
                        }
                        ks_advance_search_params["ksDomain"] = self.ks_field_domain_list;
                        if (self.ks_search_domain.length === 0) {
                            self.ksBaseDomain = []
                        }
                        ks_advance_search_params["domain"] = self.ksBaseDomain.concat(self.ks_field_domain_list)
                        self.ksDomain = ks_advance_search_params["ksDomain"]
                        self.mydomain = ks_advance_search_params["ksDomain"]
                        self.ks_update(self.mydomain);
                        // Fixme update
                        //                            self.update(ks_advance_search_params, undefined);
                    }
                } else {
                    self.ks_advance_search_refresh = true;
                    //                        var ks_search_value = $('#' + ks_options.data.KsSearchId).val().trim();
                    if (ks_options.ksfieldtype == "selection") {
                        var ks_search_value = $(".custom-control-searchbar-change[data-name=" + ks_options.KsSearchId + "]").val().trim();
                    } else {
                        var ks_search_value = $(".custom-control-searchbar-advance[data-name=" + ks_options.KsSearchId + "]").val();
                    }
                    //                        var ks_search_value = $(".custom-control-searchbar-advance[data-name=" + ks_options.data.KsSearchId + "]").val().trim();
                    var ks_advance_search_type = ks_options.ksfieldtype;
                    var ks_selection_values = [];
                    var ks_advance_search_params = {};
                    self.ks_field_domain_list = [];
                    self.ks_key_insert_flag = false;
                    var ks_data_insert_flag = false;
                    var ks_value = ks_options.KsSearchId.split("_lvm_start_date")

                    ks_advance_search_params["modelName"] = self.props.list.resModel;
                    ks_advance_search_params["context"] = self.props.context;
                    ks_advance_search_params["ids"] = ks_options.res_ids;
                    ks_advance_search_params["offset"] = self.props.list.model.root.offset;
//                    ks_advance_search_params["currentId"] = self.renderer.state.res_id;
                    ks_advance_search_params["selectRecords"] = self.props.list.model.root.selection;
                    ks_advance_search_params["groupBy"] = [];

                    for (var j = 0; j < self.ks_key_fields.length; j++) {
                        self.ks_field_domain_list = self.ks_field_domain_list.concat(self.ks_field_domain_dict[self.ks_key_fields[j]]);
                    }
                    ks_advance_search_params["ksDomain"] = self.ks_field_domain_list;
                    if (self.ks_search_domain.length === 0) {
                        self.ksBaseDomain = []
                    }
                    ks_advance_search_params["domain"] = self.ksBaseDomain.concat(self.ks_field_domain_list)
                    self.ksDomain = ks_advance_search_params["ksDomain"]
                    self.mydomain = ks_advance_search_params["ksDomain"]
                    self.ks_update(self.mydomain);

                }
            }
        }
    },

        async ks_update(data) {
//    this.props.ks_renderer_update(data);
        const list = this.props.list.model.root;
//        list.domain = []
        this.ks_search_domain  = [];
        var browser_search_domain =[];
        this.env.searchModel.globalDomain = [];
        for (let item of this.default_domain){
            if (item != undefined){
                this.ks_search_domain.push(item);
            }
        }
        for (let items of this.search_default){
            if (items != undefined){
                this.env.searchModel.globalDomain.push(items);
            }
        }
        for(let ks_domain of data){
            if (ks_domain != undefined){
//                list.domain.push(ks_domain);
                this.env.searchModel.globalDomain.push(ks_domain);
                this.ks_search_domain.push(ks_domain)
//                browser_search_domain.push(ks_domain)
            }
        }
//        browser.localStorage.setItem("ks_actionid",this.env.config.actionId);
//        browser.localStorage.setItem("search_domain",JSON.stringify(browser_search_domain));
//        browser.localStorage.setItem("ks_model",list.resModel);
//        browser.localStorage.setItem("field_dict",JSON.stringify(this.ks_field_domain_dict));
//        browser.localStorage.setItem("key_field",JSON.stringify(this.ks_key_fields));
        await this.env.searchModel._notify();

        },

        ks_remove_popup_domain_event(e,field_type,field) {
        if ($(e.target).hasClass("ks_remove_popup")) {

            var div = e.target.closest('.ks_inner_search')
            let ks_date_element = e.target.parentElement.parentElement
            let ks_end_date_el = `#end_date_${field}`
            let ks_start_date_el = `#start_date_${field}`
            if (field_type == "date" || field_type == "datetime"){
                $(ks_end_date_el)?.addClass('d-none');
                $(ks_start_date_el)?.removeClass('ks_date_main')
//                $("#input_start_val").removeClass("d-none")
//                $("#input_end_val").removeClass("d-none")
            }
            var ks_remove_options = {
                ksDiv: div,
                ksfieldtype: e.target.parentElement.parentElement.children[1].dataset.fieldType || field_type
            };
            this.ks_remove_popup_domain(ks_remove_options);
        }
    },

        ks_remove_popup_domain(ks_options) {
        if (this.ks_lvm_mode) {
            var self = this;
            var ks_i;
            var key;
            var key_array;

            if (ks_options.ksDiv !== undefined) {
                key_array = ks_options.ksDiv.id.split("_value")
                key = key_array[0];
                if(key === 'product_template_variant'){
                    key = key+'_value'+'_ids'
                }
            } else {
                key = event.target.id;
            }

            if (self.ks_field_domain_dict[key] !== undefined) {
                if (self.ks_field_domain_dict[key].length === 1 || ks_options.ksfieldtype === "date" || ks_options.ksfieldtype === "datetime") {
                    delete self.ks_field_domain_dict[key]
                    for (ks_i = 0; ks_i < self.ks_key_fields.length; ks_i++) {
                        if (key === self.ks_key_fields[ks_i]) {
                            break;
                        }
                    }

                    if (ks_options.ksDiv !== undefined) {
//                        $("#" + ks_options.ksDiv.id).remove()
                    } else {
                        // fixme
                        //                            $("#" + $(ks_options.event.target).parent().children()[$(ks_options.data.event.target).parent().children().length - 2].id).remove();
                    }

                    self.ks_key_fields.splice(ks_i, 1);
                    self.ks_remove_popup_flag = true;
                    self.Ks_update_advance_search_controller(false);
                } else {
                    for (var j = 0; j < self.ks_field_domain_dict[key].length; j++) {
                        if (self.ks_field_domain_dict[key][j] !== '|') {
                            if (ks_options.ksDiv !== undefined) {
                                if (self.ks_field_domain_dict[key][j][2] === ks_options.ksDiv.innerText) {
                                    self.ks_field_domain_dict[key].splice(j, 1)
                                    self.ks_field_domain_dict[key].splice(0, 1);
                                    break;
                                }

                            } else {
                                self.ks_field_domain_dict[key].splice(j, 1)
                                self.ks_field_domain_dict[key].splice(0, 1);
                                break;
                            }
                        }
                    }
                    if (ks_options.ksDiv !== undefined) {
//                        $("#" + ks_options.ksDiv.id).remove()
                    } else {
                        //fixme
                        //                            $("#" + $(ks_options.data.event.target).parent().children()[$(ks_options.data.event.target).parent().children().length - 2].id).remove();
                    }
                    self.ks_remove_popup_flag = true;
                    self.Ks_update_advance_search_controller(false);
                }
            } else {
                self.ks_remove_popup_flag = true;
                self.Ks_update_advance_search_controller(false);
            }
        }
    },

        getRowClass(record) {
            var classNames = super.getRowClass(...arguments);
            if (this.props.list.selection && this.props.list.selection.length > 0) {
                $('.copy_button').css('display', 'block')
            } else {
                $('.copy_button').css('display', 'none');
            }
            if (record.selected) {
                $('.o_data_row[data-id="' + record.id + '"]').addClass('ks_highlight_row');
                classNames = "o_data_row_selected"
            }else{
            $('.o_data_row[data-id="' + record.id + '"]').removeClass('ks_highlight_row');
            }
            return classNames;
        },

    toggleSelection() {
        super.toggleSelection(...arguments);
        if (this.props.list.selection && this.props.list.selection.length === 0) {
            $('.o_data_row').removeClass('ks_highlight_row');
            $('.o_data_row').addClass('text-info');
        }
    },

    toggleRecordSelection(record) {
        super.toggleRecordSelection(...arguments);
        if (!record.selected) {
            $('.o_data_row[data-id="' + record.id + '"]').removeClass('ks_highlight_row');
            $('.o_data_row[data-id="' + record.id + '"]').addClass('text-info');
        }
    },
    onClickCapture(record, ev) {
        super.onClickCapture(...arguments);
        if ($(ev.currentTarget).hasClass("ks_highlight_row")){
            $(document.querySelectorAll(".ks_highlight_row")).removeClass("ks_highlight_row")
        }
    },

    async onCellClicked(record, column, ev) {
    if (this.ks_is_lines){
        super.onCellClicked(...arguments);
    }
    if (this.props.activeActions.type == 'view'){
        if (window.getSelection().toString() && this.props.activeActions.type == 'view') {
            return;
        }
        if (this.ks_list_data){
            if (this.ks_lvm_mode && this.ks_list_data.table_data.ks_editable && this.props.activeActions.type == 'view') {
                if (ev.target.special_click) {
                    return;
                }
                const recordAfterResequence = async () => {
                    const recordIndex = this.props.list.records.indexOf(record);
                    await this.resequencePromise;
                    // row might have changed record after resequence
                    record = this.props.list.records[recordIndex] || record;
                };
                if (record.isInEdition && this.props.list.editedRecord === record) {
                    this.focusCell(column);
                    this.cellToFocus = null;
                } else {
                    await recordAfterResequence();
                    await record.switchMode("edit");
                    this.cellToFocus = { column, record };
                }

            } else {
                super.onCellClicked(...arguments);
            }
            }else{
                super.onCellClicked(...arguments);
            }
        }
},

  });

  ListRenderer.components = { ...ListRenderer.components , SearchView };


ListRenderer.props = [...ListRenderer.props,
    "Ks_update_field_data?",
    "Ks_initialize_lvm_data?",
    "list_data?",
];
