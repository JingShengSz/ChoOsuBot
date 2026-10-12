# AstrBot request-round truncation fix

AstrBot's message-count truncation treated tool calls and results as extra
conversation turns. With a 12-turn limit and a 20-turn trim amount, it could
delete the active user request and restore the first persona example as the
remaining user message. The model then answered that example.

This targeted patch changes the three truncation paths to preserve whole user
request rounds. The round limit keeps the newest 12 requests, including the
active one. System instructions and temporary persona examples do not consume
the request limit. Tool calls, parallel results, generated image messages and
the final-step notice remain in the open tool trajectory until its final
assistant answer.

Token overflow still uses the installed ContextManager and token counter.
Dropping old rounds and halving context always retain the complete latest
request. A single active request is never replaced by an earlier example.
Existing tool-output overflow handling remains available in AstrBot's runner.
The patch adds no LLM calls and does not change the configured token capacity.

## Build and test

Use the installed AstrBot Python environment for tests:

```text
python patch.py --source <installed-truncator.py> --output <candidate-truncator.py>
python verify_context_turns.py --root <AstrBot-root> --source <candidate-truncator.py>
```

The builder replaces only the round truncation methods and adds their shared
round splitter. It preserves unrelated upstream changes and the existing
tool-message repair method. Formatting and tests must pass before installation.

Installation requires backing up the installed truncator, verifying its source
has not changed since building, copying the tested candidate, and restarting
AstrBot. Keep `max_turns=12`; use `trim_turns=1` for token-overflow trimming.
On an AstrBot upgrade, rebuild and test against the new source before reapplying.

The regression suite reproduces both reported user prompts and covers the
12-request bound, persona examples, long tool trajectories, parallel calls,
generated images, excessive drop amounts, token overflow, and halving.

Local validation on 2026-10-10: 11 regression tests and 51 upstream
ContextManager tests passed. No real model requests or QQ messages were sent
by these tests.

Production validation on 2026-10-10: all 11 regression tests passed against
the installed patch. The original failing reproduction now retains all 28
messages and the current skin query. AstrBot restarted successfully; the
service is active and the dashboard responds with HTTP 200. Source and config
were backed up on the server before installation.
