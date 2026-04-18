---
description: Triage recent iMessages (default 2 days)
argument-hint: [days]
---

Run an iMessage triage review using the `imessage-review` skill.

## What to do

1. Load the `imessage-review` skill if you haven't already.
2. Parse the user's argument. If they passed a number, use it as `days`.
   Otherwise default to `2` days.
3. Verify the bridge folder is selected and the helper is installed (see
   the skill's "Prerequisites" section). If either check fails, stop and
   guide the user through setup instead of issuing a request.
4. Write a `review` request to `<bridge folder>/control/requests/`:

   ```json
   {"id": "<short-uuid>", "action": "review", "params": {"days": <days>}}
   ```

5. Poll the matching response file in `<bridge folder>/control/responses/`
   for up to 30 seconds (0.5s interval). When it arrives, parse the JSON.
6. Present the three buckets to the user:

   - **Needs reply** — full message text, sender, timestamp. Rank by how
     actionable each item looks; surface any questions the user hasn't
     answered.
   - **Low priority** — one-line summary per thread (sender, topic).
   - **Skipped** — count only. Do not print text (the helper redacts it).

7. After the summary, offer concrete next steps: draft replies to the
   "needs reply" items, dig into a specific thread, or pull
   `response_stats` for anyone with a slow reply time.

## Examples

- `/imessages` → triage the last 2 days
- `/imessages 7` → triage the last week
- `/imessages 1` → just today + yesterday
