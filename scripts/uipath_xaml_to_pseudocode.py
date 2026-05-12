
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable, Optional


SKIP_NODE_NAMES = {
    "TextExpression.NamespacesForImplementation",
    "TextExpression.ReferencesForImplementation",
    "WorkflowViewStateService.ViewState",
}
SKIP_PROPERTY_SUFFIXES = {
    ".Variables",
    ".Imports",
    ".References",
    ".NamespacesForImplementation",
    ".ReferencesForImplementation",
    ".ViewState",
}


def local_name(name: str) -> str:
    """Return namespace-free XML element/attribute name."""
    if "}" in name:
        return name.rsplit("}", 1)[-1]
    if ":" in name:
        return name.rsplit(":", 1)[-1]
    return name


def attr(elem: ET.Element, *names: str) -> Optional[str]:
    wanted = set(names)
    for key, value in elem.attrib.items():
        if local_name(key) in wanted:
            return value
    return None


def all_text(elem: Optional[ET.Element]) -> str:
    if elem is None:
        return ""
    text = "".join(elem.itertext())
    return clean_expr(text)


def clean_expr(value: Optional[str]) -> str:
    if value is None:
        return ""
    value = html.unescape(str(value))
    value = re.sub(r"\s+", " ", value).strip()
    # UiPath XAML commonly wraps expressions in [ ... ].
    if len(value) >= 2 and value[0] == "[" and value[-1] == "]":
        value = value[1:-1].strip()
    return value


def py_str(value: str) -> str:
    return repr(value)


def snake(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9]+", "_", name)
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return name.strip("_").lower() or "activity"


REDACTED = "<redacted>"
SENSITIVE_WORDS = {
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "certificate",
    "client_secret",
    "clientsecret",
    "cookie",
    "credential",
    "password",
    "passwd",
    "private_key",
    "privatekey",
    "pwd",
    "secret",
    "token",
}
SENSITIVE_SELECTOR_KEYS = {"aaname", "name", "title", "url"}
SCALAR_XAML_NODES = {"Boolean", "Byte", "Char", "Decimal", "Double", "Int16", "Int32", "Int64", "Single", "String"}
EXCLUDED_PROJECT_DIRS = {".agent-context", ".git", ".svn", ".vs", "bin", "obj", "node_modules"}


def compact_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def looks_sensitive(value: str) -> bool:
    compact = compact_key(value)
    return any(compact_key(word) in compact for word in SENSITIVE_WORDS)


def contains_config_lookup(value: str) -> bool:
    return bool(re.search(r"\bConfig\s*\(\s*['\"][^'\"]+['\"]\s*\)", value))


def redact_value(value: str, context: str = "") -> str:
    value = clean_expr(value)
    if not value:
        return ""

    # Keep Config("Key") references visible: they name a lookup key, not the secret value.
    if looks_sensitive(context) and not contains_config_lookup(value):
        return REDACTED

    value = re.sub(
        r"(?i)\b(Bearer)\s+[A-Za-z0-9._~+/=-]{8,}",
        rf"\1 {REDACTED}",
        value,
    )
    value = re.sub(
        r"(?i)\b(password|passwd|pwd|token|api[_-]?key|secret|client[_-]?secret)\s*[:=]\s*[^&\s,;\"')]+",
        lambda m: f"{m.group(1)}={REDACTED}",
        value,
    )

    bare = value.strip("\"'")
    if len(bare) >= 24 and re.fullmatch(r"[A-Za-z0-9._~+/=-]+", bare) and looks_sensitive(context):
        return REDACTED

    return value


def literal(value: str, context: str = "") -> str:
    return py_str(redact_value(value, context=context))


def property_text(elem: ET.Element, prop: str) -> str:
    node = child_property(elem, prop)
    if node is None:
        return ""
    return all_text(node)


def field_value(elem: ET.Element, *names: str) -> str:
    """Read a UiPath field from an XML attribute or matching child property node."""
    for name in names:
        value = attr(elem, name)
        if value:
            return clean_expr(value)
    for name in names:
        value = property_text(elem, name)
        if value:
            return clean_expr(value)
    return ""


