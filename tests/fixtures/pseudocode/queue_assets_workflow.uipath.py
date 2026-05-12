# AUTO-GENERATED UIPATH PSEUDOCODE
# This is not executable Python. UiPath expressions are preserved with expr(...).
# Source: tests\fixtures\queue_assets_workflow.xaml
# Source SHA256: 98f68e0226e4

def queue_assets_workflow():
    # Sequence: Queue assets credentials flow
    get_asset(
        display_name='Get queue asset',
        asset_name=expr('Config("QueueAssetName").ToString'),
        value=expr('queueName'),
    )
    get_credential(
        display_name='Get robot credential',
        credential_name=expr('Config("CredentialName").ToString'),
        username='<redacted>',
        password=redacted(),
    )
    get_transaction_item(
        display_name='Get queue transaction',
        queue_name=expr('queueName'),
        transaction_item=expr('transactionItem'),
    )
    add_queue_item(
        display_name='Add audit item',
        queue_name=expr('Config("AuditQueue").ToString'),
        transaction_item=expr('auditItem'),
    )
    if expr('transactionItem Is Nothing'):
        log(level='Info', message=expr('"No transaction item"'))
    else:
        set_transaction_status(
            display_name='Set success',
            transaction_item=expr('transactionItem'),
            status=expr('"Successful"'),
            reason=expr('"Done"'),
            queue_name=expr('queueName'),
        )
    custom_vendor_activity(
        display_name='Vendor extension',
        value=expr('queueName'),
        timeout_ms='10000',
    )
