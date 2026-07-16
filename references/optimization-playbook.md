# Skill Optimization Playbook

Use this playbook after deterministic evidence collection. Every recommendation should connect to token cost reduction and success-risk control.

## Primary Metric

Optimize for:

```text
token cost per successful skill-related task
```

Use real token usage when logs provide it. Otherwise use:

- main `SKILL.md` token estimate
- section token estimates
- related session text token proxy
- turns, tool calls, commands, and retries as cost proxies

Prefer reported token fields over estimates:

```text
reported_total_tokens > session_token_proxy_total > main_token_estimate
```

When reported tokens are absent, call the metric a proxy.

## Version Windows

Do not compare or aggregate sessions from different Skill versions as one population.

Use separate windows:

```text
baseline window: sessions produced by the old version
candidate/adopted window: sessions produced after the new version was adopted
```

If the Skill has no prior optimization record, create a baseline run record. If a candidate was adopted, set `adopted_at` and make the next analysis default to `--since adopted_at`.

Minimal run record:

```json
{
  "skill_id": "my-test-skill",
  "baseline_version": "0.2.0",
  "candidate_version": "0.3.0-candidate",
  "baseline_window": {"since": null, "until": "2026-07-15T00:00:00Z"},
  "adopted_at": null,
  "report_path": "optimization-report.md",
  "candidate_path": "SKILL.candidate.md"
}
```

When reporting token savings, distinguish:

- static savings: candidate main file tokens vs baseline main file tokens
- observed savings: post-adoption task/session cost vs baseline window task/session cost

If no post-adoption window exists yet, report only static savings and say observed savings are not available.

## Metrics Snapshots

Write a `metrics.jsonl` record for every analysis run. This lets users see version-over-version changes without rereading full reports.

Snapshot fields should include:

- `skill_id`
- `skill_version`
- `observation_window`
- `main_token_estimate`
- `section_count`
- `related_history_items`
- `related_sessions`
- `phenomena_counts`
- `command_count`
- `session_token_proxy_total`

Use snapshots to compare:

```text
v0.2.0 baseline snapshot
vs
v0.3.0 post-adoption snapshot
```

Interpretation rules:

- Lower `main_token_estimate` means static load cost improved.
- Lower `reported_total_tokens` means observed cost improved when logs expose usage.
- Lower `command_count` or `session_token_proxy_total` can indicate reduced task friction, but only compare similar observation windows and task mix.
- Higher `loaded_but_no_behavior` after adoption is a warning even if tokens dropped.
- Lower success-protecting behavior, such as missing required verification steps, is a rollback signal.

## Adapter Confidence

- Claude `projects/**/*.jsonl`: high confidence for actual tool behavior.
- Claude `history.jsonl`: demand signal only.
- Claude `transcripts/*.jsonl`: useful but may be incomplete.
- Codex `sessions/*.json`: medium to high confidence when tool calls are present.
- Codex Skill load inference: high only for direct target `SKILL.md` or skill-directory reads; otherwise heuristic.

## Section Evidence

Use `section-evidence.json` to identify which sections have command/API/identifier matches in related sessions.

Interpretation:

- `evidence_score >= 0.5`: likely behavior-driving section.
- `0 < evidence_score < 0.5`: weak or specialized section.
- `evidence_score == 0`: no deterministic evidence; do not delete without semantic review.

Section evidence is deterministic text matching. It does not prove causality.

## Script Candidates

Use `script-candidates.json` to find repeated normalized command patterns.

Strong candidates:

- frequency is high across sessions,
- commands are stable after replacing IDs/paths,
- inputs and outputs are clear,
- errors/retries often occur near the same command pattern.

Do not scriptify judgment-heavy or approval-sensitive steps.

## Observation Buckets

### Not Loaded

Signals:

- User tasks match the skill domain.
- No direct evidence that the target `SKILL.md`, references, or scripts were loaded.

Common causes:

- Description is too narrow or misses real user wording.
- Skill name or trigger language does not match demand.
- The skill has little actual demand.

Actions:

- Add concrete trigger phrases to the description.
- Clarify required inputs and task domain.
- Archive only when demand is also absent.

### Loaded But No Behavior

Signals:

- The skill was loaded.
- No relevant commands, tools, scripts, or response behavior followed.
- The session moved to unrelated work, repeated attempts, or another skill.

Common causes:

- Description is too broad.
- Skill overlaps another skill.
- Main instructions are too vague or too long.
- Workflow is not executable.

Actions:

- Add "do not use when" boundaries.
- Put the decision path near the top.
- Remove or move distracting low-frequency detail.
- Rewrite vague advice as concrete actions.

### Loaded And Used

Signals:

- The skill was loaded.
- Later behavior follows its rules, commands, scripts, or workflow.
- The task appears completed or progressed.

Actions:

- Preserve the behavior-driving content.
- Shorten redundant explanation.
- Move long examples, FAQ, and edge cases to references.
- Front-load the highest-value workflow.

### Script Candidate

Signals:

- Similar command or tool sequences recur across sessions.
- The steps are deterministic and have clear inputs/outputs.
- Agent repeatedly spends tokens deciding or reconstructing the same flow.

Actions:

- Create `scripts/*` for the repeatable flow.
- Keep `SKILL.md` instructions to when to run it, arguments, expected output, and fallback.
- Test scripts with representative inputs before recommending adoption.

## Token Reduction Moves

Use these in order:

1. Remove duplicate statements.
2. Move low-frequency detail to `references/`.
3. Replace long examples with one concise example plus a reference.
4. Convert stable repeated workflows into scripts.
5. Tighten trigger language to avoid wasted loads.
6. Reorder content so high-value instructions appear before background.
7. Delete only when evidence and risk both support deletion.

## Risk Labels

- `low`: duplicated text, unused examples, formatting cleanup, moving detail to references.
- `medium`: changing trigger conditions, moving troubleshooting, shortening workflows.
- `high`: deleting safety rules, approval boundaries, credential rules, destructive-operation guidance, or rare failure handling.

## Report Shape

```text
Skill: <name>
Version/window:
- baseline version and observation window
- candidate/adopted version and observation window, if available

Baseline: <main tokens>, <related sessions>, <token proxies>
Metrics snapshots:
- baseline snapshot path
- candidate/post-adoption snapshot path, if available
- static token delta
- observed proxy delta, if available

Observed phenomena:
- not_loaded: <count and evidence>
- loaded_but_no_behavior: <count and evidence>
- loaded_and_used: <count and evidence>
- script_candidate: <candidate flows>

Recommendations:
1. <action>
   Evidence: <specific session/section/tool evidence>
   Expected token impact: <per load or per task>
   Success risk: <low|medium|high>

Candidate version:
- Summary of structural changes.
- Any references/scripts to add.
- Rollback condition.
```