EXPR_FIELDS = {
    "AssetName",
    "Body",
    "Cell",
    "ApplicationPath",
    "CredentialName",
    "DataTable",
    "Destination",
    "Endpoint",
    "Exception",
    "ErrorType",
    "FileName",
    "FolderPath",
    "Headers",
    "Input",
    "InputDataTable",
    "MailMessage",
    "MailMessages",
    "Output",
    "OutputDataTable",
    "Password",
    "Path",
    "QueueName",
    "Reason",
    "RequestBody",
    "Result",
    "SecurePassword",
    "Source",
    "Status",
    "StatusCode",
    "Text",
    "To",
    "TransactionItem",
    "Url",
    "Value",
    "WorkbookPath",
}


def is_noise(elem: ET.Element) -> bool:
    name = local_name(elem.tag)
    if name in SKIP_NODE_NAMES:
        return True
    if name.startswith("TextExpression."):
        return True
    return any(name.endswith(suffix) for suffix in SKIP_PROPERTY_SUFFIXES)


def is_property_node(elem: ET.Element) -> bool:
    return "." in local_name(elem.tag)


def child_property(elem: ET.Element, prop: str) -> Optional[ET.Element]:
    """Find a direct child property node ending with .<prop>, e.g. Assign.To."""
    for child in elem:
        name = local_name(child.tag)
        if name.endswith("." + prop) or name == prop:
            return child
    return None


def first_activity_child(elem: ET.Element) -> Optional[ET.Element]:
    for child in elem:
        if is_noise(child):
            continue
        if is_property_node(child):
            nested = first_activity_child(child)
            if nested is not None:
                return nested
            continue
        return child
    return None


def body_children(elem: ET.Element) -> list[ET.Element]:
    """Return likely workflow/action children, unwrapping property containers."""
    result: list[ET.Element] = []
    for child in elem:
        if is_noise(child):
            continue
        name = local_name(child.tag)

        # Do not render data-only property nodes as standalone activities.
        if is_property_node(child):
            low = name.lower()
            if any(low.endswith(x) for x in [
                ".to", ".value", ".condition", ".expression", ".arguments",
                ".variables", ".displayname", ".selector", ".text", ".message",
                ".url", ".workbookpath", ".filename", ".path", ".source",
                ".destination", ".input", ".output", ".result", ".body",
                ".headers", ".datatable", ".inputdatatable", ".outputdatatable",
                ".queuename", ".transactionitem", ".assetname", ".credentialname",
                ".username", ".password", ".securepassword", ".status", ".reason",
                ".errortype", ".folder", ".folderpath", ".subject", ".attachments",
                ".mailmessages", ".method", ".endpoint", ".requestbody", ".statuscode",
                ".range", ".sheetname", ".cell", ".timeoutms", ".continueonerror"
            ]):
                continue
            result.extend(body_children(child))
            continue

        if name == "ActivityAction":
            result.extend(body_children(child))
            continue

        # Skip definitions collected separately.
        if name in {"Members", "Property", "Variable", "DelegateInArgument"}:
            continue

        result.append(child)
    return result


def summarize_selector(value: str, max_len: int = 220) -> str:
    value = clean_expr(value)
    if not value:
        return ""

    # Keep the useful selector signal without dumping full XML-ish selector blobs.
    pieces: list[str] = []
    for key in ["app", "title", "tag", "aaname", "name", "id", "class", "idx", "url"]:
        m = re.search(rf"\b{key}='([^']*)'", value)
        if m:
            v = m.group(1)
            if key in SENSITIVE_SELECTOR_KEYS:
                v = REDACTED
            if len(v) > 60:
                v = v[:57] + "..."
            pieces.append(f"{key}={v!r}")

    if pieces:
        summary = ", ".join(pieces)
    else:
        summary = re.sub(r"\s+", " ", value)

    if len(summary) > max_len:
        summary = summary[: max_len - 3] + "..."
    return summary


def expr(value: str, context: str = "") -> str:
    value = redact_value(value, context=context)
    if not value:
        return "None"
    if value == REDACTED:
        return "redacted()"
    # Keep literals readable, but preserve UiPath expressions explicitly.
    return f"expr({py_str(value)})"


