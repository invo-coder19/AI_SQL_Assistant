"""
sql_generator.py
----------------
AI-powered SQL generation service.
Supports:
  - OpenAI GPT API (preferred)
  - Rule-based fallback (no API key required)
"""

import os
import re
import logging
import openai

logger = logging.getLogger(__name__)

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

    client = openai.OpenAI(api_key=api_key)

    system_prompt = (
        "You are an expert SQL developer. "
        "Convert the user's natural-language description into a single, valid SQL query. "
        "Rules:\n"
        "  1. Output ONLY the SQL statement — no explanations, no markdown fences.\n"
        "  2. Use uppercase for all SQL keywords (SELECT, FROM, WHERE, etc.).\n"
        "  3. Use proper indentation (4 spaces per level).\n"
        "  4. Infer sensible table and column names from the description.\n"
        "  5. Always end the statement with a semicolon.\n"
        "  6. Support SELECT, WHERE, GROUP BY, ORDER BY, COUNT, SUM, AVG, JOIN.\n"
    )

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": natural_query},
        ],
        temperature=0.2,
        max_tokens=512,
    )

    sql = response.choices[0].message.content.strip()

    # Strip any accidental markdown code fences the model might include
    sql = re.sub(r"^```[a-zA-Z]*\n?", "", sql)
    sql = re.sub(r"\n?```$", "", sql)
    return sql.strip()


# ---------------------------------------------------------------------------
# Rule-based fallback
# ---------------------------------------------------------------------------

