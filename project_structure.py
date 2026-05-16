#!/usr/bin/env python3
"""
Project Structure Visualizer — FraudGuard AI
=============================================
Generates:
  1. A coloured ASCII tree printed to the console
  2. A Graphviz (.gv) source file  →  project_structure.gv
  3. Optional PNG/SVG render if the `graphviz` Python package is installed

Usage:
    python project_structure.py              # ASCII + .gv file
    python project_structure.py --render     # also render to PNG (needs graphviz pkg)
    python project_structure.py --svg        # render to SVG

Install graphviz Python package (optional):
    pip install graphviz
"""

import os
import sys
import textwrap
from pathlib import Path

# ── Directories / files to skip ──────────────────────────────────────────────
SKIP_DIRS  = {
    '__pycache__', '.git', 'venv', '.venv', 'env',
    'node_modules', '.idea', '.vscode', 'dist', 'build',
    '.mypy_cache', '.pytest_cache', 'htmlcov',
}
SKIP_FILES = {'.DS_Store', 'Thumbs.db', '*.pyc', '*.pyo'}

# ── File-type → (colour hex, Graphviz shape, display label) ──────────────────
FILE_META = {
    '.py':    ('#3b82f6', 'box',     'Python'),
    '.html':  ('#f97316', 'box',     'HTML'),
    '.css':   ('#8b5cf6', 'box',     'CSS'),
    '.js':    ('#eab308', 'box',     'JavaScript'),
    '.txt':   ('#10b981', 'note',    'Text'),
    '.md':    ('#06b6d4', 'note',    'Markdown'),
    '.json':  ('#ec4899', 'box',     'JSON'),
    '.env':   ('#ef4444', 'note',    'Env'),
    '.sql':   ('#f59e0b', 'box',     'SQL'),
    '.bat':   ('#6b7280', 'box',     'Batch'),
    '.pkl':   ('#84cc16', 'cylinder','Model'),
    '.csv':   ('#22d3ee', 'note',    'CSV'),
}

DIR_COLOUR  = '#1e3a5f'
DIR_BG      = '#38bdf8'
ROOT_COLOUR = '#0ea5e9'

# ── ANSI colour helpers ───────────────────────────────────────────────────────
ANSI = {
    'reset':  '\033[0m',
    'bold':   '\033[1m',
    'blue':   '\033[94m',
    'cyan':   '\033[96m',
    'green':  '\033[92m',
    'yellow': '\033[93m',
    'red':    '\033[91m',
    'purple': '\033[95m',
    'white':  '\033[97m',
    'dim':    '\033[2m',
}

EXT_ANSI = {
    '.py':   'blue',
    '.html': 'yellow',
    '.css':  'purple',
    '.js':   'yellow',
    '.txt':  'green',
    '.md':   'cyan',
    '.json': 'red',
    '.pkl':  'green',
    '.bat':  'dim',
    '.env':  'red',
}


def _colour(text: str, *codes: str) -> str:
    if not sys.stdout.isatty():
        return text
    prefix = ''.join(ANSI.get(c, '') for c in codes)
    return f"{prefix}{text}{ANSI['reset']}"


# ── ASCII Tree ────────────────────────────────────────────────────────────────
def ascii_tree(root: Path, prefix: str = '') -> list[str]:
    """Return list of lines forming a coloured ASCII directory tree."""
    entries = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    entries = [e for e in entries
               if not (e.is_dir() and e.name in SKIP_DIRS)
               and e.name not in SKIP_FILES]

    lines = []
    for i, entry in enumerate(entries):
        is_last  = (i == len(entries) - 1)
        connector = '└── ' if is_last else '├── '
        extension = '    ' if is_last else '│   '

        if entry.is_dir():
            name = _colour(entry.name + '/', 'cyan', 'bold')
            lines.append(f"{prefix}{connector}{name}")
            lines.extend(ascii_tree(entry, prefix + extension))
        else:
            ext  = entry.suffix.lower()
            col  = EXT_ANSI.get(ext, 'white')
            name = _colour(entry.name, col)
            size = _file_size(entry)
            lines.append(f"{prefix}{connector}{name}  {_colour(size, 'dim')}")

    return lines


