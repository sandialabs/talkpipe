import re
from typing import Iterable


CONSTRAINT_PATTERNS = (
    r"\b(must|should|always|never|do not|don't|avoid|required|please)\b",
    r"\b(prefer|use|instead of|not allowed)\b",
)

FACT_PATTERNS = (
    r"\b(my name is|i am|i live in|i work at|my email is)\b",
    r"\b(version|deadline|date|path|url|endpoint|model)\b",
)

OPEN_ITEM_PATTERNS = (
    r"\?$",
    r"\b(todo|next step|follow up|pending|blocked|need to)\b",
)

CATEGORY_WEIGHTS = {
    "constraint": 50.0,
    "fact": 35.0,
    "open_item": 25.0,
    "other": 10.0,
}

ROLE_WEIGHTS = {
    "user": 6.0,
    "assistant": 2.0,
    "system": 1.0,
    "unknown": 0.0,
}


def normalize_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", str(text)).strip().lower()
    return normalized


def _matches_any_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _classify_line(line: str) -> str:
    normalized = normalize_text(line)
    if not normalized:
        return "other"
    if _matches_any_pattern(normalized, CONSTRAINT_PATTERNS):
        return "constraint"
    if _matches_any_pattern(normalized, FACT_PATTERNS):
        return "fact"
    if _matches_any_pattern(normalized, OPEN_ITEM_PATTERNS):
        return "open_item"
    return "other"


def _extract_role_and_text(line: str) -> tuple[str, str]:
    text = str(line).strip()
    match = re.match(r"^([A-Za-z_]+):\s*(.*)$", text)
    if not match:
        return "unknown", text
    role = match.group(1).strip().lower()
    content = match.group(2).strip()
    if not content:
        content = text
    return role, content


def _score_line(category: str, role: str, content: str, index: int) -> float:
    category_weight = CATEGORY_WEIGHTS.get(category, CATEGORY_WEIGHTS["other"])
    role_weight = ROLE_WEIGHTS.get(role, ROLE_WEIGHTS["unknown"])
    recency_bonus = float(index) * 0.5
    verbosity_penalty = len(content) / 200.0
    return category_weight + role_weight + recency_bonus - verbosity_penalty


def summarize(lines: Iterable[str], max_chars: int, strategy: str = "deterministic") -> str:
    if strategy != "deterministic":
        raise ValueError(f"Unsupported summarize strategy: {strategy}")

    buckets = {"constraint": [], "fact": [], "open_item": [], "other": []}
    seen = set()
    for index, line in enumerate(lines):
        role, content = _extract_role_and_text(line)
        normalized = normalize_text(content)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        category = _classify_line(content)
        score = _score_line(category, role, content, index)
        buckets[category].append((score, index, str(line).strip()))

    for category in buckets:
        buckets[category].sort(key=lambda item: (-item[0], -item[1], item[2]))

    section_defs = [
        ("Constraints", "constraint", 8),
        ("Key facts", "fact", 10),
        ("Open items", "open_item", 8),
        ("Other context", "other", 8),
    ]
    section_lines: dict[str, list[str]] = {}
    section_titles: dict[str, str] = {}
    for title, key, limit in section_defs:
        section_titles[key] = title
        section_lines[key] = [line for _, _, line in buckets[key][:limit]]

    def render() -> str:
        parts: list[str] = []
        for title, key, _ in section_defs:
            lines_for_section = section_lines[key]
            if lines_for_section:
                parts.append(f"{title}:\n- " + "\n- ".join(lines_for_section))
        return "\n\n".join(parts).strip()

    summary = render()
    if len(summary) <= max_chars:
        return summary

    # Budget-aware trimming: drop lowest-priority lines first.
    trim_order = ["other", "open_item", "fact", "constraint"]
    while len(summary) > max_chars:
        removed = False
        for key in trim_order:
            if section_lines[key]:
                section_lines[key].pop()
                removed = True
                break
        if not removed:
            break
        summary = render()

    if len(summary) <= max_chars:
        return summary
    return summary[-max_chars:]
