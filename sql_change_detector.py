from dataclasses import dataclass, field
import re
from typing import List, Optional, Sequence, Set

import sqlparse


def normalize_sql(sql: str) -> str:
    cleaned = sqlparse.format(sql, keyword_case="upper", strip_comments=True)
    return cleaned.strip()


def _remove_line_breaks(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _split_top_level_and(expression: str) -> List[str]:
    parts: List[str] = []
    current: List[str] = []
    depth = 0
    i = 0
    while i < len(expression):
        char = expression[i]
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)

        if depth == 0 and expression[i : i + 3].upper() == "AND":
            before_ok = i == 0 or expression[i - 1].isspace() or expression[i - 1] == ")"
            after_index = i + 3
            after_ok = after_index >= len(expression) or expression[after_index].isspace() or expression[after_index] == "("
            if before_ok and after_ok:
                part = _remove_line_breaks("".join(current))
                if part:
                    parts.append(part)
                current = []
                i += 3
                continue

        current.append(char)
        i += 1

    part = _remove_line_breaks("".join(current))
    if part:
        parts.append(part)
    return parts


def _extract_clause_predicates(sql: str, clause_name: str) -> List[str]:
    pattern = rf"\b{clause_name}\s+(.*?)(?=\bGROUP\b|\bORDER\b|\bHAVING\b|\bLIMIT\b|\bOFFSET\b|\bUNION\b|\bEXCEPT\b|\bINTERSECT\b|$)"
    matches = re.findall(pattern, sql, flags=re.IGNORECASE | re.DOTALL)
    predicates: List[str] = []
    for match in matches:
        predicates.extend(_split_top_level_and(match))
    return predicates


def _split_columns(select_clause: str) -> List[str]:
    items = re.split(r",(?![^()]*\))", select_clause)
    return [item.strip() for item in items if item.strip()]


def extract_ctes(sql: str) -> List[str]:
    matches = re.findall(r"WITH\s+([A-Za-z0-9_]+)\s+AS\s*\(", sql, flags=re.IGNORECASE)
    return list(dict.fromkeys([name.upper() for name in matches]))


def extract_tables(sql: str) -> List[str]:
    tables: List[str] = []
    from_matches = re.findall(
        r"\bFROM\s+([A-Za-z0-9_\.]+)(?:\s+AS)?(?:\s+[A-Za-z0-9_]+)?",
        sql,
        flags=re.IGNORECASE,
    )
    join_matches = re.findall(
        r"\b(?:JOIN|INNER JOIN|LEFT JOIN|RIGHT JOIN|FULL JOIN|CROSS JOIN)\s+([A-Za-z0-9_\.]+)(?:\s+AS)?(?:\s+[A-Za-z0-9_]+)?",
        sql,
        flags=re.IGNORECASE,
    )
    tables.extend(from_matches)
    tables.extend(join_matches)
    return list(dict.fromkeys([table.upper() for table in tables]))


