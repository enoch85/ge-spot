---
applyTo: "**"
---

# Pull request workflow

- Reproduce a reported bug before changing behavior. Record the trigger and the
  observed result; distinguish confirmed defects from suspicions.
- Trace callers, shared services, caches, scheduled and manual actions, and
  recovery. Read blame, related PRs and issues, and the relevant official API
  documentation. Do not infer API guarantees from an error message.
- Make the smallest complete fix. Reuse the existing coordinator, services, and
  native Home Assistant UI. Avoid unrelated refactors and cosmetic changes.
- Keep tests focused on observable behavior. Extend existing cases where useful,
  and establish that a regression case fails against the affected old behavior.
- Use the real available Podman/Home Assistant environment for affected flows:
  inspect API responses, actual state, logs, and the UI with Playwright. Report
  unavailable providers or services and restore temporary fixtures.
- Run focused checks during development. Before committing or updating a PR,
  run the full Python test suite, formatting, and relevant lint checks. Run from
  a clean checkout or exclude unrelated nested checkouts and installed packages.
- Fetch the latest base before updating a branch. Keep unpublished work in
  coherent commits, preserve published history, and verify that the remote-to-local
  comparison is a clean fast-forward before pushing. Do not force-push.
- Keep the PR title and body about the final implementation: a short summary of
  what changed and why, followed by a few concrete bullets. Include useful
  validation evidence and limitations inline, without a separate "Test plan"
  section or attribution footer. Rewrite the description if the scope changes.

## Logging and recovery

- Expected missing forecasts, rate limits, timeouts, fallback, cache use, and
  scheduled retries belong at DEBUG. A handled request failure is not an
  integration failure.
- Reserve warnings for actionable configuration problems or sustained loss of
  usable data. Log those once until recovery. Reserve errors for serious failures
  such as invalid credentials or unexpected implementation errors.
- Trace repeated messages to their cause. Check for duplicate polling, nested
  retry loops, incorrect market-time assumptions, and failure states that never
  become eligible for retry. Changing severity alone does not repair such bugs.
- Preserve unavailable states and diagnostic details when prices are unknown.
  Never fabricate zero prices or costs to make the logs or UI look healthy.
