# AUTO-GENERATED UIPATH PSEUDOCODE
# This is not executable Python. UiPath expressions are preserved with expr(...).
# Source: tests\fixtures\large_workflow.xaml
# Source SHA256: ed09c8ea0dc6

# Arguments
# - In in_Config: InArgument(scg:Dictionary(x:String, x:Object))
# - In in_TransactionNumber: InArgument(x:Int32)
# - Out out_Status: OutArgument(x:String)

def large_workflow(in_Config, in_TransactionNumber):
    # Variables
    queueName: 'x:String' = expr('Config("QueueName").ToString')
    status: 'x:String' = None
    retryCounter: 'x:Int32' = expr('0')
    apiToken: 'x:String' = redacted()

    # Sequence: Process transaction
    reference = expr('"INV-" + in_TransactionNumber.ToString')
    get_asset(
        display_name='Load queue name',
        asset_name=expr('Config("QueueNameAsset").ToString'),
        value=expr('queueName'),
    )
    try:
        # Sequence: Try transaction
        excel_application_scope(display_name='Open workbook', workbook_path=expr('Config("WorkbookPath").ToString')):
            read_range(
                display_name='Read input sheet',
                sheet_name='Input',
                range='A1:F200',
            )
            # Loop rows
            for row in expr('dtInput.Rows'):
                # Sequence: Process row
                if expr('row("Amount").ToString <> String.Empty'):
                    add_queue_item(
                        display_name='Queue invoice',
                        queue_name=expr('queueName'),
                        transaction_item=expr('row'),
                    )
                else:
                    log(level='Warn', message=expr('"Skipping empty amount"'))
        retry_scope(number_of_retries=expr('CInt(Config("MaxRetryNumber"))'), retry_interval=expr('TimeSpan.FromSeconds(5)')):
            action:
                open_browser(display_name='Open portal', url=expr('Config("PortalUrl").ToString'))
                type_into(
                    display_name='Enter password',
                    text=redacted(),
                    selector_summary="aaname='<redacted>', id='password'",
                )
            condition:
                element_exists(display_name='Portal loaded', selector_summary="title='<redacted>', id='dashboard'")
        switch expr('status'):
            case 'Success':
                # Sequence: Success path
                invoke_workflow(
                    'NotifySuccess.xaml',
                    in_Reference=expr('reference'),
                    out_Status=out('out_Status'),
                )
            case 'BusinessException':
                # Sequence: Business exception path
                raise_uipath_exception(expr('New BusinessRuleException("Invalid invoice")'))
            default:
                log(level='Info', message=expr('"Unhandled status: " + status'))
    except System.Exception as ex:
        # Sequence: Handle system exception
        out_Status = expr('"Failed"')
        log(level='Error', message=expr('exception.Message'))
    finally:
        log(level='Info', message=expr('"Finished transaction"'))
