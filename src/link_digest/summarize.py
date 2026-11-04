"""Build the prompt and run Claude to turn a source into a cited report."""

import subprocess
import tempfile
from pathlib import Path

from link_digest.pipeline import Source, format_line

SYSTEM_PROMPT = (
    "You write source-cited reports. You have no tools. Reply only with the report."
)
_PROMPTS = Path(__file__).parent / "prompts"
_CITATION_FORM = '[12:34] "exact words from the source"'
_TIMEOUT_SECONDS = 1800


def _defang(text: str) -> str:
    """Stop untrusted content from closing the <source> block early."""
    return text.replace("</source>", "[/source]")


def build_prompt(source: Source) -> str:
    lines = "\n".join(format_line(segment) for segment in source.segments)
    body = _defang(f"Post text: {source.post_text}\n\nTranscript:\n{lines}")
    # Substitute the source last so its text can never be taken for a placeholder.
    return (
        (_PROMPTS / "report.md")
        .read_text(encoding="utf-8")
        .replace("{citation_form}", _CITATION_FORM)
        .replace("{profile}", (_PROMPTS / "profile.md").read_text(encoding="utf-8"))
        .replace("{source}", body)
    )


def build_command(model: str) -> list[str]:
    # No tools and no settings: post content is untrusted and must not act.
    return [
        "claude",
        "-p",
        "--tools",
        "",
        "--model",
        model,
        "--strict-mcp-config",
        "--no-session-persistence",
        "--disable-slash-commands",
        "--setting-sources",
        "",
        "--system-prompt",
        SYSTEM_PROMPT,
        "--output-format",
        "text",
    ]


def summarize(source: Source, model: str = "sonnet") -> str:
    # A fresh empty cwd so no project instructions are picked up.
    with tempfile.TemporaryDirectory() as cwd:
        try:
            result = subprocess.run(  # noqa: S603 - argument list, no shell
                build_command(model),
                input=build_prompt(source),
                cwd=cwd,
                timeout=_TIMEOUT_SECONDS,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as err:
            raise RuntimeError(f"claude failed: {err.stderr}") from err
        except subprocess.TimeoutExpired as err:
            raise RuntimeError(f"claude timed out after {err.timeout}s") from err
    if not result.stdout.strip():
        raise RuntimeError(f"claude returned no output: {result.stderr}")
    return result.stdout
