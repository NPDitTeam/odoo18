/** @odoo-module **/
import { useDebounced } from "@web/core/utils/timing";
import { useComponent, useEffect, useExternalListener } from "@odoo/owl";

const DEFAULT_MIN_WIDTH = 80;
const SELECTOR_WIDTH = 20;
const OPEN_FORM_VIEW_BUTTON_WIDTH = 54;
const DELETE_BUTTON_WIDTH = 12;
const FIELD_WIDTHS = {
    boolean: [20, 100], // [minWidth, maxWidth]
    char: [80], // only minWidth, no maxWidth
    date: 80, // minWidth = maxWidth
    datetime: 145,
    float: 93,
    integer: 71,
    many2many: [80],
    many2one_reference: [80],
    many2one: [80],
    monetary: 105,
    one2many: [80],
    reference: [80],
    selection: [80],
    text: [80, 1200],
};



function kscomputeWidths(table, state, allowedWidth, startingWidths) {
    let _columnWidths;
    const headers = [...table.querySelectorAll("thead .bg-primary th")];
    const columns = state.columns;

    // Starting point: compute widths
    if (startingWidths) {
        _columnWidths = startingWidths.slice();
    } else if (state.isEmpty) {
        // Table is empty => uniform distribution as starting point
        _columnWidths = headers.map(() => allowedWidth / headers.length);
    } else {
        // Table contains records => let the browser compute ideal widths
        // Set table layout auto and remove inline style
        table.style.tableLayout = "auto";
        headers.forEach((th) => {
            th.style.width = null;
        });
        // Toggle a className used to remove style that could interfere with the ideal width
        // computation algorithm (e.g. prevent text fields from being wrapped during the
        // computation, to prevent them from being completely crushed)
        table.classList.add("o_list_computing_widths");
        _columnWidths = headers.map((th) => th.getBoundingClientRect().width);
        table.classList.remove("o_list_computing_widths");
    }

    // Force columns to comply with their min and max widths
    if (state.hasSelectors) {
        _columnWidths[0] = SELECTOR_WIDTH;
    }
    if (state.hasOpenFormViewColumn) {
        const index = _columnWidths.length - (state.hasActionsColumn ? 2 : 1);
        _columnWidths[index] = OPEN_FORM_VIEW_BUTTON_WIDTH;
    }
    if (state.hasActionsColumn) {
        _columnWidths[_columnWidths.length - 1] = DELETE_BUTTON_WIDTH;
    }
    const columnWidthSpecs = ksgetWidthSpecs(columns);
    const columnOffset = state.hasSelectors ? 1 : 0;
    const serial = state.ks_serial_number_enable ? 1:0
    for (let columnIndex = 0; columnIndex < columns.length; columnIndex++) {
        const thIndex = columnIndex + columnOffset + serial;
        const { minWidth, maxWidth } = columnWidthSpecs[columnIndex];
        if (_columnWidths[thIndex] < minWidth) {
            _columnWidths[thIndex] = minWidth;
        } else if (maxWidth && _columnWidths[thIndex] > maxWidth) {
            _columnWidths[thIndex] = maxWidth;
        }
    }

    // Expand/shrink columns for the table to fill 100% of available space
    const totalWidth = _columnWidths.reduce((tot, width) => tot + width, 0);
    let diff = totalWidth - allowedWidth;
    if (diff >= 1 && !state.ks_list_data.table_data) {
        // Case 1: table overflows its parent => shrink some columns
        const shrinkableColumns = [];
        let totalAvailableSpace = 0; // total space we can gain by shrinking columns
        for (let columnIndex = 0; columnIndex < columns.length; columnIndex++) {
            const thIndex = columnIndex + columnOffset;
            const { minWidth, canShrink } = columnWidthSpecs[columnIndex];
            if (_columnWidths[thIndex] > minWidth && canShrink) {
                shrinkableColumns.push({ thIndex, minWidth });
                totalAvailableSpace += _columnWidths[thIndex] - minWidth;
            }
        }
        if (diff > totalAvailableSpace) {
            // We can't find enough space => set all columns to their min width, and there'll be an
            // horizontal scrollbar
            for (const { thIndex, minWidth } of shrinkableColumns) {
                _columnWidths[thIndex] = minWidth;
            }
        } else {
            // There's enough available space among shrinkable columns => shrink them uniformly
            let remainingColumnsToShrink = shrinkableColumns.length;
            while (diff >= 1) {
                const colDiff = diff / remainingColumnsToShrink;
                for (const { thIndex, minWidth } of shrinkableColumns) {
                    const currentWidth = _columnWidths[thIndex];
                    if (currentWidth === minWidth) {
                        continue;
                    }
                    const newWidth = Math.max(currentWidth - colDiff, minWidth);
                    diff -= currentWidth - newWidth;
                    _columnWidths[thIndex] = newWidth;
                    if (newWidth === minWidth) {
                        remainingColumnsToShrink--;
                    }
                }
            }
        }
    } else if (diff <= -1) {
        // Case 2: table is narrower than its parent => expand some columns
        diff = -diff; // for better readability
        const expandableColumns = [];
        for (let columnIndex = 0; columnIndex < columns.length; columnIndex++) {
            const thIndex = columnIndex + columnOffset;
            const maxWidth = columnWidthSpecs[columnIndex].maxWidth;
            if (!maxWidth || _columnWidths[thIndex] < maxWidth) {
                expandableColumns.push({ thIndex, maxWidth });
            }
        }
        // Expand all expandable columns uniformly (i.e. at most, expand columns with a maxWidth
        // to their maxWidth)
        let remainingExpandableColumns = expandableColumns.length;
        while (diff >= 1 && remainingExpandableColumns > 0) {
            const colDiff = diff / remainingExpandableColumns;
            for (const { thIndex, maxWidth } of expandableColumns) {
                const currentWidth = _columnWidths[thIndex];
                const newWidth = Math.min(currentWidth + colDiff, maxWidth || Number.MAX_VALUE);
                diff -= newWidth - currentWidth;
                _columnWidths[thIndex] = newWidth;
                if (newWidth === maxWidth) {
                    remainingExpandableColumns--;
                }
            }
        }
        if (diff >= 1) {
            // All columns have a maxWidth and have been expanded to their max => expand them more
            for (let columnIndex = 0; columnIndex < columns.length; columnIndex++) {
                const thIndex = columnIndex + columnOffset;
                _columnWidths[thIndex] += diff / columns.length;
            }
        }
    }
    return _columnWidths;
}

