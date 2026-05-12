# AUTO-GENERATED UIPATH PSEUDOCODE
# This is not executable Python. UiPath expressions are preserved with expr(...).
# Source: tests\fixtures\mail_api_files_workflow.xaml
# Source SHA256: 75540c030081

def mail_api_files_workflow():
    # Sequence: Mail API files flow
    get_outlook_mail_messages(
        display_name='Read inbox',
        folder='Inbox',
        output=expr('mailMessages'),
    )
    # Loop mails
    for mail in expr('mailMessages'):
        # Sequence: Handle mail
        save_mail_attachments(
            display_name='Save attachments',
            mail_message=expr('mail'),
            folder_path=expr('Config("AttachmentFolder").ToString'),
        )
    send_outlook_mail_message(
        display_name='Send result',
        to=expr('Config("SupportMailbox").ToString'),
        subject='"Robot completed"',
        body=expr('summaryHtml'),
    )
    http_client(
        display_name='Call status API',
        method='POST',
        endpoint=expr('Config("StatusApiEndpoint").ToString + "?token=<redacted>"'),
        body=expr('payloadJson'),
        result=expr('apiResponse'),
        status_code=expr('statusCode'),
    )
    deserialize_json(
        display_name='Parse response',
        input=expr('apiResponse'),
        output=expr('jsonResponse'),
    )
    read_text_file(
        display_name='Read template',
        path=expr('Config("TemplatePath").ToString'),
        output=expr('templateText'),
    )
    write_text_file(
        display_name='Write audit file',
        path=expr('auditPath'),
        text=expr('auditContent'),
    )
    copy_file(
        display_name='Copy archive',
        source=expr('auditPath'),
        destination=expr('archivePath'),
    )
    delete_file(display_name='Delete temp file', path=expr('tempPath'))
