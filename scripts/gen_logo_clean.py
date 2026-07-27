"""Generate a clean SVG logo containing only the ASCII banner from TUI startup."""

from pathlib import Path
from rich.console import Console
from rich.text import Text
from rich.style import Style

OUT = Path(__file__).resolve().parents[1] / "assets"
OUT.mkdir(exist_ok=True)

# Exact ASCII from ui_components.py lines 111-116
ascii_art = [
    "██████████████████████╗     ███████╗████████╗ █████╗ █████████╗██╗██╗  ██╗",
    "██╔══════██╔═══██║╔════╝████████╗██╔══╝██╔══██╗██╔══██╗██╔═════╝██║╚██╗██╔╝",
    "███████╗██║     █████╗  ███████║██╔══╝ █████╔╝ ███████║ ██╔████╔██║ ╚███╔╝ ",
    "██╔══╝  ██║     ╚════╝ ██╔═══╝██╔╝   ██╔═╝  ██╔═██║ ██╔═╚═██║ ██╔██╗ ",
    "███████╗███████╗███████╗███████║███████║███████╗████████╗███╗ █████████╗",
    "╚══════╝╚══════╝╚══════╝╚═════╝╚══════╝╚══════╝╚═════╝ ╚═╝ ╚══════╝╚═╝╚═╝  ╚═╝",
]

console = Console(record=True, width=80, color_system="truecolor")

# Exact style match from ui_components.py
white = Style(bold=True, color="#ffffff")
dim = Style(color="#888888")

console.print()
t = Text()
for i, line in enumerate(ascii_art):
    t.append("  ")
    t.append(line, style=white)
    if i < len(ascii_art) - 1:
        t.append("\n")
console.print(t)
console.print()

svg_path = OUT / "securagentx_logo_clean.svg"
console.save_svg(str(svg_path), title="SecurAgentX ASCII Banner")
print(f"Clean SVG saved to {svg_path}")