def collect_arguments(root: ET.Element) -> list[dict[str, str]]:
    args: list[dict[str, str]] = []
    for elem in root.iter():
        if local_name(elem.tag) != "Property":
            continue
        name = attr(elem, "Name") or ""
        type_ = attr(elem, "Type") or attr(elem, "TypeArguments") or ""
        if not name:
            continue
        direction = "Unknown"
        if "InOutArgument" in type_:
            direction = "InOut"
        elif "OutArgument" in type_:
            direction = "Out"
        elif "InArgument" in type_:
            direction = "In"
        args.append({"name": name, "direction": direction, "type": clean_expr(type_)})
    return args


def collect_variables(root: ET.Element) -> list[dict[str, str]]:
    variables: list[dict[str, str]] = []
    seen: set[str] = set()
    for elem in root.iter():
        if local_name(elem.tag) != "Variable":
            continue
        name = attr(elem, "Name") or ""
        if not name or name in seen:
            continue
        seen.add(name)
        type_ = attr(elem, "TypeArguments") or attr(elem, "Type") or "Object"
        default = attr(elem, "Default") or all_text(child_property(elem, "Default"))
        variables.append({
            "name": name,
            "type": clean_expr(type_),
            "default": redact_value(default, context=name),
        })
    return variables


def render_assign(elem: ET.Element, indent: int) -> list[str]:
    to_value = field_value(elem, "To")
    from_value = field_value(elem, "Value")

    line = f"{to_value or '_'} = {expr(from_value, context=to_value)}"
    return [" " * indent + line]


def extract_invoke_args(elem: ET.Element) -> list[tuple[str, str, str]]:
    args_node = child_property(elem, "Arguments")
    if args_node is None:
        return []

    result: list[tuple[str, str, str]] = []
    for arg_elem in args_node.iter():
        kind = local_name(arg_elem.tag)
        if kind not in {"InArgument", "OutArgument", "InOutArgument"}:
            continue
        key = attr(arg_elem, "Key")
        if not key:
            continue
        value = all_text(arg_elem)
        result.append((kind, key, value))
    return result


def render_invoke(elem: ET.Element, indent: int) -> list[str]:
    workflow = field_value(elem, "WorkflowFileName", "FileName")
    display = field_value(elem, "DisplayName")
    invoke_args = extract_invoke_args(elem)

    prefix = " " * indent
    lines = [prefix + "invoke_workflow("]
    if workflow:
        lines.append(prefix + f"    {py_str(workflow)},")
    elif display:
        lines.append(prefix + f"    display_name={py_str(display)},")
    else:
        lines.append(prefix + "    '<unknown-workflow>',")

    for kind, key, value in invoke_args:
        if kind == "OutArgument":
            rendered = f"out({literal(value, context=key)})" if value else "out(None)"
        elif kind == "InOutArgument":
            rendered = f"inout({literal(value, context=key)})" if value else "inout(None)"
        else:
            rendered = expr(value, context=key)
        lines.append(prefix + f"    {key}={rendered},")

    lines.append(prefix + ")")
    return lines


def render_if(elem: ET.Element, indent: int) -> list[str]:
    condition = field_value(elem, "Condition")
    lines = [" " * indent + f"if {expr(condition)}:"]
    then_node = child_property(elem, "Then")
    else_node = child_property(elem, "Else")

    then_lines = render_block(then_node, indent + 4) if then_node is not None else []
    lines.extend(then_lines or [" " * (indent + 4) + "pass"])

    if else_node is not None:
        else_lines = render_block(else_node, indent + 4)
        lines.append(" " * indent + "else:")
        lines.extend(else_lines or [" " * (indent + 4) + "pass"])

    return lines


