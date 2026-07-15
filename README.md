# skill-optimizer

Optimize agent Skills using historical session logs, token metrics, and versioned evidence.

`skill-optimizer` is an agent-native Skill plus helper scripts. It analyzes one target Skill at a time, using local Claude or Codex logs to identify whether the Skill was loaded, whether it drove useful behavior, which sections have evidence, and which repeated command flows could become scripts.

## Goals

- Reduce token cost per successful skill-related task.
- Keep task success signals from regressing.
- Record versioned metrics so users can compare Skill versions over time.
- Keep semantic judgment in the agent, while scripts collect deterministic evidence.

## Contents

```text
SKILL.md                         Agent-facing workflow
scripts/skillopt.py              Evidence collection and analysis CLI
scripts/test_skillopt.py         Unit tests
references/optimization-playbook.md
agents/openai.yaml               Skill UI metadata
docs/plans/                      Development plans
```

Generated `analysis/` outputs are ignored by git because they can contain session-derived data.

## Quick Start

Analyze a Claude Skill:

```bash
python3 scripts/skillopt.py analyze \
  --agent claude \
  --skill /path/to/skills/my-skill/SKILL.md \
  --logs ~/.claude \
  --out analysis/my-skill \
  --version 0.1.0 \
  --trigger "user phrase"
```

Analyze a Codex Skill:

```bash
python3 scripts/skillopt.py analyze \
  --agent codex \
  --skill /path/to/skills/my-skill/SKILL.md \
  --logs ~/.codex \
  --out analysis/my-skill \
  --version 0.1.0 \
  --trigger "user phrase"
```

The analyzer writes:

```text
skill-structure.json
evidence.json
section-evidence.json
script-candidates.json
snapshot.json
```

Append metrics for a run:

```bash
python3 scripts/skillopt.py analyze \
  --agent claude \
  --skill /path/to/SKILL.md \
  --logs ~/.claude \
  --out analysis/my-skill \
  --version 0.1.0 \
  --trigger "user phrase" \
  --append-metrics
```

Compare two snapshots:

```bash
python3 scripts/skillopt.py compare \
  --before analysis/my-skill/baseline-snapshot.json \
  --after analysis/my-skill/postadopt-snapshot.json
```

## Install Planning

Show where the Skill would be installed:

```bash
python3 scripts/skillopt.py install-plan --agent claude --source .
python3 scripts/skillopt.py install-plan --agent codex --source .
```

Install locally:

```bash
python3 scripts/skillopt.py install --agent claude --source .
python3 scripts/skillopt.py install --agent codex --source .
```

Use `--overwrite` only when replacing an existing local install.

## Tests

```bash
cd scripts
python3 -m unittest test_skillopt.py
```

Validate the Skill structure with Codex's skill validator when available:

```bash
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
```

## Version Windows

Do not mix logs from different Skill versions. Use `--since` and `--until` to define baseline and post-adoption windows:

```bash
python3 scripts/skillopt.py analyze \
  --agent claude \
  --skill /path/to/SKILL.md \
  --logs ~/.claude \
  --out analysis/my-skill \
  --version 0.2.0 \
  --since 2026-07-16T00:00:00Z
```

## Current Status

Prototype/MVP. Supported log adapters:

- Claude: `history.jsonl`, `transcripts/*.jsonl`, `projects/**/*.jsonl`, `sessions/**/*.jsonl`
- Codex: `history.jsonl`, `sessions/*.json`, `sessions/*.jsonl`

No third-party Python dependencies are required.
