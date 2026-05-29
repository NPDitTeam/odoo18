/** @odoo-module **/
import { SearchView } from "@ks_list_view_manager/component/search_view";
import {ExpenseListRenderer} from "@hr_expense/views/list";
import {ExpenseDashboardListRenderer} from"@hr_expense/views/list";
import {PurchaseDashBoardRenderer} from "@purchase/views/purchase_listview";
import {AccountMoveListRenderer} from "@account/views/account_move_list/account_move_list_renderer";
import {SaleListRenderer} from "@sale/views/sale_onboarding_list/sale_onboarding_list_renderer";
import {FileUploadListRenderer} from "@account/views/file_upload_list/file_upload_list_renderer";
import {StockListRenderer} from "@stock/views/stock_empty_list_help";
import { AutoColumnWidthListRenderer } from "@stock/views/list/auto_column_width_list_renderer";

  AccountMoveListRenderer.components = {...AccountMoveListRenderer.components,SearchView};
  FileUploadListRenderer.components = {...FileUploadListRenderer.components,SearchView};
  ExpenseListRenderer.components = {...ExpenseListRenderer.components,SearchView};
  ExpenseDashboardListRenderer.components = {...ExpenseDashboardListRenderer.components,SearchView};
  PurchaseDashBoardRenderer.components = {...PurchaseDashBoardRenderer.components,SearchView};
  SaleListRenderer.components = {...SaleListRenderer.components,SearchView};
  StockListRenderer.components = {...StockListRenderer.components,SearchView};

  ExpenseListRenderer.props = [...ExpenseListRenderer.props,
    "Ks_update_field_data?",
    "Ks_initialize_lvm_data?",
    "list_data?",
];

AutoColumnWidthListRenderer.props = [...AutoColumnWidthListRenderer.props,
    "Ks_update_field_data?",
    "Ks_initialize_lvm_data?",
    "list_data?",
];

