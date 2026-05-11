# uipath-xaml-pseudocode skill

This skill converts UiPath `.xaml` workflow files into compact Python-like pseudocode for agent context.

It does not modify the original UiPath project.

## Usage

```bash
python tools/uipath_xaml_to_pseudocode.py --file Main.xaml --out .agent-context/pseudocode/Main.uipath.py
```

Or write to stdout:

```bash
python tools/uipath_xaml_to_pseudocode.py --file Main.xaml
```

## Purpose

Raw UiPath XAML is noisy. This skill preserves useful workflow logic while dropping designer/viewstate/XML metadata.

Generated files are not executable Python. They are a compact semantic view of the workflow for human and agent analysis.
