"""
sql_generator.py
----------------
AI-powered SQL generation service.
Supports:
  - OpenAI Chat Completions API (preferred, model configurable via env)
  - Rule-based fallback (no API key required)

Changes vs. previous version
-----------------------------
Bug fixes
  1. Removed walrus-operator misuse inside re.search() call (line ~211).
  2. Fixed aggregate comparison: use `==` instead of `in (tuple,)`.
  3. Fixed ORDER keyword detection – was using `kw in q.split()` which
     missed words adjacent to punctuation; now uses a proper word-boundary
     regex.
  4. Numeric condition patterns that have only ONE capture group (i.e. the
     field cannot be extracted from the pattern itself) now safely fall back
     to _guess_numeric_field; a None result is guarded against.
  5. "last N" in _extract_limit was silently adding a meaningless LIMIT;
     it is now handled together with "last" ordering (DESC + LIMIT).
  6. OpenAI model is now configurable via OPENAI_MODEL env var (default
     gpt-4o-mini, not the deprecated gpt-3.5-turbo).

New: SQL output tuner / post-processor (SQLOutputTuner)
  - Strips accidental markdown code fences
  - Uppercases all SQL keywords and functions
  - Normalises whitespace (collapses runs, trims blank lines)
  - Adds a trailing semicolon if missing
  - Pretty-prints major SQL clauses onto separate indented lines
  - Standardises comparison operators (e.g. `< >` → `<>`)
  - Removes duplicate consecutive WHERE/AND conditions
  - Collapses redundant parentheses around simple literals
"""

import os
import re
import logging
import openai

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SQL keywords & functions (used by the tuner)
# ---------------------------------------------------------------------------

_SQL_KEYWORDS = {
    "SELECT", "DISTINCT", "FROM", "WHERE", "AND", "OR", "NOT", "IN",
    "IS", "NULL", "LIKE", "BETWEEN", "EXISTS",
    "ORDER", "BY", "GROUP", "HAVING", "LIMIT", "OFFSET",
    "JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "FULL", "CROSS", "ON",
    "AS", "INSERT", "INTO", "VALUES", "UPDATE", "SET", "DELETE",
    "CREATE", "TABLE", "DROP", "ALTER", "ADD", "COLUMN", "PRIMARY",
    "KEY", "FOREIGN", "REFERENCES", "INDEX", "VIEW", "UNION", "ALL",
    "CASE", "WHEN", "THEN", "ELSE", "END", "WITH", "RETURNING",
    "ASC", "DESC",
}

_SQL_FUNCTIONS = {
    "COUNT", "SUM", "AVG", "MAX", "MIN",
    "COALESCE", "IFNULL", "NULLIF", "ISNULL",
    "ROUND", "FLOOR", "CEIL", "ABS", "LENGTH",
    "UPPER", "LOWER", "TRIM", "SUBSTRING", "CONCAT",
    "NOW", "CURDATE", "CURRENT_DATE", "CURRENT_TIMESTAMP",
    "DATEADD", "DATEDIFF", "CAST", "CONVERT",
    "YEAR", "MONTH", "DATE",
}

