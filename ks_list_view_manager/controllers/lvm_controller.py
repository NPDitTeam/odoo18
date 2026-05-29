import json

from odoo import http
import logging

_logger = logging.getLogger(__name__)
from odoo.http import request
from odoo.addons.web.controllers.dataset import DataSet
from lxml import etree as etree



class LvmController(DataSet, http.Controller):

    @http.route(['/web/dataset/call_kw', '/web/dataset/call_kw/<path:path>'], type='json', auth="user")
    def call_kw(self, model, method, args, kwargs, path=None):
        call_kw_result = super(LvmController, self).call_kw(model, method, args, kwargs, path)
        if method == "get_views" and call_kw_result.get('views').get('list'):
            ks_list_view_id = call_kw_result["views"]["list"].get("id")

            self.ks_prepare_lvm_list_data(call_kw_result, model, ks_list_view_id)
        return call_kw_result

    def ks_prepare_lvm_list_data(self, original_list_data, model, ks_list_view_id):
        list_view_data = original_list_data.get('views').get('list')

        if ks_list_view_id:
            list_view_data['ks_lvm_user_data'] = self.ks_fetch_lvm_data(model, ks_list_view_id)

            if list_view_data['ks_lvm_user_data']['ks_lvm_user_table_result']['ks_fields_data']:
                self.ks_process_arch(list_view_data, original_list_data.get('models')[model])
        else:
            user_mode_data = request.env['user.mode'].check_user_mode(model, request.env.user.id, False)
            user_mode_data['ks_can_advanced_search'] = False
            user_mode_data['ks_can_edit'] = False
            user_mode_data['ks_can_duplicate'] = False
            user_mode_data['ks_dynamic_list_show'] = False
            ks_lvm_user_data = {
                'ks_lvm_user_mode_data': user_mode_data
            }
            list_view_data['ks_lvm_user_data'] = ks_lvm_user_data

    def ks_fetch_lvm_data(self, model, ks_view_id=False):
        ks_lvm_user_data = {}
        user_mode_model = request.env['user.mode']
        user_specific_model = request.env['user.specific']

        user_mode_data = user_mode_model.check_user_mode(model, request.env.user.id, ks_view_id)
        ks_user_table_result = user_specific_model.check_user_exists(model, request.env.user.id, ks_view_id)

        ks_lvm_user_data['ks_lvm_user_table_result'] = ks_user_table_result
        ks_lvm_user_data['ks_lvm_user_mode_data'] = user_mode_data
        ks_lvm_user_data['ksViewID'] = ks_view_id
        return ks_lvm_user_data

    @http.route('/ks_lvm_control/user_lvm_data', type='json', auth="user")
    def ks_fetch_lvm_data_controller(self, model, ks_view_id=False):
        return self.ks_fetch_lvm_data(model, ks_view_id)

    @http.route('/ks_lvm_control/update_list_view_data', type='json', auth="user")
    def update_list_view_data(self, ks_table_data, ks_fields_data, ks_fetch_options):
        for ks_table in ks_table_data:
            request.env['user.specific'].browse(ks_table.get('id')).write(ks_table)

        for ks_field in ks_fields_data:
            request.env['user.fields'].browse(ks_field.get('id')).write(ks_field)

        if ks_fetch_options:
            return self.ks_generate_arch_view(ks_fetch_options.get('ks_context'),ks_fetch_options.get('ks_model'), ks_fetch_options.get('ks_view_id'),ks_fetch_options.get('ks_search_id'))

    @http.route('/ks_lvm_control/ks_generate_arch_view', type='json', auth="user")
    def ks_generate_arch_view(self, ks_context, ks_model, ks_view_id, ks_search_id):
        ks_view_data = request.env[ks_model].with_context(ks_context).get_views([(ks_view_id, 'list'),(ks_search_id,'search')],{})
        self.ks_prepare_lvm_list_data(ks_view_data, ks_model, ks_view_id)
        return ks_view_data

    @http.route('/ks_lvm_control/create_list_view_data', type='json', auth="user")
    def create_list_view_data(self, ks_context,ks_model, ks_editable, ks_view_id, ks_table_width_per, ks_fields_data,ks_search_id):
        list_view_record = request.env['user.specific'].create({
            'model_name': ks_model,
            'user_id': request.env.uid,
            'ks_action_id': ks_view_id,
            'ks_table_width': ks_table_width_per,
            'ks_editable': ks_editable,
        })

        for rec in ks_fields_data.values():
            rec.update({"fields_list": list_view_record.id})
            request.env['user.fields'].create(rec)

        return self.ks_generate_arch_view(ks_context,ks_model, ks_view_id,ks_search_id)
        # Removing Fields that are not in view anymore

    def check_fields(self, table_id, fields_list, ks_field_list):
        for r_field in filter(lambda x: x not in [x for x in fields_list.keys()], [x['field_name'] for x in ks_field_list.values()]):
            field_rec = ks_field_list.pop(r_field)
            request.env['user.fields'].browse(field_rec.get('id', 0)).sudo().unlink()

        for field in filter(lambda x: not ks_field_list.get(x, False), fields_list.keys()):
            ks_field_list[field] = val = {
                "ks_columns_name": fields_list[field]['string'],
                "ksShowField": False,
                "field_name": field,
                "ks_width": 0,
                "ks_field_order": len(ks_field_list)
            }
            val.update({'fields_list': table_id})
            rec_id = request.env['user.fields'].create(val)
            ks_field_list[field]['id'] = rec_id.id

    def ks_process_arch(self, list_view_data, fields_list):

        parser = etree.XMLParser(remove_comments=True)
        node = etree.fromstring(list_view_data['arch'], parser=parser)

        ks_node_dict = {
            idx: child for idx, child in enumerate(node.getchildren())
            if child.tag == 'button'
        }

        ks_field_list = list_view_data['ks_lvm_user_data']['ks_lvm_user_table_result']['ks_fields_data']


        if list_view_data['ks_lvm_user_data']['ks_lvm_user_mode_data']['ks_can_edit']:
            if list_view_data['ks_lvm_user_data']['ks_lvm_user_table_result']['ks_table_data']['ks_editable']:
                node.set('editable', 'top')
            elif node.get("editable"):
                node.attrib.pop("editable")

        # Dynamic List Access
        ks_has_dynamic_list_access = request.env.user.has_group(
            'ks_list_view_manager.ks_list_view_manager_dynamic_list')
        if ks_has_dynamic_list_access:
            existing_fields = {field_node.get("name") for field_node in node.getchildren() if field_node.tag == 'field'}

            for field_node in node.getchildren():
                if field_node.tag == 'field':
                    field_name = field_node.get("name")
                    if field_name in ks_field_list:
                        ks_field_data = ks_field_list[field_name]
                        if ks_field_data.get("ksShowField"):
                            if field_node.get('column_invisible', False) and field_node.get('column_invisible') not in  [1, True, 'True', '1']:
                                field_node.set('column_invisible', field_node.get('column_invisible'))
                                column_invisible_value = field_node.get('column_invisible')
                                if column_invisible_value and 'context.get' in column_invisible_value:
                                    field_node.set('column_invisible', field_node.get('column_invisible'))
                            else:
                                field_node.set('column_invisible', '0')

                            if field_node.get('string', False):
                                field_node.set('string', ks_field_data.get('ks_columns_name') or field_node.get('string'))
                            else:
                                field_node.set('string', ks_field_data.get('ks_columns_name', field_name))
                            if 'optional' in field_node.attrib:
                                field_node.attrib.pop('optional')
                            if (field_node.attrib.get('widget') != 'image'):
                                field_node.attrib['width'] = ks_field_list[field_name]['ks_width']
                        else:
                            field_node.set('column_invisible', '1')
                            field_node.set('optional', 'hide')
                            if (field_node.attrib.get('widget') != 'image'):
                                field_node.attrib['width'] = ks_field_list[field_name]['ks_width']

            for field_name, field_data in ks_field_list.items():
                if field_name not in existing_fields and field_data.get("ksShowField"):
                    new_field = etree.Element('field', attrib={
                        'name': field_name,
                        'string': field_data.get('ks_columns_name', field_name),
                        'column_invisible': '0',
                    })
                    node.append(new_field)

            sorted_fields = sorted(
                [f for f in node.getchildren() if f.tag == 'field' and f.get("name") in ks_field_list],
                key=lambda f: ks_field_list[f.get("name")]['ks_field_order']
            )

            for field in sorted_fields:
                node.remove(field)
                node.append(field)

        for idx, btn_node in ks_node_dict.items():
            node.insert(idx, btn_node)

        # Convert back to XML
        list_view_data['arch'] = etree.tostring(node, pretty_print=True, encoding='unicode')

    @http.route('/ks_lvm_control/ks_reset_list_view_data', type='json', auth="user")
    def ks_reset_list_view_data(self, ks_context,ks_model, ks_view_id, ks_lvm_table_id, ks_search_view_id):
        ks_lvm_user_specific = request.env['user.specific'].browse(ks_lvm_table_id)
        ks_lvm_user_specific.fields.sudo().unlink()
        ks_lvm_user_specific.sudo().unlink()


        ks_view_data = request.env[ks_model].with_context(ks_context).get_views([(ks_view_id, 'list'),(ks_search_view_id, 'search')])

        # ks_view_data['fields'].update(ks_view_data.get('models')[ks_model])
        # ks_view_data.get('models')[ks_model] = ks_view_data['fields']
        self.ks_prepare_lvm_list_data(ks_view_data, ks_model, ks_view_id)
        return ks_view_data
