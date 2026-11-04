"""Validate, annotate and render a generated report."""

import html
import re

from link_digest.citations import CitationCheck, find_citations

REQUIRED_SECTIONS = (
    "In short",
    "Main points",
    "Steps and methods",
    "Tools and references",
    "Treat with caution",
    "How you could apply this",
)

UNVERIFIED_MARK = " **(unverified)**"

_STYLE = """\
:root { color-scheme: light dark; }
body { font-family: system-ui, sans-serif; line-height: 1.6; max-width: 42rem;
  margin: 0 auto; padding: 1rem; background: #fff; color: #1a1a1a; }
a { color: #0b57d0; }
code { background: #eee; padding: 0.1em 0.3em; border-radius: 3px; }
@media (prefers-color-scheme: dark) {
  body { background: #121212; color: #e6e6e6; }
  a { color: #8ab4f8; }
  code { background: #2a2a2a; }
}
"""

_INLINE = re.compile(
    r"`(?P<code>[^`]+)`"
    r"|\*\*(?P<bold>.+?)\*\*"
    r"|\[(?P<text>[^\]]+)\]\((?P<url>(?:[^\s()]|\([^\s()]*\))+)\)"
)
_HEADING = re.compile(r"(#{1,3}) (.*)")
_ITEM = re.compile(r"(\s*)(?:(-)|\d+\.) (.*)")


def missing_sections(markdown: str) -> list[str]:
    present = {
        line[3:].strip().casefold()
        for line in markdown.splitlines()
        if line.startswith("## ")
    }
    return [name for name in REQUIRED_SECTIONS if name.casefold() not in present]


def mark_unverified(markdown: str, checks: list[CitationCheck]) -> str:
    unverified = {(c.timestamp, c.snippet) for c in checks if not c.verified}
    out = []
    last = 0
    for end, cited in find_citations(markdown):
        out.append(markdown[last:end])
        if any(pair in unverified for pair in cited):
            out.append(UNVERIFIED_MARK)
        last = end
    out.append(markdown[last:])
    return "".join(out)


def _is_web_url(url: str) -> bool:
    return url.lower().startswith(("http://", "https://"))


def _inline(text: str) -> str:
    return _format(html.escape(text))


def _format(escaped: str) -> str:
    """Turn code, bold and safe links in already-escaped text into HTML."""

    def replace(match: re.Match[str]) -> str:
        if match["code"] is not None:
            return f"<code>{match['code']}</code>"
        if match["bold"] is not None:
            return f"<strong>{_format(match['bold'])}</strong>"
        if _is_web_url(html.unescape(match["url"])):
            return f'<a href="{match["url"]}">{match["text"]}</a>'
        return str(match["text"])

    return _INLINE.sub(replace, escaped)


def _list_html(tag: str, items: list[tuple[bool, str]]) -> str:
    """Render items as a list; nested items go in a <ul> inside the previous item."""
    out = [f"<{tag}>"]
    open_item = False
    in_sub = False
    for nested, text in items:
        if nested and open_item:
            if not in_sub:
                out.append("<ul>")
                in_sub = True
            out.append(f"<li>{text}</li>")
            continue
        if in_sub:
            out.append("</ul>")
            in_sub = False
        if open_item:
            out.append("</li>")
        out.append(f"<li>{text}")
        open_item = True
    if in_sub:
        out.append("</ul>")
    if open_item:
        out.append("</li>")
    out.append(f"</{tag}>")
    return "".join(out)


def _body_html(markdown: str) -> str:
    blocks: list[str] = []
    paragraph: list[str] = []
    list_tag = ""
    items: list[tuple[bool, str]] = []

    def flush() -> None:
        nonlocal paragraph, list_tag, items
        if paragraph:
            blocks.append(f"<p>{_inline(' '.join(paragraph))}</p>")
        if items:
            blocks.append(_list_html(list_tag, [(n, _inline(t)) for n, t in items]))
        paragraph, list_tag, items = [], "", []

    for line in markdown.splitlines():
        heading = _HEADING.fullmatch(line)
        item = _ITEM.fullmatch(line)
        if item:
            tag = "ul" if item[2] else "ol"
            if tag != list_tag:
                flush()
                list_tag = tag
            items.append((len(item[1]) >= 2, item[3]))
        elif heading:
            flush()
            level = len(heading[1])
            blocks.append(f"<h{level}>{_inline(heading[2])}</h{level}>")
        elif line.strip():
            if items:
                flush()
            paragraph.append(line.strip())
        else:
            flush()
    flush()
    return "\n".join(blocks)


def render_html(markdown: str, title: str, source_url: str) -> str:
    escaped_url = html.escape(source_url)
    source = (
        f'<a href="{escaped_url}">{escaped_url}</a>'
        if _is_web_url(source_url)
        else escaped_url
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
{_STYLE}</style>
</head>
<body>
<p class="source">Source: {source}</p>
{_body_html(markdown)}
</body>
</html>
"""
