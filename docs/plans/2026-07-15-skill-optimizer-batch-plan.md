# Skill Optimizer Batch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Upgrade `skill-optimizer` from a prototype into a usable Claude/Codex Skill optimization tool with install support, deeper log adapters, token metrics, section evidence, and scriptification detection.

**Architecture:** Keep `SKILL.md` as the agent-facing workflow and keep deterministic work in `scripts/skillopt.py`. Add adapters and analyzers as tested functions first, then expose them as CLI subcommands. Store every run as JSON artifacts so reports and version comparisons are reproducible.

**Tech Stack:** Python standard library only, `unittest`, JSON/JSONL artifacts, shell commands for validation and installation.

---

## File Structure

- Modify: `scripts/skillopt.py`
  - Add log source discovery, Claude project adapter, Codex adapter, token usage extraction, section evidence scoring, repeated command detection, install/adoption helpers.
- Modify: `scripts/test_skillopt.py`
  - Add tests for every new analyzer and adapter before implementation.
- Modify: `SKILL.md`
  - Update workflow to use new commands and enforce run/snapshot/version discipline.
- Modify: `references/optimization-playbook.md`
  - Add interpretation rules for token usage, section evidence, script candidates, and adapter confidence.
- Create: `docs/plans/2026-07-15-skill-optimizer-batch-plan.md`
  - This implementation plan.
- Optional generated analysis artifacts:
  - `analysis/<skill-id>/evidence.json`
  - `analysis/<skill-id>/section-evidence.json`
  - `analysis/<skill-id>/script-candidates.json`
  - `analysis/<skill-id>/metrics.jsonl`

---

### Task 1: Install Support

**Files:**
- Modify: `scripts/skillopt.py`
- Test: `scripts/test_skillopt.py`
- Modify: `SKILL.md`

- [x] **Step 1: Write failing tests for install path planning**

Add tests for:

```python
def test_plan_install_targets_claude_skills_dir():
    plan = skillopt.plan_install(Path("/draft/skill-optimizer"), agent="claude", home=Path("/home/me"))
    assert plan["target"] == "/home/me/.claude/skills/skill-optimizer"
    assert plan["requires_overwrite"] is False

def test_plan_install_refuses_unknown_agent():
    with self.assertRaises(ValueError):
        skillopt.plan_install(Path("/draft/skill-optimizer"), agent="cursor", home=Path("/home/me"))
```

- [x] **Step 2: Run tests to verify failure**

Run:

```bash
cd ./skill-optimizer/scripts
python3 -m unittest test_skillopt.py
```

Expected: FAIL because `plan_install` does not exist.

- [x] **Step 3: Implement install planning**

Add:

```python
def plan_install(source: Path, agent: str, home: Path | None = None) -> dict[str, Any]:
    ...
```

Supported agents:

```text
claude -> ~/.claude/skills/skill-optimizer
codex -> ~/.codex/skills/skill-optimizer
```

Expose:

```bash
python3 scripts/skillopt.py install-plan --agent claude --source /path/to/skill-optimizer
```

Do not copy files in this command.

- [x] **Step 4: Add optional install command**

Add:

```bash
python3 scripts/skillopt.py install --agent claude --source /path/to/skill-optimizer
```

Behavior:

- copy only required skill files,
- ignore `analysis/`, `docs/`, `__pycache__`,
- fail if target exists unless `--overwrite` is passed,
- print target path.

- [x] **Step 5: Verify tests pass**

Run unit tests and `quick_validate.py`.

---

### Task 2: Claude Project Logs Adapter

**Files:**
- Modify: `scripts/skillopt.py`
- Test: `scripts/test_skillopt.py`
- Modify: `SKILL.md`

- [x] **Step 1: Write failing tests for `~/.claude/projects/**` discovery**

Create temp structure:

```text
logs/
  history.jsonl
  projects/
    -repo/
      session.jsonl
```

Test that project JSONL files are included when `--source claude` or `claude-evidence` runs.

- [x] **Step 2: Write failing tests for Claude project message shapes**

Cover these observed patterns:

```json
{"type":"user","message":{"content":"..."}}
{"type":"assistant","message":{"content":[{"type":"text","text":"..."}]}}
{"type":"tool_result","tool_name":"bash","tool_input":{"command":"gh pr checks 1"}}
{"type":"tool_use","name":"Bash","input":{"command":"gh pr checks 1"}}
```