def _file_size(path: Path) -> str:
    try:
        b = path.stat().st_size
        if b < 1024:       return f"{b} B"
        if b < 1_048_576:  return f"{b/1024:.1f} KB"
        return f"{b/1_048_576:.1f} MB"
    except OSError:
        return ''


def print_ascii_tree(root: Path) -> None:
    header = _colour('═' * 58, 'cyan')
    title  = _colour('  FraudGuard AI  —  Project Structure', 'cyan', 'bold')
    print(f"\n{header}\n{title}\n{header}")
    print(_colour(root.name + '/', 'cyan', 'bold'))
    for line in ascii_tree(root):
        print(line)
    print()


# ── Graphviz (.gv) Generator ──────────────────────────────────────────────────
def _safe_id(path: Path, root: Path) -> str:
    """Create a valid Graphviz node ID from a path."""
    return '"' + str(path.relative_to(root)).replace('\\', '/').replace('"', '\\"') + '"'


def _gv_colour(path: Path) -> tuple[str, str]:
    """Return (fillcolor, fontcolor) for a Graphviz node."""
    if path.is_dir():
        return DIR_BG, 'white'
    meta = FILE_META.get(path.suffix.lower())
    if meta:
        return meta[0], 'white'
    return '#334155', '#94a3b8'


def _gv_shape(path: Path) -> str:
    if path.is_dir():
        return 'folder'
    meta = FILE_META.get(path.suffix.lower())
    return meta[1] if meta else 'box'


def _gv_label(path: Path) -> str:
    if path.is_dir():
        return path.name + '/'
    return path.name


def build_graphviz(root: Path) -> str:
    """Build and return a complete Graphviz .gv source string."""

    nodes: list[str] = []
    edges: list[str] = []

    # Root node
    root_id = _safe_id(root, root.parent)
    nodes.append(
        f'  {root_id} '
        f'[label="{root.name}/", shape=house, '
        f'fillcolor="{ROOT_COLOUR}", fontcolor="white", '
        f'fontsize=13, fontname="Inter Bold", style="filled,bold", penwidth=2];'
    )

    def walk(directory: Path) -> None:
        entries = sorted(directory.iterdir(),
                         key=lambda p: (p.is_file(), p.name.lower()))
        for entry in entries:
            if entry.is_dir() and entry.name in SKIP_DIRS:
                continue
            if entry.is_file() and entry.name in SKIP_FILES:
                continue

            nid   = _safe_id(entry, root.parent)
            pid   = _safe_id(directory, root.parent)
            fc, _ = _gv_colour(entry)
            shape = _gv_shape(entry)
            label = _gv_label(entry)
            fsize = 10 if entry.is_file() else 11
            bwidth = 0 if entry.is_file() else 1

            nodes.append(
                f'  {nid} '
                f'[label="{label}", shape={shape}, '
                f'fillcolor="{fc}", fontcolor="white", '
                f'fontsize={fsize}, fontname="Inter", '
                f'style="filled,rounded", penwidth={bwidth}, height=0.28];'
            )
            edges.append(
                f'  {pid} -> {nid} '
                f'[color="#{("38bdf8" if directory == root else "1e3a5f")}", '
                f'arrowsize=0.5, penwidth=0.8];'
            )

            if entry.is_dir():
                walk(entry)

    walk(root)

    # Legend
    legend_entries = [
        ('Python (.py)',   '#3b82f6'),
        ('HTML (.html)',   '#f97316'),
        ('CSS (.css)',     '#8b5cf6'),
        ('JS (.js)',       '#eab308'),
        ('Knowledge (.txt)', '#10b981'),
        ('ML Model (.pkl)', '#84cc16'),
        ('Config/Env',    '#ef4444'),
        ('Directory',     '#38bdf8'),
    ]
    legend_nodes = '\n'.join(
        f'  legend_{i} [label="{lbl}", fillcolor="{col}", shape=box, '
        f'fontcolor="white", fontsize=9, fontname="Inter", style="filled,rounded", '
        f'height=0.22, width=1.4];'
        for i, (lbl, col) in enumerate(legend_entries)
    )
    legend_chain = ' -> '.join(f'legend_{i}' for i in range(len(legend_entries)))
    legend_rank  = f'{{ rank=same; {"; ".join(f"legend_{i}" for i in range(len(legend_entries)))} }}'

    gv = textwrap.dedent(f"""\
        // ═══════════════════════════════════════════════════════
        //  FraudGuard AI — Project Structure Diagram
        //  Generated by project_structure.py
        //  Render:  dot -Tpng project_structure.gv -o project_structure.png
        //           dot -Tsvg project_structure.gv -o project_structure.svg
        // ═══════════════════════════════════════════════════════

        digraph FraudGuardAI {{
          graph [
            rankdir    = "LR",
            bgcolor    = "#040915",
            fontname   = "Inter",
            pad        = "0.6",
            splines    = "ortho",
            nodesep    = "0.4",
            ranksep    = "1.0",
            label      = "FraudGuard AI — Project Architecture",
            labelloc   = "t",
            fontcolor  = "#38bdf8",
            fontsize   = 16,
          ];

          // ── Nodes ───────────────────────────────────────────
        {chr(10).join(nodes)}

          // ── Edges ───────────────────────────────────────────
        {chr(10).join(edges)}

          // ── Legend ──────────────────────────────────────────
          subgraph cluster_legend {{
            label      = "File Type Legend";
            fontcolor  = "#38bdf8";
            fontsize   = 10;
            bgcolor    = "#0a1628";
            color      = "#1e3a5f";
            style      = "filled,rounded";

        {legend_nodes}
            {legend_chain} [style=invis];
            {legend_rank}
          }}
        }}
    """)

    return gv