# Clauses that should start on a new (indented) line
_CLAUSE_PATTERN = re.compile(
    r"\b(SELECT|FROM|WHERE|GROUP\s+BY|ORDER\s+BY|HAVING|LIMIT|OFFSET|"
    r"LEFT\s+JOIN|RIGHT\s+JOIN|INNER\s+JOIN|FULL\s+OUTER\s+JOIN|"
    r"CROSS\s+JOIN|JOIN|UNION\s+ALL|UNION)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# SQL Output Tuner
# ---------------------------------------------------------------------------

class SQLOutputTuner:
    """
    Post-processes a raw SQL string into a clean, consistently formatted,
    well-indented statement.

    Pipeline
    --------
    1. Strip markdown fences
    2. Uppercase keywords & functions
    3. Normalise whitespace
    4. Pretty-print clause breaks
    5. Ensure trailing semicolon
    6. Normalise comparison operators
    7. Deduplicate redundant AND conditions
    8. Collapse trivial single-value parentheses
    """

    # ── 1. Strip markdown fences ──────────────────────────────────────────
    _FENCE_RE = re.compile(r"^```[a-zA-Z]*\n?|\n?```$", re.MULTILINE)

    # ── 6. Operator normalisation map ─────────────────────────────────────
    _OP_MAP = [
        (re.compile(r"<\s*>"),   "<>"),
        (re.compile(r"!\s*="),   "!="),
        (re.compile(r"<\s*="),   "<="),
        (re.compile(r">\s*="),   ">="),
        (re.compile(r"=\s*="),   "="),
    ]

    def tune(self, sql: str) -> str:
        sql = self._strip_fences(sql)
        sql = self._uppercase_keywords(sql)
        sql = self._normalise_whitespace(sql)
        sql = self._pretty_print(sql)
        sql = self._ensure_semicolon(sql)
        sql = self._normalise_operators(sql)
        sql = self._deduplicate_conditions(sql)
        sql = self._collapse_trivial_parens(sql)
        return sql.strip()

    # ── helpers ───────────────────────────────────────────────────────────

    def _strip_fences(self, sql: str) -> str:
        return self._FENCE_RE.sub("", sql).strip()

    def _uppercase_keywords(self, sql: str) -> str:
        """
        Uppercase SQL keywords and functions while leaving string literals
        and identifiers untouched.
        """
        # Tokenise around string literals so we don't alter them
        parts = re.split(r"('(?:[^'\\]|\\.)*')", sql)
        result = []
        for i, part in enumerate(parts):
            if i % 2 == 1:
                # Inside a string literal – leave as-is
                result.append(part)
            else:
                # Outside a literal – uppercase known tokens
                def _up(m: re.Match) -> str:
                    word = m.group(0)
                    upper = word.upper()
                    if upper in _SQL_KEYWORDS or upper in _SQL_FUNCTIONS:
                        return upper
                    return word
                result.append(re.sub(r"\b[A-Za-z_][A-Za-z_0-9]*\b", _up, part))
        return "".join(result)

    def _normalise_whitespace(self, sql: str) -> str:
        """Collapse runs of blanks (but keep newlines for now)."""
        # Collapse multiple spaces on the same line
        sql = re.sub(r"[ \t]+", " ", sql)
        # Collapse multiple blank lines
        sql = re.sub(r"\n{3,}", "\n\n", sql)
        # Strip trailing whitespace on each line
        sql = "\n".join(line.rstrip() for line in sql.splitlines())
        return sql.strip()

    def _pretty_print(self, sql: str) -> str:
        """
        Collapse the SQL to a single logical line first, then re-insert
        newlines + 4-space indents before each major clause keyword.
        """
        # Flatten to one line (preserving string literals)
        parts = re.split(r"('(?:[^'\\]|\\.)*')", sql)
        flat_parts = []
        for i, part in enumerate(parts):
            if i % 2 == 1:
                flat_parts.append(part)
            else:
                flat_parts.append(re.sub(r"\s+", " ", part))
        flat = "".join(flat_parts).strip()

        # Now break at clause boundaries
        def _insert_break(m: re.Match) -> str:
            kw = m.group(0).upper()
            # Collapse internal whitespace in multi-word keywords
            kw = re.sub(r"\s+", " ", kw)
            return f"\n    {kw}"

        formatted = _CLAUSE_PATTERN.sub(_insert_break, flat)

        # The very first token (SELECT / INSERT / …) should not be indented
        lines = formatted.splitlines()
        if lines and lines[0].startswith("    "):
            lines[0] = lines[0].lstrip()
        return "\n".join(lines)

    def _ensure_semicolon(self, sql: str) -> str:
        sql = sql.rstrip()
        if not sql.endswith(";"):
            sql += ";"
        return sql

    def _normalise_operators(self, sql: str) -> str:
        """Fix spacing around comparison operators outside string literals."""
        parts = re.split(r"('(?:[^'\\]|\\.)*')", sql)
        result = []
        for i, part in enumerate(parts):
            if i % 2 == 1:
                result.append(part)
            else:
                for pattern, replacement in self._OP_MAP:
                    part = pattern.sub(replacement, part)
                result.append(part)
        return "".join(result)

    def _deduplicate_conditions(self, sql: str) -> str:
        """
        Remove exact-duplicate AND/OR conditions in a WHERE clause.
        e.g.  WHERE a = 1 AND a = 1  →  WHERE a = 1
        """
        def _dedup_clause(m: re.Match) -> str:
            intro = m.group(1)   # "WHERE " or "HAVING "
            body  = m.group(2)
            # Split on AND/OR keeping the separator
            tokens = re.split(r"\s+(AND|OR)\s+", body, flags=re.IGNORECASE)
            seen:  list[str] = []
            ops:   list[str] = []
            for j, tok in enumerate(tokens):
                if j % 2 == 0:
                    norm = tok.strip()
                    if norm not in seen:
                        seen.append(norm)
                else:
                    ops.append(tok.upper())

            # Rebuild
            rebuilt = seen[0]
            for k, op in enumerate(ops):
                if k + 1 < len(seen):
                    rebuilt += f" {op} {seen[k + 1]}"
            return intro + rebuilt

        sql = re.sub(
            r"((?:WHERE|HAVING)\s+)((?:.|\n)+?)(?=\n\s*(?:GROUP|ORDER|LIMIT|OFFSET|UNION|;|$))",
            _dedup_clause,
            sql,
            flags=re.IGNORECASE,
        )
        return sql

    def _collapse_trivial_parens(self, sql: str) -> str:
        """
        Replace ( simple_value ) with simple_value where the parentheses
        add no semantic value — e.g. COUNT( * ) → COUNT(*).
        """
        # Fix COUNT( * ) → COUNT(*)
        sql = re.sub(r"COUNT\s*\(\s*\*\s*\)", "COUNT(*)", sql, flags=re.IGNORECASE)
        # Collapse (   value   ) → (value) for literals / plain identifiers
        sql = re.sub(r"\(\s*([A-Za-z0-9_.]+)\s*\)", r"(\1)", sql)
        return sql


# Module-level singleton tuner
_tuner = SQLOutputTuner()


# ---------------------------------------------------------------------------
# OpenAI helper
# ---------------------------------------------------------------------------

def _generate_with_openai(natural_query: str) -> str:
    """
    Call the OpenAI Chat Completions API to convert a natural-language query
    into a well-formatted SQL statement.
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set.")

    # Allow model override via env; default to a modern, cost-effective model
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    client = openai.OpenAI(api_key=api_key)

    system_prompt = (
        "You are an expert SQL developer. "
        "Convert the user's natural-language description into a single, valid SQL query.\n"
        "Rules:\n"
        "  1. Output ONLY the raw SQL statement — no explanations, no markdown fences.\n"
        "  2. Use UPPERCASE for ALL SQL keywords (SELECT, FROM, WHERE, etc.).\n"
        "  3. Indent each major clause (FROM, WHERE, GROUP BY, ORDER BY, HAVING, LIMIT) "
        "with exactly 4 spaces on its own line.\n"
        "  4. Infer sensible, snake_case table and column names from the description.\n"
        "  5. Always end the statement with a semicolon.\n"
        "  6. Support SELECT, WHERE, GROUP BY, ORDER BY, HAVING, LIMIT, COUNT, SUM, AVG, "
        "MAX, MIN, JOIN, UNION, CASE/WHEN/THEN/ELSE/END.\n"
        "  7. For ambiguous queries prefer a safe SELECT over destructive statements.\n"
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": natural_query},
        ],
        temperature=0.1,   # lower = more deterministic / less hallucination
        max_tokens=768,
    )

    raw_sql = response.choices[0].message.content.strip()

    # Run through the output tuner regardless of what the model returned
    return _tuner.tune(raw_sql)


# ---------------------------------------------------------------------------
# Rule-based fallback
# ---------------------------------------------------------------------------

class RuleBasedSQLGenerator:
    """
    A pattern-matching SQL generator used when no OpenAI key is configured.
    Handles common English query patterns.
    """

    # ---------- keyword maps ----------
    AGGREGATE_MAP = {
        "count":   "COUNT(*)",
        "total":   "COUNT(*)",
        "number":  "COUNT(*)",
        "how many":"COUNT(*)",
        "sum":     "SUM",
        "average": "AVG",
        "avg":     "AVG",
        "maximum": "MAX",
        "max":     "MAX",
        "minimum": "MIN",
        "min":     "MIN",
    }

    ORDER_KEYWORDS = {
        "highest":  "DESC",
        "largest":  "DESC",
        "greatest": "DESC",
        "lowest":   "ASC",
        "smallest": "ASC",
        "least":    "ASC",
    }

    # Common field synonyms → canonical column name
    FIELD_ALIASES = {
        "salary":   "salary",
        "age":      "age",
        "score":    "score",
        "marks":    "marks",
        "revenue":  "revenue",
        "sales":    "sales",
        "price":    "price",
        "amount":   "amount",
        "quantity": "quantity",
        "rating":   "rating",
        "grade":    "grade",
        "points":   "points",
    }

    def generate(self, query: str) -> str:
        q = query.lower().strip()

        table      = self._extract_table(q)
        conditions = self._extract_conditions(q, query)
        order      = self._extract_order(q)
        limit      = self._extract_limit(q)
        aggregate  = self._extract_aggregate(q)
        group_by   = self._extract_group_by(q)

        # "last N" → ORDER BY id DESC LIMIT N (fix: was only LIMIT)
        last_m = re.search(r"\blast\s+(\d+)\b", q)
        if last_m and limit is None:
            limit = last_m.group(1)
            if order is None:
                order = "id DESC"

        # Build SELECT clause
        select_clause = f"SELECT {aggregate}" if aggregate else "SELECT *"

        sql_parts = [select_clause, f"FROM {table}"]

        if conditions:
            sql_parts.append(f"WHERE {conditions}")

        if group_by:
            sql_parts.append(f"GROUP BY {group_by}")

        if order:
            sql_parts.append(f"ORDER BY {order}")

        if limit:
            sql_parts.append(f"LIMIT {limit}")

        # Join with newlines + indent for readability
        raw_sql = "\n    ".join(sql_parts)

        # Run through output tuner for consistent formatting
        return _tuner.tune(raw_sql)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_table(self, q: str) -> str:
        """Guess table name from common entity nouns in the query."""
        entity_map = {
            "employee":     "employees",
            "employees":    "employees",
            "staff":        "employees",
            "worker":       "employees",
            "workers":      "employees",
            "customer":     "customers",
            "customers":    "customers",
            "client":       "clients",
            "clients":      "clients",
            "order":        "orders",
            "orders":       "orders",
            "product":      "products",
            "products":     "products",
            "item":         "items",
            "items":        "items",
            "student":      "students",
            "students":     "students",
            "user":         "users",
            "users":        "users",
            "sale":         "sales",
            "sales":        "sales",
            "invoice":      "invoices",
            "invoices":     "invoices",
            "department":   "departments",
            "departments":  "departments",
            "transaction":  "transactions",
            "transactions": "transactions",
            "record":       "records",
            "records":      "records",
            "report":       "reports",
            "reports":      "reports",
            "account":      "accounts",
            "accounts":     "accounts",
            "payment":      "payments",
            "payments":     "payments",
            "project":      "projects",
            "projects":     "projects",
            "supplier":     "suppliers",
            "suppliers":    "suppliers",
            "vendor":       "vendors",
            "vendors":      "vendors",
        }
        for word in re.findall(r"[a-z]+", q):
            if word in entity_map:
                return entity_map[word]
        return "records"

    def _extract_conditions(self, q: str, original_query: str) -> str:
        """Extract WHERE clause conditions from the query."""
        conditions: list[str] = []

        # ── Numeric comparisons ──────────────────────────────────────────
        # Patterns where the field name CAN be extracted from the match
        field_num_patterns = [
            (r"(\w+)\s+(?:greater|more|higher|above|over)\s+than\s+(\d+(?:\.\d+)?)",  ">"),
            (r"(\w+)\s+(?:less|lower|below|under)\s+than\s+(\d+(?:\.\d+)?)",          "<"),
            (r"(\w+)\s+(?:equal(?:s)?\s+to|is|=)\s+(\d+(?:\.\d+)?)",                 "="),
            (r"(\w+)\s+(?:at\s+least|minimum\s+of)\s+(\d+(?:\.\d+)?)",               ">="),
            (r"(\w+)\s+(?:at\s+most|maximum\s+of)\s+(\d+(?:\.\d+)?)",                "<="),
        ]
        # Patterns where the field must be guessed from context
        context_num_patterns = [
            (r"(?:greater|more|higher|above|over)\s+than\s+(\d+(?:\.\d+)?)",  ">"),
            (r"(?:less|lower|below|under)\s+than\s+(\d+(?:\.\d+)?)",          "<"),
            (r"\babove\s+(\d+(?:\.\d+)?)",                                    ">"),
            (r"\bbelow\s+(\d+(?:\.\d+)?)",                                    "<"),
        ]

        matched_num = False
        for pattern, op in field_num_patterns:
            m = re.search(pattern, q)
            if m:
                field = self._normalise_field(m.group(1))
                value = m.group(2)
                conditions.append(f"{field} {op} {value}")
                matched_num = True
                break

        if not matched_num:
            for pattern, op in context_num_patterns:
                m = re.search(pattern, q)
                if m:
                    value = m.group(1)
                    field = self._guess_numeric_field(q)
                    if field:  # BUG FIX: guard against None
                        conditions.append(f"{field} {op} {value}")
                    break

        # ── City / location ──────────────────────────────────────────────
        # BUG FIX: removed walrus operator misuse; search the original query
        # for proper capitalisation detection.
        loc_m = re.search(
            r"(?:from|in|at|located\s+in)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
            original_query,
            re.IGNORECASE,
        )
        if loc_m:
            city = loc_m.group(1).strip().title()
            conditions.append(f"city = '{city}'")

        # ── Date / time ──────────────────────────────────────────────────
        if "this month" in q:
            conditions.append(
                "MONTH(created_at) = MONTH(CURRENT_DATE())"
                " AND YEAR(created_at) = YEAR(CURRENT_DATE())"
            )
        elif "today" in q:
            conditions.append("DATE(created_at) = CURRENT_DATE()")
        elif "this year" in q:
            conditions.append("YEAR(created_at) = YEAR(CURRENT_DATE())")
        elif "last month" in q:
            conditions.append(
                "MONTH(created_at) = MONTH(CURRENT_DATE() - INTERVAL 1 MONTH)"
                " AND YEAR(created_at) = YEAR(CURRENT_DATE() - INTERVAL 1 MONTH)"
            )
        elif "last year" in q:
            conditions.append("YEAR(created_at) = YEAR(CURRENT_DATE()) - 1")

        # ── Status ───────────────────────────────────────────────────────
        if re.search(r"\bactive\b", q):
            conditions.append("status = 'active'")
        elif re.search(r"\binactive\b", q):
            conditions.append("status = 'inactive'")
        elif re.search(r"\bpending\b", q):
            conditions.append("status = 'pending'")
        elif re.search(r"\bcompleted\b", q):
            conditions.append("status = 'completed'")

        # ── Gender ───────────────────────────────────────────────────────
        if re.search(r"\b(female|women|woman)\b", q):
            conditions.append("gender = 'female'")
        elif re.search(r"\b(male|men|man)\b", q):
            conditions.append("gender = 'male'")

        return " AND ".join(conditions)

    def _extract_order(self, q: str) -> str | None:
        """Extract ORDER BY clause."""
        # BUG FIX: use word-boundary regex instead of `kw in q.split()`
        for kw, direction in self.ORDER_KEYWORDS.items():
            if re.search(rf"\b{re.escape(kw)}\b", q):
                field = self._guess_numeric_field(q) or "id"
                return f"{field} {direction}"

        # Explicit "top N" → handled elsewhere (limit); infer DESC ordering
        if re.search(r"\btop\s+\d+\b", q):
            field = self._guess_numeric_field(q) or "id"
            return f"{field} DESC"

        if "sort" in q or re.search(r"\border\s+by\b", q):
            field = self._guess_numeric_field(q) or "id"
            direction = "DESC" if "descend" in q else "ASC"
            return f"{field} {direction}"

        return None

    def _extract_limit(self, q: str) -> str | None:
        """Extract LIMIT clause from 'top N' or 'first N' phrases."""
        # BUG FIX: removed "last" from this pattern — "last N" is handled
        # specially in generate() to add DESC ordering as well.
        m = re.search(r"\b(?:top|first|limit)\s+(\d+)\b", q)
        if m:
            return m.group(1)
        return None

    def _extract_aggregate(self, q: str) -> str | None:
        """Detect aggregate functions."""
        for kw, agg in self.AGGREGATE_MAP.items():
            if re.search(rf"\b{re.escape(kw)}\b", q):
                # BUG FIX: use == instead of `in (tuple,)` for readability/correctness
                if agg == "COUNT(*)":
                    return agg
                # Try to find which field to aggregate
                field = self._guess_numeric_field(q)
                if field:
                    return f"{agg}({field})"
                return f"{agg}(*)"
        return None

    def _extract_group_by(self, q: str) -> str | None:
        """Detect GROUP BY hint words."""
        m = re.search(
            r"(?:group(?:ed)?\s+by|per|by\s+each|for\s+each)\s+(\w+)", q
        )
        if m:
            return m.group(1)
        if re.search(r"\bper\s+city\b|\bby\s+city\b", q):
            return "city"
        if re.search(r"\bper\s+department\b|\bby\s+department\b", q):
            return "department"
        if re.search(r"\bper\s+category\b|\bby\s+category\b", q):
            return "category"
        if re.search(r"\bper\s+region\b|\bby\s+region\b", q):
            return "region"
        return None

    def _normalise_field(self, word: str) -> str:
        """Map a potentially noisy word to a clean column name."""
        word = word.lower().strip()
        return self.FIELD_ALIASES.get(word, word)

    def _guess_numeric_field(self, q: str) -> str | None:
        """Pick the most likely numeric column from the query text."""
        for field in self.FIELD_ALIASES:
            if re.search(rf"\b{re.escape(field)}\b", q):
                return field
        return None


# ---------------------------------------------------------------------------
# Public API used by app.py
# ---------------------------------------------------------------------------

_rule_gen = RuleBasedSQLGenerator()


def generate_sql(natural_query: str) -> dict:
    """
    Generate SQL from a natural-language query.

    Returns a dict with:
      - sql    : the generated SQL string
      - method : 'openai' | 'rule-based'
      - error  : error message string (only present on failure)
    """
    if not natural_query or not natural_query.strip():
        return {"error": "Query cannot be empty."}

    natural_query = natural_query.strip()

    # Try OpenAI first
    api_key = os.getenv("OPENAI_API_KEY", "")
    if api_key:
        try:
            sql = _generate_with_openai(natural_query)
            logger.info("SQL generated via OpenAI.")
            return {"sql": sql, "method": "openai"}
        except Exception as exc:
            logger.warning(
                "OpenAI generation failed: %s. Falling back to rule-based.", exc
            )

    # Fallback → rule-based
    try:
        sql = _rule_gen.generate(natural_query)
        logger.info("SQL generated via rule-based engine.")
        return {"sql": sql, "method": "rule-based"}
    except Exception as exc:
        logger.error("Rule-based generation failed: %s", exc)
        return {"error": f"SQL generation failed: {exc}"}
