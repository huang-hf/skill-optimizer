import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import skillopt


class SkillParsingTests(unittest.TestCase):
    def test_parse_skill_splits_frontmatter_and_markdown_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_path = Path(tmp) / "SKILL.md"
            skill_path.write_text(
                """---
name: sample-skill
description: Use when testing section parsing.
---

# Sample Skill

Intro text.

## Rules

- Do the important thing.

## Workflow

1. Run command.
2. Check output.
""",
                encoding="utf-8",
            )

            result = skillopt.parse_skill(skill_path)

        self.assertEqual(result["name"], "sample-skill")
        section_ids = [section["id"] for section in result["sections"]]
        self.assertEqual(section_ids, ["frontmatter", "sample-skill", "rules", "workflow"])
        self.assertGreater(result["token_estimate"], 0)
        self.assertGreater(result["sections"][2]["token_estimate"], 0)

    def test_parse_skill_ignores_hash_comments_inside_code_fences(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_path = Path(tmp) / "SKILL.md"
            skill_path.write_text(
                """---
name: code-fence-skill
description: Use when testing code fences.
---

## Commands

```bash
# This is a shell comment, not a markdown heading
echo ok
```

## Next Section

Done.
""",
                encoding="utf-8",
            )

            result = skillopt.parse_skill(skill_path)

        section_ids = [section["id"] for section in result["sections"]]
        self.assertEqual(section_ids, ["frontmatter", "commands", "next-section"])


class ClaudeLogAnalysisTests(unittest.TestCase):
    def test_collect_claude_evidence_detects_history_trigger_and_transcript_activity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "history.jsonl"
            transcripts = root / "transcripts"
            transcripts.mkdir()

            history.write_text(
                json.dumps(
                    {
                        "display": "watch pr",
                        "timestamp": 1776246744134,
                        "project": "/repo",
                        "sessionId": "session-1",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            transcript = transcripts / "session-1.jsonl"
            transcript.write_text(
                "\n".join(
                    [
                        json.dumps({"type": "user", "content": "watch pr"}),
                        json.dumps(
                            {
                                "type": "tool_result",
                                "tool_name": "read",
                                "tool_input": {
                                    "filePath": "/Users/me/.claude/skills/my-test-skill/SKILL.md"
                                },
                                "tool_output": {"output": "# AI Review Response"},
                            }
                        ),
                        json.dumps(
                            {
                                "type": "tool_result",
                                "tool_name": "bash",
                                "tool_input": {"command": "gh pr checks 123 --watch"},
                                "tool_output": {"output": "success"},
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = skillopt.collect_claude_evidence(
                skill_path=Path("/Users/me/.claude/skills/my-test-skill/SKILL.md"),
                logs_path=root,
                trigger_terms=["watch pr", "monitor PR"],
            )

        self.assertEqual(result["total_history_items"], 1)
        self.assertEqual(result["related_history_items"], 1)
        self.assertEqual(result["transcripts_scanned"], 1)
        self.assertEqual(len(result["sessions"]), 1)
        session = result["sessions"][0]
        self.assertTrue(session["skill_loaded"])
        self.assertIn("gh pr checks", session["commands"][0])
        self.assertEqual(session["phenomena"], ["loaded_and_used"])

    def test_collect_claude_evidence_does_not_count_other_skill_reads_as_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "history.jsonl").write_text("", encoding="utf-8")
            transcripts = root / "transcripts"
            transcripts.mkdir()
            (transcripts / "other.jsonl").write_text(
                json.dumps(
                    {
                        "type": "tool_result",
                        "tool_name": "read",
                        "tool_input": {"filePath": "/Users/me/.claude/skills/other-skill/SKILL.md"},
                        "tool_output": {"output": "# Coffer"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = skillopt.collect_claude_evidence(
                skill_path=Path("/Users/me/.claude/skills/my-test-skill/SKILL.md"),
                logs_path=root,
                trigger_terms=["watch pr"],
            )

        self.assertEqual(result["sessions"], [])

    def test_collect_claude_evidence_filters_by_observation_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "history.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "display": "watch pr",
                                "timestamp": "2026-07-10T00:00:00Z",
                                "sessionId": "old",
                            }
                        ),
                        json.dumps(
                            {
                                "display": "watch pr",
                                "timestamp": "2026-07-20T00:00:00Z",
                                "sessionId": "new",
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            transcripts = root / "transcripts"
            transcripts.mkdir()
            (transcripts / "old.jsonl").write_text(
                json.dumps(
                    {
                        "type": "user",
                        "timestamp": "2026-07-10T00:00:00Z",
                        "content": "watch pr",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (transcripts / "new.jsonl").write_text(
                json.dumps(
                    {
                        "type": "user",
                        "timestamp": "2026-07-20T00:00:00Z",
                        "content": "watch pr",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = skillopt.collect_claude_evidence(
                skill_path=Path("/Users/me/.claude/skills/my-test-skill/SKILL.md"),
                logs_path=root,
                trigger_terms=["watch pr"],
                since="2026-07-15T00:00:00Z",
            )

        self.assertEqual(result["observation_window"]["since"], "2026-07-15T00:00:00Z")
        self.assertEqual(result["total_history_items"], 1)
        self.assertEqual(result["related_history_items"], 1)
        self.assertEqual(result["transcripts_scanned"], 1)
        self.assertEqual(result["sessions"][0]["session_file"].split("/")[-1], "new.jsonl")


class MetricsSnapshotTests(unittest.TestCase):
    def test_build_metrics_snapshot_summarizes_structure_and_evidence(self):
        structure = {
            "path": "/skills/demo/SKILL.md",
            "name": "demo",
            "token_estimate": 1000,
            "sections": [{"id": "a"}, {"id": "b"}],
        }
        evidence = {
            "skill_name": "demo",
            "observation_window": {"since": "2026-07-01T00:00:00Z", "until": None},
            "total_history_items": 10,
            "related_history_items": 3,
            "transcripts_scanned": 4,
            "sessions": [
                {"phenomena": ["loaded_and_used"], "commands": ["gh pr checks"], "token_proxy": 100},
                {"phenomena": ["loaded_and_used"], "commands": ["gh pr view"], "token_proxy": 200},
                {"phenomena": ["related_but_not_loaded"], "commands": [], "token_proxy": 50},
            ],
        }

        snapshot = skillopt.build_metrics_snapshot(
            structure=structure,
            evidence=evidence,
            skill_version="0.2.0",
            run_id="run-1",
        )

        self.assertEqual(snapshot["skill_id"], "demo")
        self.assertEqual(snapshot["skill_version"], "0.2.0")
        self.assertEqual(snapshot["main_token_estimate"], 1000)
        self.assertEqual(snapshot["section_count"], 2)
        self.assertEqual(snapshot["related_sessions"], 3)
        self.assertEqual(snapshot["phenomena_counts"]["loaded_and_used"], 2)
        self.assertEqual(snapshot["command_count"], 2)
        self.assertEqual(snapshot["session_token_proxy_total"], 350)

    def test_compare_snapshots_reports_token_delta_and_session_delta(self):
        before = {
            "skill_id": "demo",
            "skill_version": "0.2.0",
            "main_token_estimate": 1000,
            "related_sessions": 10,
            "phenomena_counts": {"loaded_and_used": 8, "loaded_but_no_behavior": 2},
            "command_count": 30,
            "session_token_proxy_total": 5000,
        }
        after = {
            "skill_id": "demo",
            "skill_version": "0.3.0",
            "main_token_estimate": 700,
            "related_sessions": 10,
            "phenomena_counts": {"loaded_and_used": 9, "loaded_but_no_behavior": 1},
            "command_count": 20,
            "session_token_proxy_total": 3500,
        }

        comparison = skillopt.compare_snapshots(before, after)

        self.assertEqual(comparison["main_token_delta"], -300)
        self.assertEqual(comparison["main_token_reduction_pct"], 30.0)
        self.assertEqual(comparison["command_delta"], -10)
        self.assertEqual(comparison["session_token_proxy_delta"], -1500)
        self.assertEqual(comparison["phenomena_delta"]["loaded_and_used"], 1)


class InstallSupportTests(unittest.TestCase):
    def test_plan_install_targets_agent_skill_directories(self):
        source = Path("/draft/skill-optimizer")

        claude = skillopt.plan_install(source, agent="claude", home=Path("/home/me"))
        codex = skillopt.plan_install(source, agent="codex", home=Path("/home/me"))

        self.assertEqual(claude["target"], "/home/me/.claude/skills/skill-optimizer")
        self.assertEqual(codex["target"], "/home/me/.codex/skills/skill-optimizer")
        self.assertFalse(claude["requires_overwrite"])

    def test_plan_install_refuses_unknown_agent(self):
        with self.assertRaises(ValueError):
            skillopt.plan_install(Path("/draft/skill-optimizer"), agent="cursor", home=Path("/home/me"))


class AdapterAndUsageTests(unittest.TestCase):
    def test_claude_evidence_scans_project_logs_and_skill_base_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "history.jsonl").write_text("", encoding="utf-8")
            project = root / "projects" / "-repo"
            project.mkdir(parents=True)
            (project / "session.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "type": "assistant",
                                "timestamp": "2026-07-10T00:00:00Z",
                                "message": {
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": "Base directory for this skill: /Users/me/.claude/skills/my-test-skill",
                                        }
                                    ]
                                },
                            }
                        ),
                        json.dumps(
                            {
                                "type": "tool_use",
                                "name": "Bash",
                                "input": {"command": "gh pr checks 7 --watch"},
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = skillopt.collect_claude_evidence(
                Path("/Users/me/.claude/skills/my-test-skill/SKILL.md"),
                root,
                ["watch-pr"],
            )

        self.assertEqual(result["transcripts_scanned"], 1)
        self.assertEqual(len(result["sessions"]), 1)
        self.assertTrue(result["sessions"][0]["skill_loaded"])
        self.assertIn("gh pr checks", result["sessions"][0]["commands"][0])

    def test_codex_evidence_parses_session_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "history.jsonl").write_text(
                json.dumps({"text": "optimize skill", "timestamp": "2026-07-10T00:00:00Z"})
                + "\n",
                encoding="utf-8",
            )
            sessions = root / "sessions"
            sessions.mkdir()
            (sessions / "rollout.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {"role": "user", "content": "optimize skill"},
                            {
                                "type": "tool_call",
                                "name": "read",
                                "arguments": {
                                    "filePath": "/Users/me/.codex/skills/skill-optimizer/SKILL.md"
                                },
                            },
                            {
                                "type": "tool_call",
                                "name": "shell",
                                "arguments": {"cmd": "python3 scripts/skillopt.py parse-skill"},
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = skillopt.collect_codex_evidence(
                Path("/Users/me/.codex/skills/skill-optimizer/SKILL.md"),
                root,
                ["optimize skill"],
            )

        self.assertEqual(result["related_history_items"], 1)
        self.assertEqual(len(result["sessions"]), 1)
        self.assertTrue(result["sessions"][0]["skill_loaded"])
        self.assertIn("python3 scripts/skillopt.py", result["sessions"][0]["commands"][0])

    def test_sum_token_usage_extracts_known_shapes(self):
        rows = [
            {"usage": {"input_tokens": 100, "output_tokens": 20}},
            {"message": {"usage": {"input_tokens": 50, "output_tokens": 10}}},
            {"tokenUsage": {"input": 70, "output": 30}},
        ]

        usage = skillopt.sum_token_usage(rows)

        self.assertEqual(usage["input_tokens"], 220)
        self.assertEqual(usage["output_tokens"], 60)
        self.assertEqual(usage["total_tokens"], 280)
        self.assertEqual(usage["token_source"], "reported")


class EvidenceAnalysisTests(unittest.TestCase):
    def test_section_evidence_matches_commands_and_terms(self):
        structure = {
            "sections": [
                {
                    "id": "resolve-threads",
                    "title": "Resolve Threads",
                    "content": "Use gh api graphql resolveReviewThread before cycling ai-review.",
                    "token_estimate": 20,
                }
            ]
        }
        evidence = {
            "sessions": [
                {
                    "session_file": "a",
                    "commands": ["gh api graphql mutation resolveReviewThread"],
                    "tools": [],
                    "token_proxy": 10,
                },
                {
                    "session_file": "b",
                    "commands": ["gh pr edit 1 --add-label ai-review"],
                    "tools": [],
                    "token_proxy": 10,
                },
            ]
        }

        result = skillopt.build_section_evidence(structure, evidence)

        self.assertEqual(result["sections"][0]["section_id"], "resolve-threads")
        self.assertEqual(result["sections"][0]["matched_sessions"], 2)
        self.assertGreater(result["sections"][0]["evidence_score"], 0)

    def test_script_candidates_find_repeated_normalized_commands(self):
        evidence = {
            "sessions": [
                {"commands": ["gh pr checks 123 --json name,state", "gh pr view 123 --comments"]},
                {"commands": ["gh pr checks 456 --json name,state", "gh pr view 456 --comments"]},
                {"commands": ["gh pr checks 789 --json name,state", "gh pr view 789 --comments"]},
            ]
        }

        result = skillopt.find_script_candidates(evidence, min_frequency=3)

        self.assertTrue(result["candidates"])
        self.assertEqual(result["candidates"][0]["frequency"], 3)
        self.assertIn("<NUM>", result["candidates"][0]["pattern"])

    def test_analyze_command_generates_expected_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "skills" / "demo"
            skill_dir.mkdir(parents=True)
            skill_file = skill_dir / "SKILL.md"
            skill_file.write_text(
                """---
name: demo
description: Use when demo trigger.
---

## Workflow

Run `gh pr checks`.
""",
                encoding="utf-8",
            )
            logs = root / "logs"
            project = logs / "projects" / "-repo"
            project.mkdir(parents=True)
            (logs / "history.jsonl").write_text("", encoding="utf-8")
            (project / "session.jsonl").write_text(
                json.dumps(
                    {
                        "type": "tool_result",
                        "tool_name": "read",
                        "tool_input": {"filePath": str(skill_file)},
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "gh pr checks 1"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            out = root / "out"

            skillopt.run_analyze(
                agent="claude",
                skill_path=skill_file,
                logs_path=logs,
                out_dir=out,
                version="0.1.0",
                triggers=["demo trigger"],
                since=None,
                until=None,
                append_metrics=False,
            )

            for name in [
                "skill-structure.json",
                "evidence.json",
                "section-evidence.json",
                "script-candidates.json",
                "snapshot.json",
            ]:
                self.assertTrue((out / name).exists(), name)


if __name__ == "__main__":
    unittest.main()