# ── Entry Point ───────────────────────────────────────────────────────────────
def main() -> None:
    root = Path(__file__).parent.resolve()

    # ── 1. Console ASCII tree ────────────────────────────────────────────────
    print_ascii_tree(root)

    # ── 2. Generate Graphviz source ──────────────────────────────────────────
    gv_source = build_graphviz(root)
    gv_path   = root / 'project_structure.gv'
    gv_path.write_text(gv_source, encoding='utf-8')
    print(f"[Graphviz]  Source written  →  {gv_path}")
    print(f"[Graphviz]  Render with:        dot -Tpng project_structure.gv -o project_structure.png")
    print(f"[Graphviz]  Or SVG:             dot -Tsvg project_structure.gv -o project_structure.svg")

    # ── 3. Optional: render with graphviz Python package ────────────────────
    render_png = '--render' in sys.argv
    render_svg = '--svg'    in sys.argv

    if render_png or render_svg:
        try:
            import graphviz  # pip install graphviz
            fmt    = 'svg' if render_svg else 'png'
            src    = graphviz.Source(gv_source, engine='dot', format=fmt)
            output = src.render(filename='project_structure', cleanup=True)
            print(f"[Graphviz]  Rendered         →  {output}")
        except ImportError:
            print("[Graphviz]  Install the graphviz package to auto-render:")
            print("            pip install graphviz")
        except Exception as e:
            print(f"[Graphviz]  Render error: {e}")
            print("            Make sure Graphviz is installed:  https://graphviz.org/download/")

    # ── Summary stats ────────────────────────────────────────────────────────
    total_py   = sum(1 for _ in root.rglob('*.py')   if not any(s in str(_) for s in SKIP_DIRS))
    total_html = sum(1 for _ in root.rglob('*.html') if not any(s in str(_) for s in SKIP_DIRS))
    total_js   = sum(1 for _ in root.rglob('*.js')   if not any(s in str(_) for s in SKIP_DIRS))
    total_css  = sum(1 for _ in root.rglob('*.css')  if not any(s in str(_) for s in SKIP_DIRS))
    total_txt  = sum(1 for _ in root.rglob('*.txt')  if not any(s in str(_) for s in SKIP_DIRS))

    print(f"\n{'═'*45}")
    print(f"  File summary")
    print(f"{'═'*45}")
    print(f"  Python files      :  {total_py}")
    print(f"  HTML templates    :  {total_html}")
    print(f"  JavaScript files  :  {total_js}")
    print(f"  CSS stylesheets   :  {total_css}")
    print(f"  Knowledge docs    :  {total_txt}")
    print(f"{'═'*45}\n")


if __name__ == '__main__':
    main()
