## What & why
<!-- 1–3 sentences. Link the spec/ticket/ADR, but this must still make sense if links die. -->

## How it works
<!-- Approach chosen. Alternatives rejected and why. -->

## Proof it works
<!-- Commands you ran + pasted output, or a screenshot. Which tests assert the requirement? -->
- [ ] Each new test was seen FAILING before the fix, and passing after
- [ ] I ran the change myself once (not only the tests)

## AI involvement
- Tool / model:
- Extent: <!-- scaffolded / wrote X, I rewrote Y / review only -->
- [ ] I read every line of this diff and can explain it

## Review checklist (AI-specific)
- [ ] No invented APIs, flags or packages; new dependencies checked on the registry (owner, age, downloads)
- [ ] Solves the ticket, not a "plausible nearby problem"; nothing outside the ticket's scope changed
- [ ] Error paths handled; no swallowed errors (`_ = err`, bare `except`)
- [ ] Tests check behaviour, not the implementation; no asserts on mocks; expected values are literals
- [ ] No duplicated helpers (searched for existing ones); no needless abstraction
- [ ] No secrets or credentials; inputs validated
- [ ] AI reviewer findings triaged (accepted / rejected + why)

## Known gaps / follow-ups
