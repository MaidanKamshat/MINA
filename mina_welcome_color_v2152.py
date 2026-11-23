"""v2.15.2: reuse the installed original welcome-page name accent.

Does not require Streamlit or new dependencies and never transmits CSS/data.
Matches the last .mina-name-specific color declaration in the three original
CSS theme layers that the main app loads before the v2.15.1 polish layer.
"""

from pathlib import Path
import re

_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.S)
_CLASS = re.compile(r"\.mina-name(?![\w-])")
_COLOR = re.compile(r"(?:^|;)\s*color\s*:\s*([^;]+)", re.I)
_SAFE = re.compile(
    r"(?:#[\da-fA-F]{3,8}|[a-zA-Z-]+|(?:var|rgb|rgba|hsl|hsla|oklch)\([^{};<>]*\))\Z"
)


def original_brand_accent(paths: tuple[Path, ...]) -> str | None:
    """Return prior `.mina-name` CSS color expression, or None if unknown.

    The CSS is from trusted installed theme files. We return only a CSS color
    expression (not arbitrary declarations). If unknown, the existing heading
    remains unmodified and its original theme takes precedence.
    """
    last = None
    for path in paths:
        try:
            css = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        for match in _RULE.finditer(css):
            selector_list, declarations = match.groups()
            if not any(_CLASS.search(part) for part in selector_list.split(",")):
                continue
            for found in _COLOR.finditer(declarations):
                color = re.sub(r"\s*!important\s*$", "", found.group(1), flags=re.I).strip()
                if _SAFE.fullmatch(color) and color.lower() not in {"inherit", "initial", "unset", "revert", "transparent"}:
                    last = color
    return last
