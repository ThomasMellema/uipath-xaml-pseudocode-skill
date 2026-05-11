---
name: uipath-xaml-pseudocode
description: "Use this when you need to inspect a UiPath .xaml workflow. Convert raw XAML into compact Python-like pseudocode first, preserving workflow structure, Assign values, conditions, invokes, variables, arguments, Try/Catch, queues, assets, config usage, and important UI actions while dropping designer/viewstate/XML noise."
allowed-tools: Bash, Read, Glob
user-invocable: true
---

# UiPath XAML Pseudocode

Use this skill whenever a UiPath `.xaml` file must be read or analyzed.

The goal is to avoid using raw XAML as agent context. Raw UiPath XAML contains large amounts of designer/viewstate/XML metadata that wastes tokens and obscures the actual workflow logic.

## Primary rule

Do not read raw `.xaml` as the primary context.

Before analyzing a `.xaml` file, run:

```bash
python tools/uipath_xaml_to_pseudocode.py --file "<path-to-xaml>" --out ".agent-context/pseudocode/<workflow-name>.uipath.py"
```

Then read the generated `.uipath.py` file and use that as the primary context.

Read raw XAML only when the generated pseudocode explicitly fails to capture a detail needed for debugging.

## Output

Generated pseudocode should be treated as non-executable Python-like workflow source.

Default output location:

```text
.agent-context/pseudocode/*.uipath.py
```

## Preserve

- workflow order
- indentation/nesting
- Sequence
- If / Else
- Switch / Case where detectable
- For Each / While / Do While
- Try / Catch / Finally
- Retry Scope where detectable
- InvokeWorkflowFile
- Assign activities with exact right-hand expressions
- variables with type/default where detectable
- arguments with direction/type where detectable
- LogMessage text
- Throw / Rethrow
- queue operations
- asset operations
- config key usage
- Excel, mail, browser, API and database actions
- selector summaries

## Remove from context

- `sap:VirtualizedContainerService.HintSize`
- `sap2010:WorkflowViewState.IdRef`
- `WorkflowViewStateService.ViewState`
- designer layout metadata
- XML namespace declarations
- assembly reference dumps
- XML serialization IDs
- layout coordinates
- empty attributes
- duplicate metadata

## Expression handling

Do not translate UiPath expressions into Python unless the conversion is trivial and safe.

Preserve UiPath expressions as:

```python
expr("original UiPath expression")
```

Examples:

```python
invoice_number = expr('row("InvoiceNumber").ToString.Trim')
queue_name = expr('Config("QueueName").ToString')
retry_count = expr('CInt(Config("MaxRetryNumber"))')
```

## Redaction

Never expose actual secret values.

Redact or summarize:

- passwords
- tokens
- API keys
- credential values
- cookies
- private certificates
- personal data
- customer-identifying selector values when not needed

Keep asset names and config key names, but redact values.

## Fallback

If the converter reports a parse error or unsupported activity, keep the generated fallback output and mention that raw XAML may need targeted inspection for the unsupported part.
