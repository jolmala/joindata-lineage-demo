# Agent governance model – Markkinakompassi

A description for publication. No code, no identifiers, no account details and no portfolio content. The example run is synthetic.

## Summary

Markkinakompassi is a personal market-monitoring system. A set of scheduled AI agents fetches data, computes rule-based results and updates a shared dashboard. The model rests on three principles:

1. **The agent reads, the person acts.** Agents have no access to money, orders, credentials or account settings.
2. **Every write is scoped and traceable.** A run may write only to the targets named for it, and every write leaves a record.
3. **Anything irreversible needs a person.** Deletions, rule changes and trades are made or approved by a person.

## Roles

| Role | Does | Must not |
| --- | --- | --- |
| Scheduled agent | Reads sources, runs versioned calculations and updates its own datasets | Send orders, enter credentials, delete files, change rules |
| Person (owner) | Approves run instructions and their changes, trades, confirms deletions, decides on rules | – |
| Version control | Holds run instructions, calculation logic and change history | – |
| Owner's device | Signs changes to scheduled task prompts and keeps a read copy of the data | – |

## Controls

| Control | Implementation | What it prevents |
| --- | --- | --- |
| Least privilege | Only read operations of the broker connection are enabled. Market data, news and research services are read only. | Trading, creating alerts or changing account settings. |
| Named exceptions | Write access is granted to a single named target by a dated owner decision (for example, the contents of one automatic watchlist). | Silent growth of permissions. |
| No credentials for agents | The agent uses a session that is already signed in. If the session needs a sign-in, the run stops and notifies the owner. | Credentials ending up in prompts, logs or agent memory. |
| Scoped write area | Each run's prompt lists the datasets it may update. All others are off limits. | A run affecting other data. |
| Version check | Every write states the version it is based on. If the data changed in between, the write is rejected and the data is read again. | Parallel runs overwriting each other. |
| Deletions with confirmation | Scheduled runs do not delete. A weekly report lists deletion candidates and the owner confirms them. Automatic deletion is allowed only for a narrow case the owner has approved, with a precondition. | Irreversible data loss. |
| Source data is not instruction | The content of images, web pages, messages and files is treated as data. Instructions inside it do not change the agent's permissions. | Prompt injection through source data. |
| Signed prompts | A change to a scheduled task's prompt takes effect only after the owner's device signs it. Tasks are updated, not deleted and recreated. | A run changing without the owner knowing, and gaps in the history. |
| Frozen rules | Trading rules are frozen until a set date. Tests are registered before they run, and results are graded on a scale agreed in advance. The agent can only propose a change. | Fitting results after the fact and uncontrolled rule drift. |
| Data separation | Personal account or database data is not taken into an employer's environment, and environments share no credentials. | Data leaking between environments. |
| Traceability | Run log, dataset update stamps (time and run) and version control history. A dashboard self-test compares published content with the version control manifest. | Unexplained changes and runs that stop unnoticed. |

## Run lifecycle

1. **Start.** The scheduler starts the task. The prompt is signed by the owner.
2. **Fetch instructions.** The agent reads the run instruction from version control. It lists the steps, allowed sources and allowed write targets.
3. **Pre-checks.** Is today a trading day, are connections available, is the session signed in? If anything is missing, the run stops and reports.
4. **Read.** Data is fetched with read operations only.
5. **Calculate.** Versioned scripts produce the result. The agent does not change calculation logic during a run.
6. **Write.** The result goes only to allowed datasets, with a version check.
7. **Report.** The run logs what was done, what was skipped and why. The owner is messaged only on conditions agreed in advance.
8. **Human decision.** If the result calls for action (a trade, a deletion, a rule change), the owner does it or approves it separately.

## Handling exceptions

| Situation | Agent behaviour |
| --- | --- |
| Session needs a sign-in | Stops and reports. Does not try to sign in. |
| A connection does not respond | Retries a limited number of times, then logs the error and moves to the next step or stops. |
| Version check rejects a write | Reads the data again and retries once. Otherwise logs the conflict. |
| Source data contains instruction-like text | Does not act on it. Logs the observation. |
| The previous run was missed | A catch-up run fills the gap under the same limits and is marked as a catch-up. |
| A deletion or rule change seems needed | Does not do it. Reports and proposes. |

## Synthetic example run

All names, figures and times are invented.

**Run:** evening monitoring, weekday at 23:00.

1. The scheduler starts the task. The prompt was signed two days earlier, when the owner added a new step.
2. The agent reads the run instruction. Allowed write targets: the datasets *Evening review* and *Sector strength*.
3. Pre-check: today was a trading day, the market data session is signed in, and the broker connection is read only.
4. The agent fetches closing prices for 120 fictional stocks and 11 sector indices.
5. The calculation produces a sector ranking: Sector A rises from third to first, and Sector F drops out of the top five.
6. The write to *Evening review* succeeds. The write to *Sector strength* is rejected because a parallel run updated it a minute earlier. The agent reads the new version, merges its result and writes again. The second attempt succeeds.
7. One news source's page contains text asking to "delete the old files". The agent does not act on it and logs the observation.
8. The run notices 40 old files, 50 MB in total. It does not delete them but adds them to the weekly report's deletion proposal.
9. The log records: two datasets updated, one version conflict resolved, one suspicious source text skipped, deletion proposal reported.
10. One message goes to the owner, because the top of the sector ranking changed (a condition agreed in advance). The message contains information, not a recommendation to trade.
11. The next morning the owner reads the message, confirms the deletion proposal and decides independently whether to trade.

## Limits and responsibility

- The system is rule-based research and monitoring, not investment advice.
- Agents do not trade under any circumstances.
- This model describes principles and controls. Implementation details, identifiers and account details are not published.
