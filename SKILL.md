---
name: uipath-xaml-pseudocode
description: Convert UiPath .xaml workflows into compact Python-like pseudocode before analysis. Use when Codex needs to inspect, summarize, debug, review, or compare UiPath workflows or projects, including REFramework projects, while preserving workflow structure, StateMachine transitions, variables, arguments, Assign, InvokeWorkflowFile, If/Switch, loops, Try/Catch/Rethrow, RetryScope, queue/asset/credential/config references, UI/browser, Excel/DataTable, mail, API, file activity signals, selectors, and logs without loading raw XAML noise.
---

# UiPath XAML Pseudocode

Use this skill before reading UiPath `.xaml` files. Raw UiPath XAML contains designer metadata, view state, namespace dumps, and serialization noise that should not be the primary analysis context.

## Workflow

1. Resolve this skill's script path:

   ```bash
   <skill-dir>/scripts/uipath_xaml_to_pseudocode.py
   ```

2. Convert one workflow:

   ```bash
   python "<skill-dir>/scripts/uipath_xaml_to_pseudocode.py" --file "<path-to-workflow.xaml>" --out ".agent-context/pseudocode/<workflow-name>.uipath.py"
   ```

3. Or convert a UiPath project directory:

   ```bash
   python "<skill-dir>/scripts/uipath_xaml_to_pseudocode.py" --dir "<path-to-uipath-project>" --out ".agent-context/pseudocode"
   ```

4. Read the generated `.uipath.py` files and use them as the primary context.

Read raw XAML only for a targeted detail that the pseudocode explicitly omits or marks as unsupported.

## Output Contract

Treat generated files as non-executable Python-like workflow source.

Preserve:

- workflow order and indentation
- `Sequence`, `StateMachine`, `State`, `Transition`, `If`/`Else`, `Switch`/`case`, loops, `Try`/`Catch`/`Finally`, `Rethrow`, and `RetryScope`
- `InvokeWorkflowFile` calls and arguments
- `Assign` targets and right-hand expressions
- variables and arguments where detectable
- `LogMessage`, `Throw`, queue, asset, credential, config, Excel/DataTable, mail, browser, API, file, database, and UI activity signals
- compact selector summaries

Drop:

- view state and designer layout metadata
- XML namespace and assembly reference dumps
- serialization IDs, hint sizes, coordinates, and empty metadata

## Expression Handling

Preserve UiPath expressions as `expr("original UiPath expression")`. Do not translate expressions into Python unless it is trivial and safe.

Examples:

```python
invoice_number = expr('row("InvoiceNumber").ToString.Trim')
queue_name = expr('Config("QueueName").ToString')
retry_count = expr('CInt(Config("MaxRetryNumber"))')
```

## Redaction

Do not expose actual secret values. The converter redacts obvious password/token/API-key literals and customer-identifying selector values while keeping config key names such as `Config("QueueName")` visible.

If a redacted or summarized value blocks debugging, inspect only the smallest necessary raw XAML fragment.

## Fallback

If parsing fails, keep the fallback output and mention that targeted raw XAML inspection may be needed.