class RuleBasedSQLGenerator:
    """
    A simple pattern-matching SQL generator used when no OpenAI key is
    configured.  Handles common English query patterns.
    """

    # ---------- keyword maps ----------
    AGGREGATE_MAP = {
        "count":   "COUNT(*)",
        "total":   "COUNT(*)",
        "number":  "COUNT(*)",
        "sum":     "SUM",
        "average": "AVG",
        "avg":     "AVG",
        "maximum": "MAX",
        "max":     "MAX",
        "minimum": "MIN",
        "min":     "MIN",
    }

    ORDER_KEYWORDS = {
        "top":      "DESC",
        "highest":  "DESC",
        "largest":  "DESC",
        "greatest": "DESC",
        "lowest":   "ASC",
        "smallest": "ASC",
        "bottom":   "ASC",
        "least":    "ASC",
    }

    # Common field synonyms → canonical column name
    FIELD_ALIASES = {
        "salary":  "salary",
        "age":     "age",
        "score":   "score",
        "marks":   "marks",
        "revenue": "revenue",
        "sales":   "sales",
        "price":   "price",
        "amount":  "amount",
        "quantity": "quantity",
        "rating":  "rating",
    }

    def generate(self, query: str) -> str:
        q = query.lower().strip()

        table      = self._extract_table(q)
        conditions = self._extract_conditions(q)
        order      = self._extract_order(q)
        limit      = self._extract_limit(q)
        aggregate  = self._extract_aggregate(q)
        group_by   = self._extract_group_by(q)

        # Build SELECT clause
        if aggregate:
            select_clause = f"SELECT {aggregate}"
        else:
            select_clause = "SELECT *"

        sql_parts = [f"{select_clause}", f"FROM {table}"]

        if conditions:
            sql_parts.append(f"WHERE {conditions}")

        if group_by:
            sql_parts.append(f"GROUP BY {group_by}")

        if order:
            sql_parts.append(f"ORDER BY {order}")

        if limit:
            sql_parts.append(f"LIMIT {limit}")

        # Join with newlines + indent for readability
        sql = "\n    ".join(sql_parts) + ";"
        return sql

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_table(self, q: str) -> str:
        """Guess table name from common nouns in the query."""
        entity_map = {
            "employee":  "employees",
            "employees": "employees",
            "customer":  "customers",
            "customers": "customers",
            "order":     "orders",
            "orders":    "orders",
            "product":   "products",
            "products":  "products",
            "student":   "students",
            "students":  "students",
            "user":      "users",
            "users":     "users",
            "sale":      "sales",
            "sales":     "sales",
            "invoice":   "invoices",
            "invoices":  "invoices",
            "department":"departments",
            "departments":"departments",
            "transaction":"transactions",
            "transactions":"transactions",
            "record":    "records",
            "records":   "records",
        }
        for word in q.split():
            word_clean = word.strip(".,?!")
            if word_clean in entity_map:
                return entity_map[word_clean]
        return "table_name"

    def _extract_conditions(self, q: str) -> str:
        """Extract WHERE clause conditions from the query."""
        conditions = []

        # Numeric comparisons  e.g. "salary greater than 50000"
        num_patterns = [
            (r"(\w+)\s+(?:greater|more|higher|above|over)\s+than\s+(\d+(?:\.\d+)?)", ">"),
            (r"(\w+)\s+(?:less|lower|below|under)\s+than\s+(\d+(?:\.\d+)?)", "<"),
            (r"(\w+)\s+(?:equal(?:s)?\s+to|is|=)\s+(\d+(?:\.\d+)?)", "="),
            (r"(\w+)\s+(?:at\s+least|minimum\s+of)\s+(\d+(?:\.\d+)?)", ">="),
            (r"(\w+)\s+(?:at\s+most|maximum\s+of)\s+(\d+(?:\.\d+)?)", "<="),
            (r"(?:greater|more|higher|above|over)\s+than\s+(\d+(?:\.\d+)?)", ">"),
            (r"(?:less|lower|below|under)\s+than\s+(\d+(?:\.\d+)?)", "<"),
            (r"(?:above|over)\s+(\d+(?:\.\d+)?)", ">"),
            (r"(?:below|under)\s+(\d+(?:\.\d+)?)", "<"),
        ]
        for pattern, op in num_patterns:
            m = re.search(pattern, q)
            if m:
                if len(m.groups()) == 2:
                    field = self._normalise_field(m.group(1))
                    value = m.group(2)
                else:
                    field = self._guess_numeric_field(q)
                    value = m.group(1)
                conditions.append(f"{field} {op} {value}")
                break

        # City / location  e.g. "from Mumbai", "in Delhi"
        loc_m = re.search(
            r"(?:from|in|at|located\s+in)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", query := q
        , re.IGNORECASE)
        if loc_m:
            city = loc_m.group(1).strip().title()
            conditions.append(f"city = '{city}'")

        # Date / time  e.g. "this month", "today", "this year"
        if "this month" in q:
            conditions.append(
                "MONTH(created_at) = MONTH(CURRENT_DATE())"
                " AND YEAR(created_at) = YEAR(CURRENT_DATE())"
            )
        elif "today" in q:
            conditions.append("DATE(created_at) = CURRENT_DATE()")
        elif "this year" in q:
            conditions.append("YEAR(created_at) = YEAR(CURRENT_DATE())")

        # Status / active
        if re.search(r"\bactive\b", q):
            conditions.append("status = 'active'")
        elif re.search(r"\binactive\b", q):
            conditions.append("status = 'inactive'")

        return " AND ".join(conditions)

    def _extract_order(self, q: str) -> str | None:
        """Extract ORDER BY clause."""
        for kw, direction in self.ORDER_KEYWORDS.items():
            if kw in q.split():
                field = self._guess_numeric_field(q) or "id"
                return f"{field} {direction}"
        if "sort" in q or "order" in q:
            field = self._guess_numeric_field(q) or "id"
            direction = "DESC" if "descend" in q else "ASC"
            return f"{field} {direction}"
        return None

    def _extract_limit(self, q: str) -> str | None:
        """Extract LIMIT clause."""
        m = re.search(r"(?:top|first|last|limit)\s+(\d+)", q)
        if m:
            return m.group(1)
        return None

    def _extract_aggregate(self, q: str) -> str | None:
        """Detect aggregate functions."""
        for kw, agg in self.AGGREGATE_MAP.items():
            if re.search(rf"\b{kw}\b", q):
                if agg in ("COUNT(*)",):
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
        if "per city" in q or "by city" in q:
            return "city"
        if "per department" in q or "by department" in q:
            return "department"
        return None

    def _normalise_field(self, word: str) -> str:
        """Map a potentially noisy word to a clean column name."""
        word = word.lower().strip()
        return self.FIELD_ALIASES.get(word, word)

    def _guess_numeric_field(self, q: str) -> str | None:
        """Pick the most likely numeric column from the query text."""
        for field in self.FIELD_ALIASES:
            if field in q:
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
            logger.warning("OpenAI generation failed: %s. Falling back to rule-based.", exc)

    # Fallback → rule-based
    try:
        sql = _rule_gen.generate(natural_query)
        logger.info("SQL generated via rule-based engine.")
        return {"sql": sql, "method": "rule-based"}
    except Exception as exc:
        logger.error("Rule-based generation failed: %s", exc)
        return {"error": f"SQL generation failed: {exc}"}