def render_switch(elem: ET.Element, indent: int) -> list[str]:
    expression = field_value(elem, "Expression")
    lines = [" " * indent + f"switch {expr(expression)}:"]
    cases_node = child_property(elem, "Cases")
    seen: set[int] = set()
    rendered_cases = 0

    if cases_node is not None:
        for case in cases_node:
            key = attr(case, "Key")
            if not key or id(case) in seen:
                continue
            seen.add(id(case))
            rendered_cases += 1
            lines.append(" " * (indent + 4) + f"case {py_str(clean_expr(key))}:")
            if local_name(case.tag) in SCALAR_XAML_NODES and not body_children(case):
                case_lines = []
            else:
                case_lines = render_element(case, indent + 8)
            lines.extend(case_lines or [" " * (indent + 8) + "pass"])

    default_node = child_property(elem, "Default")
    if default_node is not None:
        lines.append(" " * (indent + 4) + "default:")
        lines.extend(render_block(default_node, indent + 8) or [" " * (indent + 8) + "pass"])

    if rendered_cases == 0 and default_node is None:
        lines.append(" " * (indent + 4) + "pass")

    return lines


def render_while(elem: ET.Element, indent: int) -> list[str]:
    condition = field_value(elem, "Condition")
    lines = [" " * indent + f"while {expr(condition)}:"]
    body = child_property(elem, "Body") or elem
    body_lines = render_block(body, indent + 4)
    lines.extend(body_lines or [" " * (indent + 4) + "pass"])
    return lines


def render_for_each(elem: ET.Element, indent: int) -> list[str]:
    display = field_value(elem, "DisplayName")
    values = field_value(elem, "Values", "DataTable", "Input")
    item_name = clean_expr(attr(elem, "CurrentIndex") or "item")
    # UiPath often stores the loop variable in a body ActivityAction Argument.
    for child in elem.iter():
        if local_name(child.tag) == "DelegateInArgument":
            item_name = attr(child, "Name") or item_name
            break

    lines = [" " * indent + f"for {item_name} in {expr(values)}:"]
    if display:
        lines.insert(0, " " * indent + f"# {display}")
    body = child_property(elem, "Body") or elem
    body_lines = render_block(body, indent + 4)
    lines.extend(body_lines or [" " * (indent + 4) + "pass"])
    return lines


def render_retry_scope(elem: ET.Element, indent: int) -> list[str]:
    retries = field_value(elem, "NumberOfRetries")
    interval = field_value(elem, "RetryInterval")
    kwargs: list[str] = []
    if retries:
        kwargs.append(f"number_of_retries={expr(retries, context='NumberOfRetries')}")
    if interval:
        kwargs.append(f"retry_interval={expr(interval, context='RetryInterval')}")

    prefix = " " * indent
    header = f"retry_scope({', '.join(kwargs)}):" if kwargs else "retry_scope():"
    lines = [prefix + header]

    action_node = (
        child_property(elem, "ActivityBody")
        or child_property(elem, "Action")
        or child_property(elem, "Body")
    )
    condition_node = child_property(elem, "Condition")

    if action_node is not None:
        lines.append(" " * (indent + 4) + "action:")
        lines.extend(render_block(action_node, indent + 8) or [" " * (indent + 8) + "pass"])
    if condition_node is not None:
        lines.append(" " * (indent + 4) + "condition:")
        lines.extend(render_block(condition_node, indent + 8) or [" " * (indent + 8) + "pass"])
    if action_node is None and condition_node is None:
        lines.extend(render_block(elem, indent + 4) or [" " * (indent + 4) + "pass"])

    return lines


def render_trycatch(elem: ET.Element, indent: int) -> list[str]:
    lines = [" " * indent + "try:"]
    try_node = child_property(elem, "Try")
    lines.extend((render_block(try_node, indent + 4) if try_node is not None else []) or [" " * (indent + 4) + "pass"])

    catches_node = child_property(elem, "Catches")
    if catches_node is not None:
        for catch in catches_node.iter():
            if local_name(catch.tag) != "Catch":
                continue
            ex_type = attr(catch, "TypeArguments") or "Exception"
            lines.append(" " * indent + f"except {clean_expr(ex_type)} as ex:")
            catch_lines = render_block(catch, indent + 4)
            lines.extend(catch_lines or [" " * (indent + 4) + "pass"])

    finally_node = child_property(elem, "Finally")
    if finally_node is not None:
        lines.append(" " * indent + "finally:")
        lines.extend(render_block(finally_node, indent + 4) or [" " * (indent + 4) + "pass"])

    return lines