Expected extraction:

- user text,
- assistant text,
- tool names,
- bash commands,
- read paths,
- token usage if present.

- [x] **Step 3: Implement source discovery**

Replace transcript-only discovery with:

```python
discover_log_files(logs_path, source="claude")
```

Claude sources:

- `history.jsonl`
- `transcripts/*.jsonl`
- `projects/**/*.jsonl`
- `sessions/**/*.jsonl` if present

- [x] **Step 4: Improve load markers**

Detect direct Claude skill load markers:

```text
Base directory for this skill:
/my-test-skill
my-test-skill/SKILL.md
/Users/.../.claude/skills/my-test-skill
```

- [x] **Step 5: Re-run `my-test-skill` evidence**

Run:

```bash
python3 scripts/skillopt.py claude-evidence \
  --skill ~/.claude/skills/my-test-skill/SKILL.md \
  --logs ~/.claude \
  --until 2026-07-15T00:00:00Z \
  --trigger watch-pr --trigger "watch pr"
```

Expected: related sessions should reflect project logs, not just transcripts.

---

### Task 3: Codex Adapter

**Files:**
- Modify: `scripts/skillopt.py`
- Test: `scripts/test_skillopt.py`
- Modify: `SKILL.md`
- Modify: `references/optimization-playbook.md`

- [x] **Step 1: Write failing tests for Codex JSON session parsing**

Use a temp `.codex` fixture with:

```text
history.jsonl
sessions/rollout-xxx.json
```

Test extraction of:

- user messages,
- tool calls,
- file reads,
- commands,
- skill load evidence from `SKILL.md` reads,
- timestamps.

- [x] **Step 2: Add `codex-evidence` command**

Expose:

```bash
python3 scripts/skillopt.py codex-evidence \
  --skill /path/to/SKILL.md \
  --logs ~/.codex \
  --trigger "optimize skill"
```

Output schema must match `claude-evidence` enough for `snapshot` to consume.

- [x] **Step 3: Add source-neutral command**

Add:

```bash
python3 scripts/skillopt.py evidence --agent claude|codex ...
```

Keep old commands as aliases.

- [x] **Step 4: Validate on local `.codex` sample**

Use read-only local logs. Do not read secrets or auth files.

---

### Task 4: Token Usage Extraction

**Files:**
- Modify: `scripts/skillopt.py`
- Test: `scripts/test_skillopt.py`
- Modify: `references/optimization-playbook.md`

- [x] **Step 1: Write failing tests for token usage extraction**

Fixtures:

```json
{"usage":{"input_tokens":100,"output_tokens":20}}
{"message":{"usage":{"input_tokens":50,"output_tokens":10}}}
{"tokenUsage":{"input":70,"output":30}}
```

Expected:

```json
{
  "input_tokens": 220,
  "output_tokens": 60,
  "total_tokens": 280,
  "token_source": "reported"
}
```

- [x] **Step 2: Implement recursive usage extraction**

Add:

```python
extract_token_usage(row)
sum_token_usage(rows)
```

Fallback remains `token_proxy`.

- [x] **Step 3: Extend session output and snapshots**

Add fields:

```json
"reported_input_tokens": 0,
"reported_output_tokens": 0,
"reported_total_tokens": 0,
"token_source": "reported|proxy"
```

Update `build_metrics_snapshot`.

- [x] **Step 4: Update comparison output**

Add:

```json
"reported_total_token_delta"
"reported_total_token_reduction_pct"
```

---

### Task 5: Section-Level Evidence

**Files:**
- Modify: `scripts/skillopt.py`
- Test: `scripts/test_skillopt.py`
- Modify: `SKILL.md`

- [x] **Step 1: Write failing tests for section keyword extraction**

Given a section with:

```text
gh pr checks
resolveReviewThread
ai-review
```

Expected extracted evidence terms include command phrases and unique identifiers.

- [x] **Step 2: Write failing tests for section matching**

Given parsed sections and sessions, expect:

```json
{
  "section_id": "step-4-resolve-all-previous-review-threads",
  "matched_sessions": 2,
  "matched_commands": ["gh api graphql ... resolveReviewThread ..."],
  "evidence_score": 0.8
}
```

- [x] **Step 3: Implement `section-evidence` command**

Expose:

```bash
python3 scripts/skillopt.py section-evidence \
  --structure skill-structure.json \
  --evidence evidence.json
```

Scoring should be simple and transparent:

- exact command/API phrase match,
- unique term match,
- section title phrase match,
- no LLM dependency.

- [x] **Step 4: Add snapshot summary fields**

Add:

```json
"high_evidence_sections": 0,
"low_evidence_sections": 0,
"zero_evidence_sections": 0
```

Only when section evidence file is provided.

---

### Task 6: Scriptification Detection

**Files:**
- Modify: `scripts/skillopt.py`
- Test: `scripts/test_skillopt.py`
- Modify: `references/optimization-playbook.md`

- [x] **Step 1: Write failing tests for repeated command normalization**

Normalize:

```text
gh pr checks 123 --json name,state
gh pr checks 456 --json name,state
```

into the same pattern:

```text
gh pr checks <NUM> --json name,state
```

- [x] **Step 2: Write failing tests for repeated sequence candidates**

Given commands:

```text
gh pr checks 1
gh pr view 1 --comments
gh api graphql ...
```

appearing across 3 sessions, expect one script candidate with frequency 3.

- [x] **Step 3: Implement `script-candidates` command**

Expose:

```bash
python3 scripts/skillopt.py script-candidates --evidence evidence.json --min-frequency 3
```

Output:

```json
{
  "candidates": [
    {
      "pattern": "...",
      "frequency": 3,
      "example_commands": [],
      "suggested_script_name": "pr_review_state.sh",
      "expected_benefit": "reduce repeated command planning"
    }
  ]
}
```

- [x] **Step 4: Update report guidance**

Require recommendations to reference script candidates when present.

---

### Task 7: Batch Analysis Command

**Files:**
- Modify: `scripts/skillopt.py`
- Test: `scripts/test_skillopt.py`
- Modify: `SKILL.md`

- [x] **Step 1: Write failing integration-style test for `analyze`**

Using temp skill/log fixtures, run:

```bash
python3 skillopt.py analyze \
  --agent claude \
  --skill /tmp/skill/SKILL.md \
  --logs /tmp/logs \
  --out /tmp/analysis \
  --version 0.2.0 \
  --trigger "watch pr"
```

Expected files:

```text
skill-structure.json
evidence.json
section-evidence.json
script-candidates.json
snapshot.json
metrics.jsonl
```

- [x] **Step 2: Implement command orchestration**

Call internal functions directly, not subprocesses.

- [x] **Step 3: Ensure idempotency**

If run twice, overwrite deterministic JSON outputs but append `metrics.jsonl` only when `--append-metrics` is explicitly passed.

---

### Task 8: Update Skill Documentation

**Files:**
- Modify: `SKILL.md`
- Modify: `references/optimization-playbook.md`

- [x] **Step 1: Update main workflow**

Document preferred command:

```bash
python3 scripts/skillopt.py analyze --agent claude ...
```

Keep lower-level commands as debugging tools.

- [x] **Step 2: Add adapter confidence rules**

Document:

- Claude project logs are highest confidence for behavior.
- `history.jsonl` is demand signal.
- transcript-only evidence is partial.
- Codex skill loads may be heuristic.

- [x] **Step 3: Add rollback/adoption flow**

Document:

- install candidate,
- set `adopted_at`,
- wait for new sessions,
- run post-adoption snapshot,
- compare snapshots,
- rollback if success-protecting behavior regresses.

---

### Task 9: Final Verification

**Files:**
- All modified files

- [x] **Step 1: Run unit tests**

```bash
cd ./skill-optimizer/scripts
python3 -m unittest test_skillopt.py
```

Expected: OK.

- [x] **Step 2: Validate Skill**

```bash
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py ./skill-optimizer
```

Expected: `Skill is valid!`

- [x] **Step 3: Run real sample analysis**

```bash
python3 ./skill-optimizer/scripts/skillopt.py analyze \
  --agent claude \
  --skill ~/.claude/skills/my-test-skill/SKILL.md \
  --logs ~/.claude \
  --out ./skill-optimizer/analysis/my-test-skill \
  --version 0.2.0 \
  --until 2026-07-15T00:00:00Z \
  --trigger watch-pr \
  --trigger "watch pr"
```

Expected: JSON artifacts generated and metrics snapshot usable.

- [x] **Step 4: Clean generated caches**

Remove `scripts/__pycache__` if created.

