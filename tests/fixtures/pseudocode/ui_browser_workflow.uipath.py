# AUTO-GENERATED UIPATH PSEUDOCODE
# This is not executable Python. UiPath expressions are preserved with expr(...).
# Source: tests\fixtures\ui_browser_workflow.xaml
# Source SHA256: 224ed60abb8e

def ui_browser_workflow():
    # Sequence: UI browser flow
    use_application_browser(
        display_name='Use customer portal',
        url=expr('Config("PortalUrl").ToString'),
        selector_summary="title='<redacted>'",
    ):
        # Sequence: Portal actions
        click(
            display_name='Click login',
            timeout_ms='30000',
            selector_summary="aaname='<redacted>', id='login'",
        )
        type_into(
            display_name='Password field',
            text=redacted(),
            selector_summary="aaname='<redacted>', id='password'",
        )
        get_text(
            display_name='Read confirmation',
            output=expr('confirmationText'),
            selector_summary="title='<redacted>', id='welcome'",
        )
        element_exists(
            display_name='Find dashboard',
            output=expr('dashboardExists'),
            selector_summary="title='<redacted>', id='dashboard'",
        )
        check_app_state(display_name='Check dashboard'):
            target:
                element_exists(display_name='Dashboard target', selector_summary="title='<redacted>', id='dashboard'")
            then:
                log(level='Info', message=expr('"Dashboard loaded"'))
            else:
                raise_uipath_exception(expr('New System.Exception("Dashboard missing")'))
