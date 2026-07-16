# skill-optimizer

Evidence-based Skill optimization for coding agents.

`skill-optimizer` helps improve agent Skills using real usage logs. It looks at how a Skill is actually triggered and used, then helps produce an optimization report and a candidate Skill version.

## Why

Agent Skills tend to grow over time:

- old rules stay around after they stop mattering
- examples and FAQ sections become duplicated
- trigger descriptions get too broad
- low-frequency details stay in the always-loaded context
- repeated workflows remain as instructions instead of scripts

Blindly shortening a Skill is risky. A smaller Skill can make tasks fail.

## What It Does

Given a target Skill and historical Claude or Codex logs, `skill-optimizer` helps identify:

- whether the Skill is loaded for matching tasks
- whether loaded sessions show useful behavior
- which sections have deterministic evidence
- which content may be moved, rewritten, or removed
- which repeated workflows may become scripts
- how Skill metrics change across versions

## Not Prompt Compression

This is not a prompt compression tool.

`skill-optimizer` separates:

1. static Skill size reduction
2. loaded-context reduction
3. observed task-level impact after adoption

The goal is:

```text
lower token cost per successful skill-related task
```

while avoiding regressions in task success.

## Quick Start

### 1. Install

Send this to your agent:

```text
Install https://github.com/huang-hf/skill-optimizer as an agent Skill.
```

### 2. Optimize

Send this to your agent:

```text
Optimize my <skill-name> skill with skill-optimizer. Create a report and a candidate version.
```

Example:

```text
Optimize my netmind-power-model skill with skill-optimizer. Create a report and a candidate version.
```

## Supported Agents

- Claude Code
- Codex

## Status

Prototype / MVP.

No third-party Python dependencies are required.
