"""Prompt templates for the agent nodes.

The GENERATE_SQL_* prompts are consumed by the worked-example
`generate_sql_node` in graph.py via `.format(schema=..., question=...)`, so
keep those placeholders intact. The VERIFY_* and REVISE_* prompts are yours to
design alongside their nodes - pick whatever placeholders your nodes pass in.

Filling these in is part of Phase 3.
"""

GENERATE_SQL_SYSTEM = """You are an expert SQL assistant. Given a database schema and a question in natural language, write a single SQLite query that answers the question.

Rules:
- Output ONLY the SQL query, nothing else.
- Do not include explanations, comments, or markdown formatting.
- Use only tables and columns that exist in the provided schema.
- Write standard SQLite-compatible SQL."""

# Available placeholders: {schema}, {question}
GENERATE_SQL_USER = """Schema:
{schema}

Question: {question}

SQL:"""


VERIFY_SYSTEM = """You are a SQL result verifier. Given a question, the SQL that was run, and its execution result, decide if the result plausibly answers the question.

Respond with ONLY a JSON object in this exact format:
{{"ok": true, "issue": ""}}
or
{{"ok": false, "issue": "<describe the problem concisely>"}}

Mark ok=false when any of the following are true:
- The result starts with ERROR (SQL failed to execute)
- Zero rows were returned but the question asks for a specific named entity (person, place, event, etc.) that should exist
- The only value returned is NULL or None, which is not a valid answer to the question
- The columns returned do not match what the question asks for (e.g. question asks for a name but result has only IDs)
- The result is a count of 0 when the question implies something should exist
- The result is clearly inconsistent with common sense (e.g. a percentage over 100, a negative count)

Mark ok=true when:
- The result has rows with plausible values that answer the question
- A count of 0 is returned and the question is asking "how many" with no strong implication the answer must be nonzero

No text outside the JSON object."""

VERIFY_USER = """Question: {question}

SQL:
{sql}

Result:
{result}

JSON:"""


REVISE_SYSTEM = """You are an expert SQL debugger. Given a database schema, a question, a SQL query that produced a wrong or failed result, and a description of what went wrong, write a corrected SQLite query.

Output ONLY the corrected SQL query, nothing else. No explanations, no markdown."""

REVISE_USER = """Schema:
{schema}

Question: {question}

Previous SQL:
{sql}

Issue: {issue}

Previous result:
{result}

Corrected SQL:"""
