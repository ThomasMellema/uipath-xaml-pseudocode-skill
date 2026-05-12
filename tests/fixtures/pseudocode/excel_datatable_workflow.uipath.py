# AUTO-GENERATED UIPATH PSEUDOCODE
# This is not executable Python. UiPath expressions are preserved with expr(...).
# Source: tests\fixtures\excel_datatable_workflow.xaml
# Source SHA256: 9d65cce25714

def excel_datatable_workflow():
    # Sequence: Excel and datatable flow
    use_excel_file(display_name='Use workbook', workbook_path=expr('Config("WorkbookPath").ToString')):
        # Sequence: Workbook actions
        read_range(
            display_name='Read invoices',
            sheet_name='Input',
            range='A1:F200',
            output=expr('dtInvoices'),
        )
        filter_data_table(
            display_name='Keep open invoices',
            input_data_table=expr('dtInvoices'),
            output_data_table=expr('dtOpenInvoices'),
        )
        # Loop open invoices
        for row in expr('dtOpenInvoices.Rows'):
            # Sequence: Update row
            read_cell(
                display_name='Read status',
                sheet_name='Input',
                cell=expr('"F" + rowIndex.ToString'),
                output=expr('status'),
            )
            write_cell(
                display_name='Write processed',
                sheet_name='Input',
                cell=expr('"G" + rowIndex.ToString'),
                value=expr('"Processed"'),
            )
        write_range(
            display_name='Write filtered invoices',
            sheet_name='Output',
            range='A1',
            data_table=expr('dtOpenInvoices'),
        )
