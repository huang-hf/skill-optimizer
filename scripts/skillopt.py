#!/usr/bin/env python3
"""Deterministic evidence collectors for skill optimization."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from collections import Counter


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
WORD_RE = re.compile(r"\S+")


def estimate_tokens(text: str) -> int:
    """Estimate tokens without external tokenizer dependencies."""
    if not text:
        return 0
    word_count = len(WORD_RE.findall(text))
    char_estimate = max(1, len(text) // 4)
    return max(word_count, char_estimate)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "section"


def parse_frontmatter(text: str) -> tuple[dict[str, str], str, str]:
    if not text.startswith("---\n"):
        return {}, "", text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, "", text
    raw = text[4:end].strip()
    body = text[text.find("\n", end + 1) + 1 :]
    data: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"')
    return data, raw, body


def parse_skill(skill_path: Path) -> dict[str, Any]:
    text = skill_path.read_text(encoding="utf-8")
    frontmatter, raw_frontmatter, body = parse_frontmatter(text)
    sections: list[dict[str, Any]] = []
    if raw_frontmatter:
        sections.append(
            {
                "id": "frontmatter",
                "title": "frontmatter",
                "level": 0,
                "content": raw_frontmatter,
                "token_estimate": estimate_tokens(raw_frontmatter),
            }
        )

    current: dict[str, Any] | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current, current_lines
        if current is None:
            content = "\n".join(current_lines).strip()
            if content:
                sections.append(
                    {
                        "id": "intro",
                        "title": "intro",
                        "level": 0,
                        "content": content,
                        "token_estimate": estimate_tokens(content),
                    }
                )
            current_lines = []
            return
        content = "\n".join(current_lines).strip()
        current["content"] = content
        current["token_estimate"] = estimate_tokens(current["title"] + "\n" + content)
        sections.append(current)
        current = None
        current_lines = []

    in_fence = False
    for line in body.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            current_lines.append(line)
            continue
        match = None if in_fence else HEADING_RE.match(line)
        if match:
            flush()
            title = match.group(2).strip()
            current = {
                "id": slugify(title),
                "title": title,
                "level": len(match.group(1)),
            }
            current_lines = []
        else:
            current_lines.append(line)
    flush()

    return {
        "path": str(skill_path),
        "name": frontmatter.get("name", skill_path.parent.name),
        "description": frontmatter.get("description", ""),
        "token_estimate": estimate_tokens(text),
        "sections": sections,
    }


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def text_contains_any(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms if term)


def extract_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(extract_text(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(extract_text(v) for v in value)
    return ""


def first_present(mapping: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp = timestamp / 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.isdigit():
            return parse_timestamp(int(raw))
        normalized = raw.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def in_observation_window(row: dict[str, Any], since: str | None, until: str | None) -> bool:
    if not since and not until:
        return True
    row_time = parse_timestamp(row.get("timestamp"))
    if row_time is None:
        return True
    since_time = parse_timestamp(since)
    until_time = parse_timestamp(until)
    if since_time and row_time < since_time:
        return False
    if until_time and row_time >= until_time:
        return False
    return True


def filter_rows_by_window(
    rows: list[dict[str, Any]], since: str | None, until: str | None
) -> list[dict[str, Any]]:
    return [row for row in rows if in_observation_window(row, since, until)]


def discover_log_files(logs_path: Path, source: str = "claude") -> list[Path]:
    if source == "claude":
        structured_dirs = [logs_path / "transcripts", logs_path / "sessions"]
        files: list[Path] = []
        for candidate in structured_dirs:
            if candidate.is_dir():
                files.extend(candidate.glob("*.jsonl"))
        projects = logs_path / "projects"
        if projects.is_dir():
            files.extend(projects.glob("**/*.jsonl"))
        if not files and logs_path.is_dir():
            files.extend(path for path in logs_path.glob("*.jsonl") if path.name != "history.jsonl")
        return sorted(set(files))
    if source == "codex":
        files = []
        sessions = logs_path / "sessions"
        if sessions.is_dir():
            files.extend(sessions.glob("*.json"))
            files.extend(sessions.glob("*.jsonl"))
        return sorted(set(files))
    raise ValueError(f"unsupported log source: {source}")


def transcript_files(logs_path: Path) -> list[Path]:
    return discover_log_files(logs_path, "claude")


def flatten_json_events(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        events: list[dict[str, Any]] = [value]
        for key in ("items", "messages", "events", "entries", "turns"):
            child = value.get(key)
            if isinstance(child, list):
                for item in child:
                    events.extend(flatten_json_events(item))
        return events
    if isinstance(value, list):
        events = []
        for item in value:
            events.extend(flatten_json_events(item))
        return events
    return []


def iter_json_events(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".jsonl":
        return iter_jsonl(path)
    try:
        return flatten_json_events(json.loads(path.read_text(encoding="utf-8", errors="replace")))
    except json.JSONDecodeError:
        return []


def event_tool_name(row: dict[str, Any]) -> str:
    return str(first_present(row, ["tool_name", "name", "tool", "toolName"]) or "")


def event_tool_input(row: dict[str, Any]) -> dict[str, Any]:
    value = first_present(row, ["tool_input", "input", "arguments", "args"])
    return value if isinstance(value, dict) else {}


def extract_event_activity(row: dict[str, Any]) -> tuple[str, str, str]:
    tool_name = event_tool_name(row)
    tool_input = event_tool_input(row)
    command = str(first_present(tool_input, ["command", "cmd", "shell_command"]) or "")
    read_path = str(first_present(tool_input, ["filePath", "path", "ref_id"]) or "")
    return tool_name, command, read_path


def skill_markers_for(skill_path: Path) -> list[str]:
    skill_dir = skill_path.parent
    skill_name = skill_dir.name
    return [
        str(skill_path),
        str(skill_dir),
        f"/{skill_name}/SKILL.md",
        f"{skill_name}/SKILL.md",
        f"Base directory for this skill: {skill_dir}",
    ]
    files: list[Path] = []
    for candidate in structured_dirs:
        if candidate.is_dir():
            files.extend(candidate.glob("*.jsonl"))
    if not files and logs_path.is_dir():
        files.extend(path for path in logs_path.glob("*.jsonl") if path.name != "history.jsonl")
    return sorted(set(files))


def classify_session(skill_loaded: bool, commands: list[str], related_text: bool) -> list[str]:
    if not skill_loaded and not related_text:
        return ["not_loaded"]
    if skill_loaded and commands:
        return ["loaded_and_used"]
    if skill_loaded:
        return ["loaded_but_no_behavior"]
    return ["related_but_not_loaded"]


def extract_token_usage(row: Any) -> dict[str, int]:
    total = {"input_tokens": 0, "output_tokens": 0}

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            usage = value.get("usage")
            if isinstance(usage, dict):
                total["input_tokens"] += int(
                    usage.get("input_tokens") or usage.get("prompt_tokens") or usage.get("input") or 0
                )
                total["output_tokens"] += int(
                    usage.get("output_tokens")
                    or usage.get("completion_tokens")
                    or usage.get("output")
                    or 0
                )
            token_usage = value.get("tokenUsage")
            if isinstance(token_usage, dict):
                total["input_tokens"] += int(
                    token_usage.get("input_tokens") or token_usage.get("input") or 0
                )
                total["output_tokens"] += int(
                    token_usage.get("output_tokens") or token_usage.get("output") or 0
                )
            for child in value.values():
                if child is usage or child is token_usage:
                    continue
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(row)
    return total


def sum_token_usage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    input_tokens = 0
    output_tokens = 0
    for row in rows:
        usage = extract_token_usage(row)
        input_tokens += usage["input_tokens"]
        output_tokens += usage["output_tokens"]
    total_tokens = input_tokens + output_tokens
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "token_source": "reported" if total_tokens else "proxy",
    }


def collect_claude_evidence(
    skill_path: Path,
    logs_path: Path,
    trigger_terms: list[str] | None = None,
    since: str | None = None,
    until: str | None = None,
) -> dict[str, Any]:
    trigger_terms = trigger_terms or []
    skill_name = skill_path.parent.name
    skill_markers = skill_markers_for(skill_path)
    history_rows = filter_rows_by_window(iter_jsonl(logs_path / "history.jsonl"), since, until)
    related_history = [
        row
        for row in history_rows
        if text_contains_any(extract_text(row.get("display", "")), trigger_terms)
        or text_contains_any(extract_text(row), [skill_name])
    ]

    sessions: list[dict[str, Any]] = []
    files = discover_log_files(logs_path, "claude")
    transcripts_scanned = 0
    for file_path in files:
        rows = filter_rows_by_window(iter_json_events(file_path), since, until)
        if not rows:
            continue
        transcripts_scanned += 1
        all_text = "\n".join(extract_text(row) for row in rows)
        skill_loaded = text_contains_any(all_text, skill_markers)
        related_text = text_contains_any(all_text, trigger_terms + [skill_name])
        commands: list[str] = []
        file_reads: list[str] = []
        tools: list[str] = []
        for row in rows:
            tool_name, command, read_path = extract_event_activity(row)
            if tool_name:
                tools.append(str(tool_name))
            if read_path:
                file_reads.append(read_path)
            if command:
                commands.append(command)
        usage = sum_token_usage(rows)
        if skill_loaded or related_text:
            sessions.append(
                {
                    "session_file": str(file_path),
                    "skill_loaded": skill_loaded,
                    "related_text": related_text,
                    "tools": tools,
                    "commands": commands,
                    "file_reads": file_reads,
                    "line_count": len(rows),
                    "token_proxy": estimate_tokens(all_text),
                    "reported_input_tokens": usage["input_tokens"],
                    "reported_output_tokens": usage["output_tokens"],
                    "reported_total_tokens": usage["total_tokens"],
                    "token_source": usage["token_source"],
                    "phenomena": classify_session(skill_loaded, commands, related_text),
                }
            )

    return {
        "skill_path": str(skill_path),
        "skill_name": skill_name,
        "logs_path": str(logs_path),
        "observation_window": {"since": since, "until": until},
        "total_history_items": len(history_rows),
        "related_history_items": len(related_history),
        "transcripts_scanned": transcripts_scanned,
        "sessions": sessions,
    }


def collect_codex_evidence(
    skill_path: Path,
    logs_path: Path,
    trigger_terms: list[str] | None = None,
    since: str | None = None,
    until: str | None = None,
) -> dict[str, Any]:
    trigger_terms = trigger_terms or []
    skill_name = skill_path.parent.name
    skill_markers = skill_markers_for(skill_path)
    history_rows = filter_rows_by_window(iter_jsonl(logs_path / "history.jsonl"), since, until)
    related_history = [
        row
        for row in history_rows
        if text_contains_any(extract_text(row), trigger_terms) or text_contains_any(extract_text(row), [skill_name])
    ]
    sessions: list[dict[str, Any]] = []
    files = discover_log_files(logs_path, "codex")
    scanned = 0
    for file_path in files:
        rows = filter_rows_by_window(iter_json_events(file_path), since, until)
        if not rows:
            continue
        scanned += 1
        all_text = "\n".join(extract_text(row) for row in rows)
        skill_loaded = text_contains_any(all_text, skill_markers)
        related_text = text_contains_any(all_text, trigger_terms + [skill_name])
        commands: list[str] = []
        file_reads: list[str] = []
        tools: list[str] = []
        for row in rows:
            tool_name, command, read_path = extract_event_activity(row)
            if tool_name:
                tools.append(tool_name)
            if command:
                commands.append(command)
            if read_path:
                file_reads.append(read_path)
        usage = sum_token_usage(rows)
        if skill_loaded or related_text:
            sessions.append(
                {
                    "session_file": str(file_path),
                    "skill_loaded": skill_loaded,
                    "related_text": related_text,
                    "tools": tools,
                    "commands": commands,
                    "file_reads": file_reads,
                    "line_count": len(rows),
                    "token_proxy": estimate_tokens(all_text),
                    "reported_input_tokens": usage["input_tokens"],
                    "reported_output_tokens": usage["output_tokens"],
                    "reported_total_tokens": usage["total_tokens"],
                    "token_source": usage["token_source"],
                    "phenomena": classify_session(skill_loaded, commands, related_text),
                }
            )
    return {
        "skill_path": str(skill_path),
        "skill_name": skill_name,
        "logs_path": str(logs_path),
        "observation_window": {"since": since, "until": until},
        "total_history_items": len(history_rows),
        "related_history_items": len(related_history),
        "transcripts_scanned": scanned,
        "sessions": sessions,
    }


def collect_evidence(
    agent: str,
    skill_path: Path,
    logs_path: Path,
    trigger_terms: list[str] | None = None,
    since: str | None = None,
    until: str | None = None,
) -> dict[str, Any]:
    if agent == "claude":
        return collect_claude_evidence(skill_path, logs_path, trigger_terms, since, until)
    if agent == "codex":
        return collect_codex_evidence(skill_path, logs_path, trigger_terms, since, until)
    raise ValueError(f"unsupported agent: {agent}")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def plan_install(source: Path, agent: str, home: Path | None = None) -> dict[str, Any]:
    home = home or Path.home()
    if agent == "claude":
        target = home / ".claude" / "skills" / source.name
    elif agent == "codex":
        target = home / ".codex" / "skills" / source.name
    else:
        raise ValueError(f"unsupported agent: {agent}")
    return {
        "source": str(source),
        "agent": agent,
        "target": str(target),
        "requires_overwrite": target.exists(),
    }


def install_skill(source: Path, agent: str, overwrite: bool = False, home: Path | None = None) -> dict[str, Any]:
    plan = plan_install(source, agent, home)
    target = Path(plan["target"])
    if target.exists():
        if not overwrite:
            raise FileExistsError(f"target exists: {target}")
        shutil.rmtree(target)
    ignore = shutil.ignore_patterns("analysis", "docs", "__pycache__", "*.pyc")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, ignore=ignore)
    plan["installed"] = True
    return plan


def section_terms(section: dict[str, Any]) -> list[str]:
    text = f"{section.get('title', '')}\n{section.get('content', '')}"
    terms = set()
    for match in re.findall(r"`([^`]{3,})`", text):
        terms.add(match.strip())
    for match in re.findall(r"\b(?:gh|git|python3?|npm|pnpm|jq)\s+[^\n`]+", text):
        terms.add(match.strip())
    for match in re.findall(r"\b[A-Za-z][A-Za-z0-9]*(?:[A-Z][A-Za-z0-9]*)+\b", text):
        terms.add(match.strip())
    for match in re.findall(r"\b[a-z0-9]+(?:-[a-z0-9]+)+\b", text.lower()):
        terms.add(match.strip())
    return sorted(term for term in terms if len(term) >= 4)


def build_section_evidence(structure: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    sessions = evidence.get("sessions", [])
    output = []
    for section in structure.get("sections", []):
        terms = section_terms(section)
        matched_sessions = 0
        matched_commands: list[str] = []
        for session in sessions:
            haystack = "\n".join(
                session.get("commands", []) + session.get("tools", []) + session.get("file_reads", [])
            )
            if not haystack:
                continue
            if any(term.lower() in haystack.lower() for term in terms):
                matched_sessions += 1
                matched_commands.extend(
                    command
                    for command in session.get("commands", [])
                    if any(term.lower() in command.lower() for term in terms)
                )
        evidence_score = 0.0
        if sessions:
            evidence_score = round(min(1.0, matched_sessions / max(1, len(sessions))), 3)
        output.append(
            {
                "section_id": section.get("id"),
                "title": section.get("title"),
                "token_estimate": section.get("token_estimate", 0),
                "terms": terms[:20],
                "matched_sessions": matched_sessions,
                "matched_commands": matched_commands[:20],
                "evidence_score": evidence_score,
            }
        )
    return {"sections": output}


def normalize_command(command: str) -> str:
    normalized = re.sub(r"\b\d+\b", "<NUM>", command.strip())
    normalized = re.sub(r"/Users/[^\s]+", "<PATH>", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def suggest_script_name(pattern: str) -> str:
    if "gh pr" in pattern:
        return "pr_review_state.sh"
    if "json" in pattern or "jq" in pattern:
        return "analyze_json.sh"
    return "repeatable_flow.sh"


def find_script_candidates(evidence: dict[str, Any], min_frequency: int = 3) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    examples: dict[str, list[str]] = {}
    for session in evidence.get("sessions", []):
        seen_in_session = set()
        for command in session.get("commands", []):
            pattern = normalize_command(command)
            if not pattern:
                continue
            seen_in_session.add(pattern)
            examples.setdefault(pattern, [])
            if len(examples[pattern]) < 3:
                examples[pattern].append(command)
        counts.update(seen_in_session)
    candidates = []
    for pattern, frequency in counts.most_common():
        if frequency < min_frequency:
            continue
        candidates.append(
            {
                "pattern": pattern,
                "frequency": frequency,
                "example_commands": examples.get(pattern, []),
                "suggested_script_name": suggest_script_name(pattern),
                "expected_benefit": "reduce repeated command planning and tool-call retries",
            }
        )
    return {"candidates": candidates}


def build_metrics_snapshot(
    structure: dict[str, Any],
    evidence: dict[str, Any],
    skill_version: str | None = None,
    run_id: str | None = None,
    section_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sessions = evidence.get("sessions", [])
    phenomena = Counter()
    command_count = 0
    token_proxy_total = 0
    reported_total = 0
    reported_input = 0
    reported_output = 0
    for session in sessions:
        phenomena.update(session.get("phenomena", []))
        command_count += len(session.get("commands", []))
        token_proxy_total += int(session.get("token_proxy") or 0)
        reported_total += int(session.get("reported_total_tokens") or 0)
        reported_input += int(session.get("reported_input_tokens") or 0)
        reported_output += int(session.get("reported_output_tokens") or 0)

    section_summary: dict[str, int] = {}
    if section_evidence:
        scores = [float(section.get("evidence_score") or 0) for section in section_evidence.get("sections", [])]
        section_summary = {
            "high_evidence_sections": sum(1 for score in scores if score >= 0.5),
            "low_evidence_sections": sum(1 for score in scores if 0 < score < 0.5),
            "zero_evidence_sections": sum(1 for score in scores if score == 0),
        }

    payload = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "skill_id": evidence.get("skill_name") or structure.get("name"),
        "skill_version": skill_version,
        "skill_path": structure.get("path") or evidence.get("skill_path"),
        "observation_window": evidence.get("observation_window", {}),
        "main_token_estimate": structure.get("token_estimate", 0),
        "section_count": len(structure.get("sections", [])),
        "total_history_items": evidence.get("total_history_items", 0),
        "related_history_items": evidence.get("related_history_items", 0),
        "transcripts_scanned": evidence.get("transcripts_scanned", 0),
        "related_sessions": len(sessions),
        "phenomena_counts": dict(sorted(phenomena.items())),
        "command_count": command_count,
        "session_token_proxy_total": token_proxy_total,
        "reported_input_tokens": reported_input,
        "reported_output_tokens": reported_output,
        "reported_total_tokens": reported_total,
        "token_source": "reported" if reported_total else "proxy",
    }
    payload.update(section_summary)
    return payload


def pct_reduction(before: int | float, after: int | float) -> float | None:
    if not before:
        return None
    return round((before - after) / before * 100, 1)


def compare_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_phenomena = before.get("phenomena_counts", {})
    after_phenomena = after.get("phenomena_counts", {})
    keys = sorted(set(before_phenomena) | set(after_phenomena))
    phenomena_delta = {
        key: int(after_phenomena.get(key, 0)) - int(before_phenomena.get(key, 0)) for key in keys
    }
    before_tokens = int(before.get("main_token_estimate") or 0)
    after_tokens = int(after.get("main_token_estimate") or 0)
    before_proxy = int(before.get("session_token_proxy_total") or 0)
    after_proxy = int(after.get("session_token_proxy_total") or 0)
    before_reported = int(before.get("reported_total_tokens") or 0)
    after_reported = int(after.get("reported_total_tokens") or 0)
    return {
        "skill_id": after.get("skill_id") or before.get("skill_id"),
        "before_version": before.get("skill_version"),
        "after_version": after.get("skill_version"),
        "before_window": before.get("observation_window"),
        "after_window": after.get("observation_window"),
        "main_token_delta": after_tokens - before_tokens,
        "main_token_reduction_pct": pct_reduction(before_tokens, after_tokens),
        "related_session_delta": int(after.get("related_sessions") or 0)
        - int(before.get("related_sessions") or 0),
        "command_delta": int(after.get("command_count") or 0)
        - int(before.get("command_count") or 0),
        "session_token_proxy_delta": after_proxy - before_proxy,
        "session_token_proxy_reduction_pct": pct_reduction(before_proxy, after_proxy),
        "reported_total_token_delta": after_reported - before_reported,
        "reported_total_token_reduction_pct": pct_reduction(before_reported, after_reported),
        "phenomena_delta": phenomena_delta,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_analyze(
    agent: str,
    skill_path: Path,
    logs_path: Path,
    out_dir: Path,
    version: str | None,
    triggers: list[str],
    since: str | None,
    until: str | None,
    append_metrics: bool = False,
) -> dict[str, Any]:
    structure = parse_skill(skill_path)
    evidence = collect_evidence(agent, skill_path, logs_path, triggers, since, until)
    section_evidence = build_section_evidence(structure, evidence)
    script_candidates = find_script_candidates(evidence)
    snapshot = build_metrics_snapshot(
        structure,
        evidence,
        version,
        f"{evidence.get('skill_name')}-{version or 'unknown'}",
        section_evidence,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "skill-structure.json", structure)
    write_json(out_dir / "evidence.json", evidence)
    write_json(out_dir / "section-evidence.json", section_evidence)
    write_json(out_dir / "script-candidates.json", script_candidates)
    write_json(out_dir / "snapshot.json", snapshot)
    if append_metrics:
        with (out_dir / "metrics.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(snapshot, ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "structure": str(out_dir / "skill-structure.json"),
        "evidence": str(out_dir / "evidence.json"),
        "section_evidence": str(out_dir / "section-evidence.json"),
        "script_candidates": str(out_dir / "script-candidates.json"),
        "snapshot": str(out_dir / "snapshot.json"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect skill optimization evidence.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_parser = subparsers.add_parser("parse-skill")
    parse_parser.add_argument("--skill", required=True)

    install_plan_parser = subparsers.add_parser("install-plan")
    install_plan_parser.add_argument("--agent", required=True, choices=["claude", "codex"])
    install_plan_parser.add_argument("--source", required=True)

    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("--agent", required=True, choices=["claude", "codex"])
    install_parser.add_argument("--source", required=True)
    install_parser.add_argument("--overwrite", action="store_true")

    evidence_parser = subparsers.add_parser("claude-evidence")
    evidence_parser.add_argument("--skill", required=True)
    evidence_parser.add_argument("--logs", required=True)
    evidence_parser.add_argument("--trigger", action="append", default=[])
    evidence_parser.add_argument("--since")
    evidence_parser.add_argument("--until")

    codex_parser = subparsers.add_parser("codex-evidence")
    codex_parser.add_argument("--skill", required=True)
    codex_parser.add_argument("--logs", required=True)
    codex_parser.add_argument("--trigger", action="append", default=[])
    codex_parser.add_argument("--since")
    codex_parser.add_argument("--until")

    generic_evidence_parser = subparsers.add_parser("evidence")
    generic_evidence_parser.add_argument("--agent", required=True, choices=["claude", "codex"])
    generic_evidence_parser.add_argument("--skill", required=True)
    generic_evidence_parser.add_argument("--logs", required=True)
    generic_evidence_parser.add_argument("--trigger", action="append", default=[])
    generic_evidence_parser.add_argument("--since")
    generic_evidence_parser.add_argument("--until")

    section_parser = subparsers.add_parser("section-evidence")
    section_parser.add_argument("--structure", required=True)
    section_parser.add_argument("--evidence", required=True)

    script_parser = subparsers.add_parser("script-candidates")
    script_parser.add_argument("--evidence", required=True)
    script_parser.add_argument("--min-frequency", type=int, default=3)

    snapshot_parser = subparsers.add_parser("snapshot")
    snapshot_parser.add_argument("--structure", required=True)
    snapshot_parser.add_argument("--evidence", required=True)
    snapshot_parser.add_argument("--section-evidence")
    snapshot_parser.add_argument("--version")
    snapshot_parser.add_argument("--run-id")
    snapshot_parser.add_argument("--append-jsonl")

    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("--before", required=True)
    compare_parser.add_argument("--after", required=True)

    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("--agent", required=True, choices=["claude", "codex"])
    analyze_parser.add_argument("--skill", required=True)
    analyze_parser.add_argument("--logs", required=True)
    analyze_parser.add_argument("--out", required=True)
    analyze_parser.add_argument("--version")
    analyze_parser.add_argument("--trigger", action="append", default=[])
    analyze_parser.add_argument("--since")
    analyze_parser.add_argument("--until")
    analyze_parser.add_argument("--append-metrics", action="store_true")

    args = parser.parse_args()
    if args.command == "parse-skill":
        payload = parse_skill(Path(args.skill))
    elif args.command == "install-plan":
        payload = plan_install(Path(args.source), args.agent)
    elif args.command == "install":
        payload = install_skill(Path(args.source), args.agent, args.overwrite)
    elif args.command == "claude-evidence":
        payload = collect_claude_evidence(
            Path(args.skill), Path(args.logs), args.trigger, args.since, args.until
        )
    elif args.command == "codex-evidence":
        payload = collect_codex_evidence(
            Path(args.skill), Path(args.logs), args.trigger, args.since, args.until
        )
    elif args.command == "evidence":
        payload = collect_evidence(
            args.agent, Path(args.skill), Path(args.logs), args.trigger, args.since, args.until
        )
    elif args.command == "section-evidence":
        payload = build_section_evidence(load_json(Path(args.structure)), load_json(Path(args.evidence)))
    elif args.command == "script-candidates":
        payload = find_script_candidates(load_json(Path(args.evidence)), args.min_frequency)
    elif args.command == "snapshot":
        section_evidence = load_json(Path(args.section_evidence)) if args.section_evidence else None
        payload = build_metrics_snapshot(
            load_json(Path(args.structure)),
            load_json(Path(args.evidence)),
            args.version,
            args.run_id,
            section_evidence,
        )
        if args.append_jsonl:
            with Path(args.append_jsonl).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    elif args.command == "analyze":
        payload = run_analyze(
            args.agent,
            Path(args.skill),
            Path(args.logs),
            Path(args.out),
            args.version,
            args.trigger,
            args.since,
            args.until,
            args.append_metrics,
        )
    else:
        payload = compare_snapshots(load_json(Path(args.before)), load_json(Path(args.after)))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