def render_log(elem: ET.Element, indent: int) -> list[str]:
    level = field_value(elem, "Level") or "Info"
    message = field_value(elem, "Message")
    return [" " * indent + f"log(level={py_str(level)}, message={expr(message, context='LogMessage Message')})"]


def render_throw(elem: ET.Element, indent: int) -> list[str]:
    exception = field_value(elem, "Exception")
    return [" " * indent + f"raise_uipath_exception({expr(exception, context='Exception')})"]


IMPORTANT_ATTRS = [
    "DisplayName",
    "Text",
    "Value",
    "To",
    "Input",
    "Output",
    "Result",
    "FileName",
    "Path",
    "Source",
    "Destination",
    "WorkbookPath",
    "SheetName",
    "Range",
    "Cell",
    "DataTable",
    "InputDataTable",
    "OutputDataTable",
    "QueueName",
    "TransactionItem",
    "AssetName",
    "CredentialName",
    "Username",
    "Password",
    "SecurePassword",
    "Status",
    "Reason",
    "ErrorType",
    "TimeoutMS",
    "ContinueOnError",
    "Url",
    "Method",
    "Endpoint",
    "Body",
    "RequestBody",
    "Headers",
    "StatusCode",
    "Subject",
    "Folder",
    "FolderPath",
    "MailMessages",
    "Attachments",
]


ACTIVITY_FIELD_SPECS: dict[str, list[str]] = {
    # UI and browser activities.
    "UseApplicationBrowser": ["DisplayName", "Url", "ApplicationPath", "BrowserType", "TimeoutMS", "ContinueOnError"],
    "OpenBrowser": ["DisplayName", "Url", "BrowserType", "TimeoutMS", "ContinueOnError"],
    "AttachBrowser": ["DisplayName", "Url", "BrowserType", "TimeoutMS", "ContinueOnError"],
    "Click": ["DisplayName", "TimeoutMS", "ContinueOnError"],
    "TypeInto": ["DisplayName", "Text", "TimeoutMS", "ContinueOnError"],
    "GetText": ["DisplayName", "Output", "Result", "TimeoutMS", "ContinueOnError"],
    "ElementExists": ["DisplayName", "Output", "Result", "TimeoutMS", "ContinueOnError"],
    "CheckAppState": ["DisplayName", "TimeoutMS", "ContinueOnError"],
    "CloseApplication": ["DisplayName", "TimeoutMS", "ContinueOnError"],
    "KillProcess": ["DisplayName", "ProcessName", "TimeoutMS", "ContinueOnError"],
    "CloseTab": ["DisplayName", "TimeoutMS", "ContinueOnError"],

    # Excel and DataTable activities.
    "ExcelApplicationScope": ["DisplayName", "WorkbookPath", "Password", "TimeoutMS", "ContinueOnError"],
    "UseExcelFile": ["DisplayName", "WorkbookPath", "Password", "TimeoutMS", "ContinueOnError"],
    "ReadRange": ["DisplayName", "SheetName", "Range", "Output", "DataTable", "TimeoutMS", "ContinueOnError"],
    "WriteRange": ["DisplayName", "SheetName", "Range", "DataTable", "Input", "TimeoutMS", "ContinueOnError"],
    "ReadCell": ["DisplayName", "SheetName", "Cell", "Output", "Result", "TimeoutMS", "ContinueOnError"],
    "WriteCell": ["DisplayName", "SheetName", "Cell", "Value", "TimeoutMS", "ContinueOnError"],
    "FilterDataTable": ["DisplayName", "InputDataTable", "OutputDataTable", "TimeoutMS", "ContinueOnError"],

    # Queues, assets and credentials.
    "GetTransactionItem": ["DisplayName", "QueueName", "TransactionItem", "TimeoutMS", "ContinueOnError"],
    "AddQueueItem": ["DisplayName", "QueueName", "TransactionItem", "TimeoutMS", "ContinueOnError"],
    "SetTransactionStatus": ["DisplayName", "TransactionItem", "Status", "Reason", "QueueName", "ErrorType", "TimeoutMS", "ContinueOnError"],
    "GetAsset": ["DisplayName", "AssetName", "Value", "TimeoutMS", "ContinueOnError"],
    "GetCredential": ["DisplayName", "CredentialName", "Username", "Password", "SecurePassword", "TimeoutMS", "ContinueOnError"],

    # Mail, API and files.
    "GetOutlookMailMessages": ["DisplayName", "Folder", "MailMessages", "Output", "TimeoutMS", "ContinueOnError"],
    "SendOutlookMailMessage": ["DisplayName", "To", "Subject", "Body", "Attachments", "TimeoutMS", "ContinueOnError"],
    "SaveMailAttachments": ["DisplayName", "MailMessage", "FolderPath", "Attachments", "TimeoutMS", "ContinueOnError"],
    "HttpClient": ["DisplayName", "Method", "Endpoint", "Url", "Body", "RequestBody", "Headers", "Result", "StatusCode", "TimeoutMS", "ContinueOnError"],
    "DeserializeJson": ["DisplayName", "Input", "Output", "Result", "TimeoutMS", "ContinueOnError"],
    "ReadTextFile": ["DisplayName", "FileName", "Path", "Output", "Result", "TimeoutMS", "ContinueOnError"],
    "WriteTextFile": ["DisplayName", "FileName", "Path", "Text", "TimeoutMS", "ContinueOnError"],
    "CopyFile": ["DisplayName", "Source", "Destination", "Path", "TimeoutMS", "ContinueOnError"],
    "DeleteFile": ["DisplayName", "FileName", "Path", "TimeoutMS", "ContinueOnError"],
    "TerminateWorkflow": ["DisplayName", "Reason", "Exception", "TimeoutMS", "ContinueOnError"],
}


