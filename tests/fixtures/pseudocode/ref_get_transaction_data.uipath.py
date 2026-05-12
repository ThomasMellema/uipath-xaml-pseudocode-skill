# AUTO-GENERATED UIPATH PSEUDOCODE
# This is not executable Python. UiPath expressions are preserved with expr(...).
# Source: tests\fixtures\ref_get_transaction_data.xaml
# Source SHA256: 43e5ae061872

# Arguments
# - In in_Config: InArgument(scg:Dictionary(x:String, x:Object))
# - InOut io_TransactionNumber: InOutArgument(x:Int32)
# - Out out_TransactionItem: OutArgument(UiPath.Core.QueueItem)
# - Out out_TransactionID: OutArgument(x:String)

def ref_get_transaction_data(in_Config, io_TransactionNumber):
    # Sequence: Get transaction data
    get_transaction_item(
        display_name='Get orchestrator transaction',
        queue_name=expr('Config("OrchestratorQueueName").ToString'),
        transaction_item=expr('out_TransactionItem'),
    )
    if expr('out_TransactionItem Is Nothing'):
        # Sequence: No queue item
        out_TransactionID = expr('Nothing')
    else:
        # Sequence: Prepare queue item
        out_TransactionID = expr('out_TransactionItem.Reference')
        io_TransactionNumber = expr('io_TransactionNumber + 1')
    if expr('Config("TransactionDataSource").ToString = "DataTable"'):
        # Sequence: Non queue fallback
        currentRow = expr('dt_TransactionData.Rows(io_TransactionNumber - 1)')
        out_TransactionID = expr('currentRow("Reference").ToString')
