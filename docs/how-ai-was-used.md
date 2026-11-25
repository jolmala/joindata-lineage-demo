# How AI was used

The code in this repository was written with Claude Code. The way of working matters more than the tool, so it is described here.

## Working method

1. **Specification first.** Each part started from a written statement of inputs, outputs and the cases it must handle, for example "a manually uploaded file with no pipeline must show as a break" or "share capital must trace only to the capital register, not to every source of the table".
2. **Expected results before code.** The synthetic data was designed so that the correct answer is known: one break, two stale cells, two reconciliation differences, four unscheduled mappings. The tests check those numbers.
3. **AI writes, a person reviews.** The assistant drafted parsers and the report; every change was read, run and checked against the tests before it was kept.
4. **Problems found by checking, not by trust.** Two examples from development:
   - The first version traced at table level, so every report cell appeared to depend on every source. Column-level lineage from Unity Catalog and the view select lists fixed it; `test_column_level_trace_is_precise` guards it.
   - The lineage graph initially put bronze, silver and gold tables in one column, which hid the order of loads. The layout was changed after looking at the rendered report.

## Boundaries

- Only synthetic data and public template codes are used. No client data, credentials or environment names are in this repository.
- The repository has a fresh history and was scanned for secrets and personal data before publishing.