ACTIVITY_BODY_PROPS: dict[str, list[str]] = {
    "UseApplicationBrowser": ["Body", "Do"],
    "OpenBrowser": ["Body", "Do"],
    "AttachBrowser": ["Body", "Do"],
    "ExcelApplicationScope": ["Body", "Do"],
    "UseExcelFile": ["Body", "Do"],
    "CheckAppState": ["Target", "Then", "Else"],
}


def render_kw_value(elem_name: str, display: str, key: str, value: str) -> str:
    if key == "DisplayName":
        return literal(value, context=key)
    context = " ".join(part for part in [elem_name, display, key] if part)
    if key in EXPR_FIELDS:
        return expr(value, context=context)
    return literal(value, context=context)


def render_activity_call(
    elem: ET.Element,
    indent: int,
    call: Optional[str] = None,
    fields: Optional[list[str]] = None,
) -> list[str]:
    name = local_name(elem.tag)
    call = call or snake(name)
    kwargs: list[str] = []
    display = field_value(elem, "DisplayName")
    seen: set[str] = set()

    for key in fields or IMPORTANT_ATTRS:
        if key in seen:
            continue
        seen.add(key)
        value = field_value(elem, key)
        if value:
            kwargs.append(f"{snake(key)}={render_kw_value(name, display, key, value)}")

    selector = field_value(elem, "Selector")
    if selector:
        kwargs.append(f"selector_summary={py_str(summarize_selector(selector))}")

    prefix = " " * indent
    if not kwargs:
        lines = [prefix + f"{call}()"]
    elif len(kwargs) <= 2:
        lines = [prefix + f"{call}({', '.join(kwargs)})"]
    else:
        lines = [prefix + f"{call}("]
        lines.extend(prefix + f"    {kw}," for kw in kwargs)
        lines.append(prefix + ")")

    nested: list[str] = []
    body_props = ACTIVITY_BODY_PROPS.get(name, [])
    found_body_props = [
        (prop, child_property(elem, prop))
        for prop in body_props
        if child_property(elem, prop) is not None
    ]
    label_body_props = len(found_body_props) > 1
    for prop, node in found_body_props:
        prop_lines = render_block(node, indent + 8 if label_body_props else indent + 4)
        if label_body_props:
            nested.append(" " * (indent + 4) + f"{snake(prop)}:")
            nested.extend(prop_lines or [" " * (indent + 8) + "pass"])
        else:
            nested.extend(prop_lines or [" " * (indent + 4) + "pass"])
    if not nested:
        for child in body_children(elem):
            nested.extend(render_element(child, indent + 4))
    if nested:
        lines[-1] = lines[-1] + ":"
        lines.extend(nested)
    return lines


