# AUTO-GENERATED UIPATH PSEUDOCODE
# This is not executable Python. UiPath expressions are preserved with expr(...).
# Source: tests\fixtures\ref_main_state_machine.xaml
# Source SHA256: c224eaffcaf1

def ref_main_state_machine():
    state_machine(initial='Init'):
        state 'Init':
            entry:
                # Sequence: Init entry
                invoke_workflow(
                    'InitAllApplications.xaml',
                    io_Config=inout('Config'),
                    out_SystemException=out('SystemException'),
                )
            transitions:
                transition(to='Get Transaction Data', condition=expr('SystemException Is Nothing')):
                    io_RetryNumber = expr('0')
                transition(to='End Process', condition=expr('SystemException IsNot Nothing')):
                    pass
        state 'Get Transaction Data':
            entry:
                invoke_workflow(
                    'GetTransactionData.xaml',
                    in_Config=expr('Config'),
                    io_TransactionNumber=inout('TransactionNumber'),
                    out_TransactionItem=out('TransactionItem'),
                    out_TransactionID=out('TransactionID'),
                )
            transitions:
                transition(to='Process Transaction', condition=expr('TransactionItem IsNot Nothing')):
                    pass
                transition(to='End Process', condition=expr('TransactionItem Is Nothing')):
                    pass
        state 'Process Transaction':
            entry:
                invoke_workflow(
                    'Process.xaml',
                    in_Config=expr('Config'),
                    in_TransactionItem=expr('TransactionItem'),
                    out_BusinessException=out('BusinessException'),
                    out_SystemException=out('SystemException'),
                )
            transitions:
                transition(to='Set Transaction Status', condition=expr('True')):
                    pass
        state 'Set Transaction Status':
            entry:
                invoke_workflow(
                    'SetTransactionStatus.xaml',
                    in_Config=expr('Config'),
                    in_TransactionItem=expr('TransactionItem'),
                    in_BusinessException=expr('BusinessException'),
                    in_SystemException=expr('SystemException'),
                    io_RetryNumber=inout('RetryNumber'),
                )
            transitions:
                transition(to='Get Transaction Data', condition=expr('RetryNumber < CInt(Config("MaxRetryNumber"))')):
                    pass
                transition(to='End Process', condition=expr('ShouldStop')):
                    pass
        state 'End Process':
            entry:
                # Sequence: Cleanup
                invoke_workflow(
                    'CloseAllApplications.xaml',
                )
                invoke_workflow(
                    'KillAllProcesses.xaml',
                )
