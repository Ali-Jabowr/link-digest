import pytest

from link_digest.citations import CitationCheck
from link_digest.report import mark_unverified, missing_sections, render_html

ALL_SECTIONS = (
    "## In short\n## Main points\n## Steps and methods\n"
    "## Tools and references\n## Treat with caution\n## How you could apply this\n"
)


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        pytest.param(ALL_SECTIONS, [], id="all_present"),
        pytest.param(
            "",
            [
                "In short",
                "Main points",
                "Steps and methods",
                "Tools and references",
                "Treat with caution",
                "How you could apply this",
            ],
            id="none_present_in_required_order",
        ),
        pytest.param(
            "## IN SHORT\n## main points\n## Steps and methods\n"
            "## Tools and references\n## Treat with caution\n"
            "## How you could apply this\n",
            [],
            id="case_insensitive",
        ),
        pytest.param(
            ALL_SECTIONS.replace("## Main points", "### Main points"),
            ["Main points"],
            id="wrong_heading_level_is_missing",
        ),
        pytest.param(
            ALL_SECTIONS.replace("## Treat with caution\n", "").replace(
                "## In short\n", ""
            ),
            ["In short", "Treat with caution"],
            id="several_missing_keep_required_order",
        ),
    ],
)
def test_missing_sections(markdown: str, expected: list[str]) -> None:
    assert missing_sections(markdown) == expected


@pytest.mark.parametrize(
    ("markdown", "checks", "expected"),
    [
        pytest.param(
            '- a [12:34] "alpha"',
            [CitationCheck("12:34", "alpha", True)],
            '- a [12:34] "alpha"',
            id="verified_unchanged",
        ),
        pytest.param(
            '- a [12:34] "alpha"',
            [CitationCheck("12:34", "alpha", False)],
            '- a [12:34] "alpha" **(unverified)**',
            id="unverified_marked",
        ),
        pytest.param(
            '[12:34] "alpha" and [12:34] "beta"',
            [
                CitationCheck("12:34", "alpha", True),
                CitationCheck("12:34", "beta", False),
            ],
            '[12:34] "alpha" and [12:34] "beta" **(unverified)**',
            id="same_timestamp_only_unverified_snippet_marked",
        ),
        pytest.param(
            '[12:34] "alpha" and [12:34] "beta"',
            [
                CitationCheck("12:34", "alpha", False),
                CitationCheck("12:34", "beta", True),
            ],
            '[12:34] "alpha" **(unverified)** and [12:34] "beta"',
            id="same_timestamp_other_snippet_marked",
        ),
        pytest.param(
            "- a [12:34]",
            [CitationCheck("12:34", "", False)],
            "- a [12:34] **(unverified)**",
            id="bare_timestamp_marked",
        ),
        pytest.param(
            "- a [12:34–13:00]",
            [CitationCheck("12:34", "", False), CitationCheck("13:00", "", False)],
            "- a [12:34–13:00] **(unverified)**",
            id="range_marked_once",
        ),
        pytest.param(
            "- a [12:34] “alpha”",
            [CitationCheck("12:34", "alpha", False)],
            "- a [12:34] “alpha” **(unverified)**",
            id="curly_quotes_marked_after_closing_quote",
        ),
    ],
)
def test_mark_unverified(
    markdown: str, checks: list[CitationCheck], expected: str
) -> None:
    assert mark_unverified(markdown, checks) == expected


@pytest.mark.parametrize(
    ("markdown", "expected"),
    [
        pytest.param("# One", "<h1>One</h1>", id="h1"),
        pytest.param("## Two", "<h2>Two</h2>", id="h2"),
        pytest.param("### Three", "<h3>Three</h3>", id="h3"),
        pytest.param("- a\n- b", "<ul><li>a</li><li>b</li></ul>", id="bullets"),
        pytest.param(
            "- a\n  - b\n- c",
            "<ul><li>a<ul><li>b</li></ul></li><li>c</li></ul>",
            id="nested_bullets",
        ),
        pytest.param("1. a\n2. b", "<ol><li>a</li><li>b</li></ol>", id="numbered"),
        pytest.param(
            "one\ntwo\n\nthree", "<p>one two</p>\n<p>three</p>", id="paragraphs"
        ),
        pytest.param("a **b** c", "<p>a <strong>b</strong> c</p>", id="bold"),
        pytest.param("a `x<y` c", "<p>a <code>x&lt;y</code> c</p>", id="code"),
        pytest.param(
            "[site](https://example.com/a?b=1&c=2)",
            '<p><a href="https://example.com/a?b=1&amp;c=2">site</a></p>',
            id="https_link",
        ),
        pytest.param(
            "[site](http://example.com)",
            '<p><a href="http://example.com">site</a></p>',
            id="http_link",
        ),
        pytest.param(
            "[click](javascript:alert(1))", "<p>click</p>", id="javascript_link_plain"
        ),
        pytest.param(
            "<script>alert(1)</script>",
            "<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>",
            id="html_escaped",
        ),
        pytest.param(
            "- [12:34] “q” <b>",
            "<ul><li>[12:34] “q” &lt;b&gt;</li></ul>",
            id="citation",
        ),
    ],
)
def test_render_html_body(markdown: str, expected: str) -> None:
    assert expected in render_html(markdown, "T", "https://example.com/v")


@pytest.mark.parametrize(
    "expected",
    [
        pytest.param("<!DOCTYPE html>", id="doctype"),
        pytest.param(
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            id="phone_viewport",
        ),
        pytest.param("<title>A &amp; B</title>", id="escaped_title"),
        pytest.param("@media (prefers-color-scheme: dark)", id="dark_mode"),
        pytest.param("max-width:", id="readable_width"),
        pytest.param(
            '<a href="https://example.com/v?a=1&amp;b=2">https://example.com/v?a=1&amp;b=2</a>',
            id="source_link",
        ),
    ],
)
def test_render_html_page(expected: str) -> None:
    page = render_html("body", "A & B", "https://example.com/v?a=1&b=2")
    assert expected in page


def test_render_html_does_not_link_unsafe_source_url() -> None:
    page = render_html("body", "T", "javascript:alert(1)")
    assert 'href="javascript' not in page