def render_known_activity(elem: ET.Element, indent: int) -> list[str]:
    name = local_name(elem.tag)
    return render_activity_call(elem, indent, call=snake(name), fields=ACTIVITY_FIELD_SPECS[name])


def render_generic(elem: ET.Element, indent: int) -> list[str]:
    return render_activity_call(elem, indent)


def render_rethrow(elem: ET.Element, indent: int) -> list[str]:
    exception = field_value(elem, "Exception")
    if exception:
        return [" " * indent + f"raise_uipath_exception({expr(exception, context='Exception')})"]
    return [" " * indent + "rethrow()"]


def render_transition(elem: ET.Element, indent: int) -> list[str]:
    condition = field_value(elem, "Condition")
    target = field_value(elem, "To", "Target", "DisplayName")
    kwargs: list[str] = []
    if target:
        kwargs.append(f"to={py_str(target)}")
    if condition:
        kwargs.append(f"condition={expr(condition)}")

    prefix = " " * indent
    header = f"transition({', '.join(kwargs)}):" if kwargs else "transition:"
    lines = [prefix + header]
    action_node = child_property(elem, "Action")
    lines.extend((render_block(action_node, indent + 4) if action_node is not None else []) or [" " * (indent + 4) + "pass"])
    return lines


def render_state(elem: ET.Element, indent: int) -> list[str]:
    name = field_value(elem, "DisplayName", "Name") or attr(elem, "Key") or "<unnamed>"
    lines = [" " * indent + f"state {py_str(name)}:"]

    entry_node = child_property(elem, "Entry")
    if entry_node is not None:
        lines.append(" " * (indent + 4) + "entry:")
        lines.extend(render_block(entry_node, indent + 8) or [" " * (indent + 8) + "pass"])

    transitions_node = child_property(elem, "Transitions")
    transitions = body_children(transitions_node) if transitions_node is not None else [
        child for child in body_children(elem) if local_name(child.tag) == "Transition"
    ]
    if transitions:
        lines.append(" " * (indent + 4) + "transitions:")
        for transition in transitions:
            if local_name(transition.tag) == "Transition":
                lines.extend(render_transition(transition, indent + 8))

    if len(lines) == 1:
        lines.append(" " * (indent + 4) + "pass")
    return lines


def render_state_machine(elem: ET.Element, indent: int) -> list[str]:
    initial = field_value(elem, "InitialState")
    header = "state_machine"
    if initial:
        header += f"(initial={py_str(initial)})"
    header += ":"

    lines = [" " * indent + header]
    states_node = child_property(elem, "States") or elem
    states = [child for child in body_children(states_node) if local_name(child.tag) == "State"]
    for state in states:
        lines.extend(render_state(state, indent + 4))
    if not states:
        lines.extend(render_block(states_node, indent + 4) or [" " * (indent + 4) + "pass"])
    return lines


RENDERERS: dict[str, Callable[[ET.Element, int], list[str]]] = {
    name: render_known_activity for name in ACTIVITY_FIELD_SPECS
}
RENDERERS.update({
    "StateMachine": render_state_machine,
    "State": render_state,
    "Transition": render_transition,
    "Rethrow": render_rethrow,
})


