"""Ambrosia — fast TUI-first command launcher and executor workbench.

Ambrosia lets an operator register any shell command with a name, description,
tags, and a ``{{input_id}}`` shell template, then search and run it from a
single Textual TUI. Inputs are remembered per session, output streams live,
and jobs can be cancelled or re-run.

It is built for authorized use (penetration testing, red teaming, sysadmin
work, anything the operator is authorized to run). Ambrosia does not install,
download, or bundle offensive tools — the operator brings the binaries on
PATH and Ambrosia runs them through an argv array (no ``shell=True``).
"""

__version__ = "0.2.0"

__all__ = ["__version__"]
