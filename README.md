# Neo4j Graphathon — Vet Charge-Sheet Forecasting

Forecast a **charge sheet / inventory estimate** for an upcoming vet appointment from its
**presenting complaint**, by walking a patient knowledge graph of what was actually done in
similar past cases — and let a practice manager **"ask why"** to get the traced graph path
that justifies every line.

- **Knowledge graph** = the clinical reasoning + provenance layer (what's done for a
  presentation, and why — traceable to real cases).
- **Inventory & pricing** = a separate data source (CSV / external). The charge sheet is the
  *join* of the two.

The graph is a clinic-scoped copy of **Chewy Vet Care Plantation** (~71k nodes / ~154k rels)
loaded into a Neo4j Aura instance. See `CLAUDE.md` for the full schema, traversal paths, and
the data cleanups applied.

## Setup

```bash
# 1. Python env + tools (Neo4j driver, MCP server, etc.)
python3 -m venv .venv && ./.venv/bin/pip install -U pip
./.venv/bin/pip install neo4j-mcp-server neo4j python-dotenv openai

# 2. Credentials
cp .env.example .env            # fill in NEO4J_* + OPENAI_API_KEY
cp .mcp.json.example .mcp.json  # set the absolute path to .venv/bin/neo4j-mcp-server + creds

# 3. (only if the target DB is empty) load the dump
TARGET_NEO4J_URI=...  TARGET_NEO4J_USERNAME=neo4j  TARGET_NEO4J_PASSWORD=... \
  ./.venv/bin/python scripts/load_patient_graph.py --dir data/patient_graph --create-vector-index
```

`.env`, `.mcp.json`, and `data/` are gitignored (secrets + derived clinical data — never committed).

## What's here
- `.mcp.json` — Neo4j MCP server config (tools: get-schema / read-cypher / write-cypher).
- `.claude/skills/` — vendored Neo4j agent skills (Cypher, GraphRAG, vector index, modeling…).
- `scripts/load_patient_graph.py` — load the dump into a Neo4j instance (count-verified).
- `scripts/export_patient_graph.py` — how the dump was produced (reads the source KG).
- `data/` — the dump (`patient_graph/` + tarball), local only.
- `CLAUDE.md` — project brief + KG schema + the canonical traversal query + forecast hygiene.
