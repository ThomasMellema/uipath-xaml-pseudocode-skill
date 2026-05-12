# AUTO-GENERATED UIPATH PSEUDOCODE
# This is not executable Python. UiPath expressions are preserved with expr(...).
# Source: tests\fixtures\ref_process_set_status.xaml
# Source SHA256: fb5e8b7a3a28

# Arguments
# - In in_Config: InArgument(scg:Dictionary(x:String, x:Object))
# - In in_TransactionItem: InArgument(UiPath.Core.QueueItem)
# - InOut io_RetryNumber: InOutArgument(x:Int32)
# - Out out_BusinessException: OutArgument(BusinessRuleException)
# - Out out_SystemException: OutArgument(System.Exception)

def ref_process_set_status(in_Config, in_TransactionItem, io_RetryNumber):
    # Sequence: Process and set status
    try:
        # Sequence: Process item
        invoiceNumber = expr('in_TransactionItem.SpecificContent("InvoiceNumber").ToString')
        transactionReference = expr('in_TransactionItem.Reference')
        if expr('String.IsNullOrWhiteSpace(invoiceNumber)'):
            raise_uipath_exception(expr('New BusinessRuleException("Missing invoice number")'))
        switch expr('transactionStatus'):
            case 'Success':
                # Sequence: Success status
                set_transaction_status(
                    display_name='Set success',
                    transaction_item=expr('in_TransactionItem'),
                    status=expr('"Successful"'),
                )
            case 'BusinessException':
                # Sequence: Business exception status
                set_transaction_status(
                    display_name='Set business exception',
                    transaction_item=expr('in_TransactionItem'),
                    status=expr('"Failed"'),
                    reason=expr('out_BusinessException.Message'),
                    error_type=expr('"Business"'),
                )
            case 'ApplicationException':
                # Sequence: Application exception status
                io_RetryNumber = expr('io_RetryNumber + 1')
                if expr('io_RetryNumber < CInt(in_Config("MaxRetryNumber"))'):
                    invoke_workflow(
                        'CloseAllApplications.xaml',
                    )
                else:
                    set_transaction_status(
                        display_name='Set application exception',
                        transaction_item=expr('in_TransactionItem'),
                        status=expr('"Failed"'),
                        reason=expr('out_SystemException.Message'),
                        error_type=expr('"Application"'),
                    )
    except BusinessRuleException as ex:
        # Sequence: Business catch
        out_BusinessException = expr('exception')
        rethrow()
    except System.Exception as ex:
        # Sequence: System catch
        out_SystemException = expr('exception')
        rethrow()
    finally:
        log(level='Info', message=expr('"Process workflow finished"'))
