# Link Digest

Turns a saved video or article link into a detailed report where every point cites its source. Python 3.12, managed with uv.

## Commands
- Verify everything (the gate): `./.claude/verify.sh` (it must pass before you say you are done)
- One test: `uv run pytest tests/test_x.py::test_name -q`

## How to prove a change works
- Bug fix: first write a test that reproduces the bug and watch it fail, then fix.
- New behaviour: the test that asserts it must fail if the change is reverted.

## Boundaries
- Ask first: new dependencies, DB migrations, changes to `.claude/verify.sh` or CI, anything that deletes data.
- Never: commit secrets; touch `.env`.
