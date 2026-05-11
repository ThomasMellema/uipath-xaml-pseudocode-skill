
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable, Optional


SKIP_NODE_NAMES = {
    "TextExpression.NamespacesForImplementation",
    "TextExpression.ReferencesForImplementation",
    "WorkflowViewStateService.ViewState",
    "ActivityBuilder.Implementation",
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
                ".variables", ".displayname", ".selector", ".text", ".message"
            ]):
                continue
            result.extend(body_children(child))
            continue

        # Skip definitions collected separately.
        if name in {"Members", "Property", "Variable"}:
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


def expr(value: str) -> str:
    value = clean_expr(value)
    if not value:
        return "None"
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
            "default": clean_expr(default),
        })
    return variables


def render_assign(elem: ET.Element, indent: int) -> list[str]:
    to_value = all_text(child_property(elem, "To"))
    from_value = all_text(child_property(elem, "Value"))
    if not to_value:
        to_value = attr(elem, "To") or ""
    if not from_value:
        from_value = attr(elem, "Value") or ""

    line = f"{to_value or '_'} = {expr(from_value)}"
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
    workflow = clean_expr(attr(elem, "WorkflowFileName") or attr(elem, "FileName") or "")
    display = clean_expr(attr(elem, "DisplayName") or "")
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
            rendered = f"out({py_str(value)})" if value else "out(None)"
        elif kind == "InOutArgument":
            rendered = f"inout({py_str(value)})" if value else "inout(None)"
        else:
            rendered = expr(value)
        lines.append(prefix + f"    {key}={rendered},")

    lines.append(prefix + ")")
    return lines


def render_if(elem: ET.Element, indent: int) -> list[str]:
    condition = clean_expr(attr(elem, "Condition") or all_text(child_property(elem, "Condition")))
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


def render_while(elem: ET.Element, indent: int) -> list[str]:
    condition = clean_expr(attr(elem, "Condition") or all_text(child_property(elem, "Condition")))
    lines = [" " * indent + f"while {expr(condition)}:"]
    body = child_property(elem, "Body") or elem
    body_lines = render_block(body, indent + 4)
    lines.extend(body_lines or [" " * (indent + 4) + "pass"])
    return lines


def render_for_each(elem: ET.Element, indent: int) -> list[str]:
    display = clean_expr(attr(elem, "DisplayName") or "")
    values = clean_expr(attr(elem, "Values") or all_text(child_property(elem, "Values")))
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
    level = clean_expr(attr(elem, "Level") or "Info")
    message = clean_expr(attr(elem, "Message") or all_text(child_property(elem, "Message")))
    return [" " * indent + f"log(level={py_str(level)}, message={expr(message)})"]


def render_throw(elem: ET.Element, indent: int) -> list[str]:
    exception = clean_expr(attr(elem, "Exception") or all_text(child_property(elem, "Exception")))
    return [" " * indent + f"raise_uipath_exception({expr(exception)})"]


IMPORTANT_ATTRS = [
    "DisplayName",
    "Text",
    "Value",
    "To",
    "FileName",
    "WorkbookPath",
    "SheetName",
    "Range",
    "QueueName",
    "TransactionItem",
    "AssetName",
    "TimeoutMS",
    "ContinueOnError",
    "Url",
    "Method",
    "Endpoint",
    "Subject",
    "Folder",
]


def render_generic(elem: ET.Element, indent: int) -> list[str]:
    name = local_name(elem.tag)
    call = snake(name)
    kwargs: list[str] = []

    for key in IMPORTANT_ATTRS:
        value = clean_expr(attr(elem, key) or "")
        if value:
            if key in {"Text", "Value", "To", "QueueName", "AssetName", "Url", "Endpoint"}:
                kwargs.append(f"{snake(key)}={expr(value)}")
            else:
                kwargs.append(f"{snake(key)}={py_str(value)}")

    selector = attr(elem, "Selector")
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

    nested = []
    for child in body_children(elem):
        nested.extend(render_element(child, indent + 4))
    if nested:
        lines.extend(nested)
    return lines


def render_element(elem: Optional[ET.Element], indent: int = 4) -> list[str]:
    if elem is None or is_noise(elem):
        return []

    name = local_name(elem.tag)
    if is_property_node(elem):
        return render_block(elem, indent)

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
    if name in {"While", "DoWhile"}:
        return render_while(elem, indent)
    if name in {"ForEach", "ForEachRow"}:
        return render_for_each(elem, indent)
    if name == "TryCatch":
        return render_trycatch(elem, indent)
    if name == "LogMessage":
        return render_log(elem, indent)
    if name in {"Throw", "Rethrow"}:
        return render_throw(elem, indent)

    return render_generic(elem, indent)


def render_block(elem: Optional[ET.Element], indent: int) -> list[str]:
    if elem is None:
        return []
    lines: list[str] = []
    for child in body_children(elem):
        rendered = render_element(child, indent)
        lines.extend(rendered)
    return lines


def build_pseudocode(path: Path, mode: str = "standard") -> str:
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
            default = f" = {expr(v['default'])}" if v["default"] else " = None"
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert a UiPath .xaml workflow into compact Python-like pseudocode."
    )
    parser.add_argument("--file", required=True, help="Path to a UiPath .xaml file.")
    parser.add_argument("--out", help="Output path. Defaults to stdout.")
    parser.add_argument("--mode", choices=["summary", "standard", "debug"], default="standard")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 2

    output = build_pseudocode(path, mode=args.mode)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
