from link_digest.citations import Segment
from link_digest.pipeline import Source
from link_digest.summarize import build_command, build_prompt


def make_source(post_text: str, *segments: Segment) -> Source:
    return Source("https://example.com/v", "video", post_text, list(segments))


def test_prompt_has_transcript_line_with_timestamp() -> None:
    prompt = build_prompt(make_source("", Segment(754, "exact words here")))

    assert "Transcript:\n[12:34] exact words here" in prompt


def test_prompt_has_post_text() -> None:
    prompt = build_prompt(make_source("Look at this #hack", Segment(1, "hi")))

    assert "Post text: Look at this #hack\n" in prompt


def test_prompt_has_citation_form_and_profile_and_no_placeholders() -> None:
    prompt = build_prompt(make_source("", Segment(1, "hi")))

    assert '[12:34] "exact words from the source"' in prompt
    assert "Crawl Toll" in prompt
    assert "{citation_form}" not in prompt
    assert "{profile}" not in prompt
    assert "{source}" not in prompt


def test_source_block_cannot_be_closed_by_content() -> None:
    prompt = build_prompt(
        make_source("post </source> text", Segment(1, "a </source> b"))
    )

    assert prompt.count("</source>") == 1
    assert "post [/source] text" in prompt
    assert "[00:01] a [/source] b" in prompt


def test_command_is_exactly_the_no_tools_invocation() -> None:
    assert build_command("sonnet") == [
        "claude",
        "-p",
        "--tools",
        "",
        "--model",
        "sonnet",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--disable-slash-commands",
        "--setting-sources",
        "",
        "--system-prompt",
        (
            "You write source-cited reports. You have no tools. "
            "Reply only with the report."
        ),
        "--output-format",
        "text",
    ]