def render_element(elem: Optional[ET.Element], indent: int = 4) -> list[str]:
    if elem is None or is_noise(elem):
        return []

    name = local_name(elem.tag)
    if is_property_node(elem):
        return render_block(elem, indent)

    if name == "ActivityBuilder":
        implementation = child_property(elem, "Implementation") or elem
        return render_block(implementation, indent)

    if name in {"Activity", "Sequence"}:
        display = clean_expr(attr(elem, "DisplayName") or "")
        lines = []
        if display:
            lines.append(" " * indent + f"# Sequence: {display}")
        lines.extend(render_block(elem, indent))
        return lines

    if name == "Assign":
        return render_assign(elem, indent)
    if name == "InvokeWorkflowFile":
        return render_invoke(elem, indent)
    if name == "If":
        return render_if(elem, indent)
    if name == "Switch":
        return render_switch(elem, indent)
    if name in {"While", "DoWhile"}:
        return render_while(elem, indent)
    if name in {"ForEach", "ForEachRow"}:
        return render_for_each(elem, indent)
    if name == "RetryScope":
        return render_retry_scope(elem, indent)
    if name == "TryCatch":
        return render_trycatch(elem, indent)
    if name == "LogMessage":
        return render_log(elem, indent)
    if name == "Throw":
        return render_throw(elem, indent)
    renderer = RENDERERS.get(name)
    if renderer is not None:
        return renderer(elem, indent)

    return render_generic(elem, indent)


def render_block(elem: Optional[ET.Element], indent: int) -> list[str]:
    if elem is None:
        return []
    lines: list[str] = []
    for child in body_children(elem):
        rendered = render_element(child, indent)
        lines.extend(rendered)
    return lines


def build_pseudocode(path: Path) -> str:
    content = path.read_text(encoding="utf-8-sig", errors="replace")
    sha = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()[:12]

    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        return (
            f"# AUTO-GENERATED UIPATH PSEUDOCODE\n"
            f"# Source: {path}\n"
            f"# Parse error: {exc}\n"
            f"# Fallback: raw XAML was not rendered.\n"
        )

    workflow_name = path.stem
    args = collect_arguments(root)
    variables = collect_variables(root)

    lines: list[str] = [
        "# AUTO-GENERATED UIPATH PSEUDOCODE",
        "# This is not executable Python. UiPath expressions are preserved with expr(...).",
        f"# Source: {path}",
        f"# Source SHA256: {sha}",
        "",
    ]

    if args:
        lines.append("# Arguments")
        for a in args:
            lines.append(f"# - {a['direction']} {a['name']}: {a['type']}")
        lines.append("")

    signature = ", ".join(a["name"] for a in args if a["direction"] in {"In", "InOut", "Unknown"})
    lines.append(f"def {snake(workflow_name)}({signature}):")

    if variables:
        lines.append("    # Variables")
        for v in variables:
            default = f" = {expr(v['default'], context=v['name'])}" if v["default"] else " = None"
            lines.append(f"    {v['name']}: '{v['type']}'{default}")
        lines.append("")

    body = render_element(root, 4)
    # Avoid repeating the root-only sequence comment if no real body was found.
    if body:
        lines.extend(body)
    else:
        lines.append("    pass")

    lines.append("")
    return "\n".join(lines)


def iter_xaml_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*.xaml"):
        if any(part in EXCLUDED_PROJECT_DIRS for part in path.parts):
            continue
        files.append(path)
    return sorted(files)


def write_output(output: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert a UiPath .xaml workflow into compact Python-like pseudocode."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", help="Path to one UiPath .xaml file.")
    source.add_argument("--dir", help="Path to a UiPath project directory; converts all .xaml files.")
    parser.add_argument("--out", help="Output file for --file, or output directory for --dir.")
    args = parser.parse_args()

    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"error: file not found: {path}", file=sys.stderr)
            return 2

        output = build_pseudocode(path)
        if args.out:
            write_output(output, Path(args.out))
        else:
            print(output)
        return 0

    root = Path(args.dir)
    if not root.exists() or not root.is_dir():
        print(f"error: directory not found: {root}", file=sys.stderr)
        return 2

    out_dir = Path(args.out) if args.out else root / ".agent-context" / "pseudocode"
    files = iter_xaml_files(root)
    for xaml_path in files:
        relative = xaml_path.relative_to(root).with_suffix(".uipath.py")
        write_output(build_pseudocode(xaml_path), out_dir / relative)

    print(f"converted {len(files)} file(s) to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
