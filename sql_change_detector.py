from dataclasses import dataclass, field
import re
from typing import List, Optional, Sequence, Set

import sqlparse


def normalize_sql(sql: str) -> str:
    cleaned = sqlparse.format(sql, keyword_case="upper", strip_comments=True)
    return cleaned.strip()


def _remove_line_breaks(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


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
    filters: List[str] = []
    where_match = re.search(
        r"\bWHERE\s+(.*?)(?=\bGROUP\b|\bORDER\b|\bHAVING\b|\bLIMIT\b|\bOFFSET\b|\bUNION\b|\bEXCEPT\b|\bINTERSECT\b|$)",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if where_match:
        filters.append(_remove_line_breaks(where_match.group(1)))

    having_match = re.search(
        r"\bHAVING\s+(.*?)(?=\bGROUP\b|\bORDER\b|\bLIMIT\b|\bOFFSET\b|\bUNION\b|\bEXCEPT\b|\bINTERSECT\b|$)",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if having_match:
        filters.append(_remove_line_breaks(having_match.group(1)))
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

    lines: List[str] = ["Modified SQL logic detected:"]
    _append_change_lines(lines, "Filters", delta.added_filters, delta.removed_filters)
    _append_change_lines(lines, "Joins", delta.added_joins, delta.removed_joins)
    _append_change_lines(lines, "CTEs", delta.added_ctes, delta.removed_ctes)
    _append_change_lines(lines, "Output columns/transforms", delta.added_columns, delta.removed_columns)
    _append_change_lines(lines, "Tables", delta.added_tables, delta.removed_tables)
    return "\n".join(lines)