def extract_join_clauses(sql: str) -> List[str]:
    join_patterns = re.findall(
        r"(INNER|LEFT|RIGHT|FULL|CROSS)?\s*JOIN\s+([A-Za-z0-9_\.]+)(?:\s+AS)?(?:\s+[A-Za-z0-9_]+)?\s+ON\s+(.*?)(?=\b(?:JOIN|WHERE|GROUP|ORDER|HAVING|LIMIT|OFFSET|UNION|EXCEPT|INTERSECT)\b|$)",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    clauses = []
    for join_type, table_name, condition in join_patterns:
        prefix = f"{join_type.strip().upper()} JOIN" if join_type else "JOIN"
        clauses.append(_remove_line_breaks(f"{prefix} {table_name} ON {condition}"))
    return clauses


def extract_filters(sql: str) -> List[str]:
    filters = _extract_clause_predicates(sql, "WHERE")
    filters.extend(_extract_clause_predicates(sql, "HAVING"))
    return filters


def extract_columns(sql: str) -> List[str]:
    select_match = re.search(r"\bSELECT\s+(.*?)\s+FROM\b", sql, flags=re.IGNORECASE | re.DOTALL)
    if not select_match:
        return []
    select_clause = select_match.group(1)
    columns = _split_columns(select_clause)
    return [re.sub(r"\s+AS\s+[A-Za-z0-9_]+$", "", col, flags=re.IGNORECASE).strip() for col in columns]


def _to_sorted_set(values: Sequence[str]) -> Set[str]:
    return {_canonicalize(value) for value in values if value and value.strip()}


def _canonicalize(value: str) -> str:
    compact = _remove_line_breaks(value)
    compact = re.sub(r"\s*([=<>!(),])\s*", r"\1", compact)
    return compact.lower()


def _normalize_optional_sql(sql: Optional[str]) -> str:
    if sql is None:
        return ""
    return normalize_sql(sql)


@dataclass
class SQLLogicDelta:
    change_kind: str = "modified"
    added_filters: List[str] = field(default_factory=list)
    removed_filters: List[str] = field(default_factory=list)
    added_joins: List[str] = field(default_factory=list)
    removed_joins: List[str] = field(default_factory=list)
    added_ctes: List[str] = field(default_factory=list)
    removed_ctes: List[str] = field(default_factory=list)
    added_columns: List[str] = field(default_factory=list)
    removed_columns: List[str] = field(default_factory=list)
    added_tables: List[str] = field(default_factory=list)
    removed_tables: List[str] = field(default_factory=list)

    def has_logic_changes(self) -> bool:
        return any(
            [
                self.added_filters,
                self.removed_filters,
                self.added_joins,
                self.removed_joins,
                self.added_ctes,
                self.removed_ctes,
                self.added_columns,
                self.removed_columns,
                self.added_tables,
                self.removed_tables,
            ]
        )


def detect_sql_logic_changes(old_sql: Optional[str], new_sql: Optional[str], change_kind: str = "modified") -> SQLLogicDelta:
    old_norm = _normalize_optional_sql(old_sql)
    new_norm = _normalize_optional_sql(new_sql)

    old_filters = _to_sorted_set(extract_filters(old_norm))
    new_filters = _to_sorted_set(extract_filters(new_norm))

    old_joins = _to_sorted_set(extract_join_clauses(old_norm))
    new_joins = _to_sorted_set(extract_join_clauses(new_norm))

    old_ctes = _to_sorted_set(extract_ctes(old_norm))
    new_ctes = _to_sorted_set(extract_ctes(new_norm))

    old_columns = _to_sorted_set(extract_columns(old_norm))
    new_columns = _to_sorted_set(extract_columns(new_norm))

    old_tables = _to_sorted_set(extract_tables(old_norm))
    new_tables = _to_sorted_set(extract_tables(new_norm))

    return SQLLogicDelta(
        change_kind=change_kind,
        added_filters=sorted(new_filters - old_filters),
        removed_filters=sorted(old_filters - new_filters),
        added_joins=sorted(new_joins - old_joins),
        removed_joins=sorted(old_joins - new_joins),
        added_ctes=sorted(new_ctes - old_ctes),
        removed_ctes=sorted(old_ctes - new_ctes),
        added_columns=sorted(new_columns - old_columns),
        removed_columns=sorted(old_columns - new_columns),
        added_tables=sorted(new_tables - old_tables),
        removed_tables=sorted(old_tables - new_tables),
    )


def _extract_in_clause_values(filter_text: str) -> tuple[list[str], str]:
    """
    Extract values from IN(...) clauses (e.g., country_code in ('us','in','pk')).
    Returns (values_list, column_name) or ([], '') if not a simple IN clause.
    """
    in_match = re.search(r"([a-z0-9_.]+)\s+in\s*\((.*?)\)", filter_text, re.IGNORECASE)
    if not in_match:
        return [], ""
    
    column = in_match.group(1).strip()
    values_str = in_match.group(2)
    values = re.findall(r"'([^']*)'", values_str)
    return sorted(values), column


def _format_in_value_change(prev_values: list[str], new_values: list[str], column_name: str) -> str:
    """
    Create a human-readable description of IN clause value changes.
    E.g., "country_code filter changed from US, IN, PK to CA, GB; now only CA/GB results included."
    """
    prev_set = set(prev_values)
    new_set = set(new_values)
    removed = sorted(prev_set - new_set)
    added = sorted(new_set - prev_set)
    
    if not removed and not added:
        return ""
    
    prev_display = ", ".join(v.upper() for v in prev_values) if prev_values else "none"
    new_display = ", ".join(v.upper() for v in new_values) if new_values else "none"
    
    readable_column = column_name.split(".")[-1]
    return f"{readable_column} filter changed from {prev_display} to {new_display}; now only {new_display} records are included."


def _shorten_condition(condition: str) -> str:
    compact = condition.replace(">=", " >= ").replace("<=", " <= ")
    compact = compact.replace("<>", " <> ").replace("!=", " != ")
    compact = compact.replace("=", " = ").replace(">", " > ").replace("<", " < ")
    compact = _remove_line_breaks(compact)
    if len(compact) <= 80:
        return compact
    return f"{compact[:77].rstrip()}..."


def _render_short_change_summary(delta: SQLLogicDelta) -> str:
    statements: List[str] = []

    matched_filter_columns: set[str] = set()
    for old_filter in sorted(delta.removed_filters):
        prev_values, column = _extract_in_clause_values(old_filter)
        if not prev_values or not column:
            continue
        for new_filter in sorted(delta.added_filters):
            new_values, new_column = _extract_in_clause_values(new_filter)
            if new_values and new_column and new_column.lower() == column.lower():
                description = _format_in_value_change(prev_values, new_values, column)
                if description:
                    statements.append(description)
                    matched_filter_columns.add(column.lower())
                break

    unmatched_added_filters = [
        item for item in delta.added_filters if _extract_in_clause_values(item)[1].lower() not in matched_filter_columns
    ]
    unmatched_removed_filters = [
        item for item in delta.removed_filters if _extract_in_clause_values(item)[1].lower() not in matched_filter_columns
    ]

    if unmatched_added_filters or unmatched_removed_filters:
        details: List[str] = []
        if unmatched_added_filters:
            details.append(f"added filter {_shorten_condition(unmatched_added_filters[0])}")
        if unmatched_removed_filters:
            details.append(f"removed filter {_shorten_condition(unmatched_removed_filters[0])}")
        statements.append("SQL filter logic changed: " + "; ".join(details) + ".")

    if delta.added_joins or delta.removed_joins:
        details: List[str] = []
        if delta.added_joins:
            details.append("join conditions were added")
        if delta.removed_joins:
            details.append("join conditions were removed")
        statements.append("SQL join logic changed: " + " and ".join(details) + ".")

    if delta.added_columns or delta.removed_columns:
        details: List[str] = []
        if delta.added_columns:
            details.append("output columns were added")
        if delta.removed_columns:
            details.append("output columns were removed")
        statements.append("SQL output changed: " + " and ".join(details) + ".")

    if delta.added_tables or delta.removed_tables:
        details: List[str] = []
        if delta.added_tables:
            details.append("new source tables were referenced")
        if delta.removed_tables:
            details.append("some source tables were removed")
        statements.append("SQL source scope changed: " + " and ".join(details) + ".")

    if delta.added_ctes or delta.removed_ctes:
        details: List[str] = []
        if delta.added_ctes:
            details.append("new CTE steps were added")
        if delta.removed_ctes:
            details.append("some CTE steps were removed")
        statements.append("SQL transformation flow changed: " + " and ".join(details) + ".")

    if not statements:
        return "SQL logic changed in a small way."

    return " ".join(statements[:2])


def _append_change_lines(lines: List[str], title: str, added: List[str], removed: List[str]) -> None:
    if not added and not removed:
        return
    lines.append(f"- {title}:")
    for item in added:
        lines.append(f"  - Added: {item}")
    for item in removed:
        lines.append(f"  - Removed: {item}")


def render_delta_snippet(delta: SQLLogicDelta) -> str:
    if delta.change_kind == "added":
        return "New SQL file added. Documentation will include the new query logic after merge."
    if delta.change_kind == "removed":
        return "SQL file removed. Existing documentation should be reviewed for archival or deprecation updates."

    if not delta.has_logic_changes():
        return "No documentation-impacting SQL logic change detected (formatting/comments only)."

    return _render_short_change_summary(delta)