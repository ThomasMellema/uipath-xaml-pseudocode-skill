# uipath-xaml-pseudocode skill

This skill converts UiPath `.xaml` workflow files into compact Python-like pseudocode for agent context.

It does not modify the original UiPath project.

## Usage

```bash
python scripts/uipath_xaml_to_pseudocode.py --file Main.xaml --out .agent-context/pseudocode/Main.uipath.py
```

Or write to stdout:

```bash
python scripts/uipath_xaml_to_pseudocode.py --file Main.xaml
```

Convert all workflows in a UiPath project:

```bash
python scripts/uipath_xaml_to_pseudocode.py --dir . --out .agent-context/pseudocode
```

## Purpose

Raw UiPath XAML is noisy. This skill preserves useful workflow logic while dropping designer/viewstate/XML metadata.

Generated files are not executable Python. They are a compact semantic view of the workflow for human and agent analysis.

## Tests

```bash
python -m unittest discover -s tests
```

The tests include small fixtures plus snapshot coverage for broader UiPath activity families and REFramework-style workflows.
