---
name: skill-optimizer
description: Use when optimizing one existing agent Skill based on historical session logs, especially to reduce token cost per successful skill-related task, analyze whether the Skill was loaded, used, mis-triggered, or contains repeatable flows that should become scripts.
---

# Skill Optimizer

Optimize one target Skill at a time. The goal is lower token cost per successful skill-related task, with no evidence of reduced task success.

## Workflow

1. **Confirm scope**
   Identify the target `SKILL.md`, current version, session log directory, agent source, and observation period. If a previous optimization run exists, default to the post-adoption window for the current version; otherwise use a baseline window and state it.

   Look for an optimization run log near the target Skill or in the current output directory:

   ```text
   .optimization-runs.jsonl
   ```

2. **Collect deterministic evidence**
   Run the batch analyzer before making semantic judgments:

   ```bash
   python3 scripts/skillopt.py analyze \
     --agent claude \
     --skill /path/to/SKILL.md \
     --logs ~/.claude \
     --out analysis/<skill-id> \
     --version 0.2.0 \
     --since 2026-07-16T00:00:00Z \
     --trigger "watch pr"
   ```

   Use `--agent codex` for Codex logs. Add multiple `--trigger` values for known user phrases. Use `--since` and `--until` to prevent mixing sessions from different Skill versions.

3. **Establish token baseline**
   Report the target Skill token estimate, main-file sections, related sessions found, and any session token proxies available. If real token usage is absent, say that token cost is estimated from text length and interaction volume.

   The analyzer writes `snapshot.json`. Append to `metrics.jsonl` only when intentionally recording a run with `--append-metrics`.

4. **Classify observed phenomena**
   Use the evidence to classify the target Skill into these buckets:
   - `not_loaded`: matching demand exists but the Skill was not observed loading.
   - `loaded_but_no_behavior`: loaded but no meaningful follow-through was observed.
   - `loaded_and_used`: loaded and followed by relevant tools, commands, scripts, or responses.
   - `script_candidate`: repeated stable steps or command sequences can become scripts.

5. **Apply optimization playbook**
   Read `references/optimization-playbook.md` before proposing edits. Tie every recommendation to token reduction and success-risk impact.

6. **Produce outputs**
   Generate:
   - `optimization-report.md`: findings, evidence, estimated token savings, risks, and recommended actions.
   - `SKILL.candidate.md`: a candidate replacement or patch plan. Do not overwrite the original Skill unless the user explicitly asks.
   - optional `scripts/*`: only for stable, repeated, deterministic flows.
   - `.optimization-runs.jsonl` entry: the baseline version, candidate version, observation window, report path, and adoption status.
   - `metrics.jsonl` entry: machine-readable snapshot for comparing versions over time.

7. **Compare versions when snapshots exist**
   Compare baseline and post-adoption snapshots:

   ```bash
   python3 scripts/skillopt.py compare --before baseline-snapshot.json --after candidate-snapshot.json
   ```

   Explain static token delta separately from observed session/task proxy deltas.

## Judgment Rules

- Do not optimize for shorter text alone. Preserve rules that protect task success, irreversible operations, credentials, or user approval boundaries.
- Treat missing evidence carefully: "not observed" is not the same as "useless".
- Never mix pre-optimization and post-optimization sessions in one performance metric. Compare version windows instead.
- Prefer moving low-frequency detail to `references/` over deleting it when the risk is unclear.
- Prefer scripts for deterministic repeated work: parsing logs, checking structured state, validating output, generating reports, or calling fixed command sequences.
- Report confidence levels plainly: high for direct file/script evidence, medium for explicit text references, low for semantic similarity only.

## Helper Scripts

- `scripts/skillopt.py analyze`: preferred entry point; generates structure, evidence, section evidence, script candidates, and snapshot JSON.
- `scripts/skillopt.py parse-skill`: split a Skill into markdown sections and estimate token cost.
- `scripts/skillopt.py evidence`: scan Claude or Codex logs for trigger phrases, skill loading evidence, commands, file reads, token usage, and optional `--since/--until` observation windows.
- `scripts/skillopt.py section-evidence`: match Skill sections against observed commands and identifiers.
- `scripts/skillopt.py script-candidates`: find repeated command patterns that may be scriptified.
- `scripts/skillopt.py snapshot`: convert skill structure and evidence into a versioned metrics record.
- `scripts/skillopt.py compare`: compare two metrics snapshots.
- `scripts/skillopt.py install-plan`: show where the Skill would install for Claude or Codex.

## Adapter Confidence

- Claude `projects/**/*.jsonl` logs are the highest-confidence behavior source.
- Claude `history.jsonl` is demand signal, not proof of Skill loading.
- Transcript-only evidence can be partial.
- Codex Skill loading is often heuristic unless a direct `SKILL.md` read appears.
- Report real token usage when logs contain it; otherwise label costs as token proxies.

## Optimization Run Record

Use one JSON object per run:

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

After adoption, set `adopted_at`. The next analysis should default to `--since <adopted_at>` for the adopted version.