function ksgetWidthSpecs(columns) {
    return columns.map((column) => {
        let minWidth;
        let maxWidth;
        if (column.options && column.attrs.width) {
            minWidth = maxWidth = parseInt(column.attrs.width.split("px")[0]);
        } else {
            let width;
            if (column.type === "field") {
                if (column.field.listViewWidth) {
                    width = column.field.listViewWidth;
                    if (typeof width === "function") {
                        width = width({ type: column.fieldType, hasLabel: column.hasLabel, options: column.options || {}, });
                    }
                } else {
                    width = FIELD_WIDTHS[column.widget || column.fieldType];
                }
            } else if (column.type === "widget") {
                width = column.widget.listViewWidth;
            }
            if (width) {
                minWidth = Array.isArray(width) ? width[0] : width;
                maxWidth = Array.isArray(width) ? width[1] : width;
            } else {
                minWidth = DEFAULT_MIN_WIDTH;
            }
        }
        return { minWidth, maxWidth, canShrink: column.type === "field" };
    });
}

function ksgetHorizontalPadding(el) {
    const { paddingLeft, paddingRight } = getComputedStyle(el);
    return parseFloat(paddingLeft) + parseFloat(paddingRight);
}

export function ksuseMagicColumnWidths(tableRef, getState) {
    const renderer = useComponent();
    let columnWidths = null;
    let allowedWidth = 0;
    let hasAlwaysBeenEmpty = true;
    let hash;
    let _resizing = false;

    /**
     * Apply the column widths in the DOM. If necessary, compute them first (e.g. if they haven't
     * been computed yet, or if columns have changed).
     *
     * Note: the following code manipulates the DOM directly to avoid having to wait for a
     * render + patch which would occur on the next frame and cause flickering.
     */
    function ksforceColumnWidths() {
        const table = tableRef.el;
        const headers = [...table.querySelectorAll("thead .bg-primary th")];
        const state = getState();
        const ksinitialTableWidth = table.getBoundingClientRect().width;

        // Generate a hash to be able to detect when the columns change
        const columns = state.columns;
        // The last part of the hash is there to detect that static columns changed (typically, the
        // selector column, which isn't displayed on small screens)
        const nextHash = `${columns.map((column) => column.id).join("/")}/${headers.length}`;
        if (nextHash !== hash) {
            hash = nextHash;
            resetWidths();
        }
        // If the table has always been empty until now, and it now contains records, we want to
        // recompute the widths based on the records (typical case: we removed a filter).
        // Exception: we were in an empty editable list, and we just added a first record.
        if (hasAlwaysBeenEmpty && !state.isEmpty) {
            hasAlwaysBeenEmpty = false;
            const rows = table.querySelectorAll(".o_data_row");
            if (rows.length !== 1 || !rows[0].classList.contains("o_selected_row")) {
                resetWidths();
            }
        }

        const parentPadding = ksgetHorizontalPadding(table.parentNode);
        const cellPaddings = headers.map((th) => ksgetHorizontalPadding(th));
        const totalCellPadding = cellPaddings.reduce((total, padding) => padding + total, 0);
        const nextAllowedWidth = table.parentNode.clientWidth - parentPadding - totalCellPadding;
        const allowedWidthDiff = Math.abs(allowedWidth - nextAllowedWidth);
        allowedWidth = nextAllowedWidth;

        // When a vertical scrollbar appears/disappears, it may (depending on the browser/os) change
        // the available width. When it does, we want to keep the current widths, but tweak them a
        // little bit s.t. the table fits in the new available space.
        if (!columnWidths || allowedWidthDiff > 0) {
            columnWidths = kscomputeWidths(table, state, allowedWidth, columnWidths);
        }

        // Set the computed widths in the DOM.
        table.style.tableLayout = "fixed";

        headers.forEach((th, index) => {
            th.style.width = `${Math.floor(columnWidths[index] + cellPaddings[index])}px`;
            let width = parseInt(th.style.width);
            if (width < 90) {
                th.style.setProperty("width", "90px", "important");
            }
        });

    }


    /**
     * Resets the widths. After next patch, ideal widths will be recomputed.
     */
    function resetWidths() {
        columnWidths = null;
        // Unset width that might have been set on the table by resizing a column
        tableRef.el.style.width = null;
    }

    /**
     * Handles the resize feature on the column headers
     *
     * @private
     * @param {MouseEvent} ev
     */
    function onStartResize(ev) {
        _resizing = true;
        const table = tableRef.el;
        const th = ev.target.closest("th");
        const handler = th.querySelector(".o_resize");
        table.style.width = `${Math.floor(table.getBoundingClientRect().width)}px`;
        const thPosition = [...th.parentNode.children].indexOf(th);
        const resizingColumnElements = [...table.getElementsByTagName("tr")]
            .filter((tr) => tr.children.length === th.parentNode.children.length)
            .map((tr) => tr.children[thPosition]);
        const initialX = ev.clientX;
        const initialWidth = th.getBoundingClientRect().width;
        const initialTableWidth = table.getBoundingClientRect().width;
        const resizeStoppingEvents = ["keydown", "pointerdown", "pointerup"];

        // Fix the width so that if the resize overflows, it doesn't affect the layout of the parent
        if (!table.parentElement.style.width) {
            table.parentElement.style.width = `${Math.floor(
                table.parentElement.getBoundingClientRect().width
            )}px`;
        }

        // Apply classes to table and selected column
        table.classList.add("o_resizing");
        for (const el of resizingColumnElements) {
            el.classList.add("o_column_resizing");
            handler.classList.add("bg-primary", "opacity-100");
            handler.classList.remove("bg-black-25", "opacity-50-hover");
        }
        // Mousemove event : resize header
        const resizeHeader = (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            const delta = ev.clientX - initialX;
            const newWidth = Math.max(10, initialWidth + delta);
            const tableDelta = newWidth - initialWidth;
            th.style.width = `${Math.floor(newWidth)}px`;
            table.style.width = `${Math.floor(initialTableWidth + tableDelta)}px`;
        };
        window.addEventListener("pointermove", resizeHeader);

        // Mouse or keyboard events : stop resize
        const stopResize = (ev) => {
            _resizing = false;

            // Store current column widths to freeze them
            const headers = [...table.querySelectorAll("thead .bg-primary th")];
            columnWidths = headers.map((th) => {
                return th.getBoundingClientRect().width - ksgetHorizontalPadding(th);
            });

            // Ignores the 'left mouse button down' event as it used to start resizing
            if (ev.type === "pointerdown" && ev.button === 0) {
                return;
            }
            ev.preventDefault();
            ev.stopPropagation();
            let ks_data_width = $(resizingColumnElements[0]).innerWidth();
            var ks_field_data_width = getState().ks_list_data.fields_data[resizingColumnElements[0].dataset.name];
            ks_field_data_width.ks_width =  ks_data_width;

            if (! getState().ks_list_data.table_data && getState().Ks_initialize_lvm_data){
                      getState().Ks_initialize_lvm_data(getState().ks_list_data.fields_data,true);
            }else{
                if (getState().Ks_update_field_data){
                getState().Ks_update_field_data([], [ks_field_data_width], true,true);
             }}

            table.classList.remove("o_resizing");
            for (const el of resizingColumnElements) {
                el.classList.remove("o_column_resizing");
                handler.classList.remove("bg-primary", "opacity-100");
                handler.classList.add("bg-black-25", "opacity-50-hover");
            }

            window.removeEventListener("pointermove", resizeHeader);
            for (const eventType of resizeStoppingEvents) {
                window.removeEventListener(eventType, stopResize);
            }

            // We remove the focus to make sure that the there is no focus inside
            // the tr.  If that is the case, there is some css to darken the whole
            // thead, and it looks quite weird with the small css hover effect.
            document.activeElement.blur();
        };
        // We have to listen to several events to properly stop the resizing function. Those are:
        // - pointerdown (e.g. pressing right click)
        // - pointerup : logical flow of the resizing feature (drag & drop)
        // - keydown : (e.g. pressing 'Alt' + 'Tab' or 'Windows' key)
        for (const eventType of resizeStoppingEvents) {
            window.addEventListener(eventType, stopResize);
        }
    }

    // Side effects
    if (getState().useMagicColumnWidths) {
        useEffect(ksforceColumnWidths);
        const debouncedResizeCallback = useDebounced(() => {
            resetWidths();
            ksforceColumnWidths();
        }, 200,{ immediate: true, trailing: true });

        useExternalListener(window, "resize", debouncedResizeCallback);
        useEffect(() => {
        const parentNode = tableRef.el.parentNode;
        let parentWidth = parentNode.clientWidth;

        const resizeObserver = new ResizeObserver(() => {
            const newParentWidth = parentNode.clientWidth;
            if (newParentWidth === parentWidth) {
                parentWidth = newParentWidth;
                debouncedResizeCallback();
            }
        });

        resizeObserver.observe(parentNode);

        return () => {
            resizeObserver.disconnect();
        };
    });
    }

    // API
    return {
        get resizing() {
            return _resizing;
        },
        onStartResize,
    };
}