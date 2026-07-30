"""Generate an SVG/PNG logo that matches the TUI startup ASCII."""

from pathlib import Path
from rich.console import Console
from rich.text import Text
from rich.style import Style

OUT = Path(__file__).resolve().parents[1] / "assets"
OUT.mkdir(exist_ok=True)

# match the exact ui_components.py layout
ascii_art = [
    "████████╗██╗     ███████╗███╗   ██╗ ██████╗ ███████╗███╗   ██╗██╗██╗  ██╗",
    "██╔════╝██║     ██╔════╝████╗  ██║██╔════╝ ██╔════╝████╗  ██║██║╚██╗██╔╝",
    "█████╗  ██║     █████╗  ██╔██╗ ██║██║  ███╗█████╗  ██╔██╗ ██║██║ ╚███╔╝ ",
    "██╔══╝  ██║     ██╔══╝  ██║╚██╗██║██║   ██║██╔══╝  ██║╚██╗██║██║ ██╔██╗ ",
    "███████╗███████╗███████╗██║ ╚████║╚██████╔╝███████╗██║ ╚████║██║██╔╝ ██╗",
    "╚══════╝╚══════╝╚══════╝╚═╝  ╚═══╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝╚═╝╚═╝  ╚═╝",
]

console = Console(record=True, width=78, color_system="truecolor")

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
sub = Text("           Universal AI & Bug Bounty Agent", style=dim)
console.print(sub)
sub2 = Text("           Type /help for commands", style=dim)
console.print(sub2)
console.print()

svg_path = OUT / "securagentx_logo.svg"
console.save_svg(str(svg_path), title="SecurAgentX")
print(f"SVG saved to {svg_path}")
