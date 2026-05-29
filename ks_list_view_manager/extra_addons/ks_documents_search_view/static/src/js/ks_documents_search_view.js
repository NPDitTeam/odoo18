/** @odoo-module **/
import { SearchView } from "@ks_list_view_manager/component/search_view";
import { DocumentsListRenderer } from "@documents/views/list/documents_list_renderer";


DocumentsListRenderer.components = {
            ...DocumentsListRenderer.components,
            SearchView

};

