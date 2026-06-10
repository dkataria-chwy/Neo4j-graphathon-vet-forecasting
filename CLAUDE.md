# Neo4j Graphathon — Vet Charge-Sheet Forecasting

## What this is
Given a **future scheduled appointment + its presenting complaint**, walk a veterinary
patient knowledge graph of *what was actually done in similar past cases* (meds, labs,
imaging, procedures, outcomes), and forecast a **charge sheet / inventory estimate** for
the upcoming visit. The differentiator over a spreadsheet or vector DB: a practice
manager can **"ask why"** about any line and get the *traced graph path* back to the real
historical cases that justify it.

- **KG = clinical brain + provenance** (what's done for a presentation, and why, traceable).
- **Inventory + pricing = a SEPARATE data source** (CSV / external) — deliberately NOT in
  the graph. Stock and prices are volatile/operational; the graph stays the reasoning layer.
  The charge sheet is the *join* of "KG says these services" × "inventory source says price/stock".

## ⚠️ Hard rule — database scope
This project connects ONLY to the **graphathon-team-1** Aura instance
(`neo4j+s://90596fbe.databases.neo4j.io`, instance id `90596fbe`). It is a clinic-scoped
*copy*. **Never point this project at the main/source KG.** All reads and writes target
graphathon-team-1.

## The knowledge graph (what's loaded)
Clinic-scoped export of **Chewy Vet Care Plantation** (the data-richest of 20 clinics):
~71k nodes / ~154k relationships, including episode narratives + 3072-dim embeddings.
No textbook/reference content — only what happened at the clinic, plus canonical name tags.

**Cleanups already applied to this instance (intentional divergence from source):**
- Strictly **one clinic** (sister-clinic `IN_CLINIC` tags removed).
- **`updated_by` removed** from all nodes + rels (held internal usernames).
- **species** normalized to exactly two values: `canine` / `feline` (Patient.species, the
  Species nodes' name/name_norm). Derived from `IS_OF_SPECIES`, not guessed.
- **`life_stage`** added to every Patient (species-specific AAHA/AAFP bands, snapshot as of
  2026-06-10): canine Puppy<1 / Young Adult 1–3 / Mature Adult 3–7 / Senior 7+;
  feline Kitten<1 / Young Adult 1–7 / Mature Adult 7–10 / Senior 10+.
- **`patient_size` removed** (sparse, no relationship behind it).
- Loader bookkeeping: every node carries `_Imported` label + `_import_id` (= source elementId).

### Graph shape — the occurrence-chain spine
An **Episode** is a *case* (often multi-visit: ~45% span >1 day). Everything clinical hangs
off the sign chain — there is NO direct Episode→medication edge:

```
Patient ─HAD_EPISODE→ Episode ─HAD_SIGN→ ClinicalSignOccurrence   ← the only door in
                                  ├─HAD_DIAGNOSTIC_TEST→  DiagnosticTestOccurrence   (LABS)
                                  ├─HAD_IMAGING→          ImagingOccurrence
                                  ├─HAD_DIAGNOSTIC_PROCEDURE→ DiagnosticProcedureOccurrence
                                  └─HAD_DIAGNOSIS→ DiagnosisOccurrence
                                        ├─HAD_TREATMENT_MEDICATION→ MedicationOccurrence  (MEDS, incl. vaccines)
                                        ├─HAD_TREATMENT_PROCEDURE→ TreatmentProcedureOccurrence
                                        │      └─PROC_GAVE_MEDICATION→ MedicationOccurrence (anesthesia/sedation)
                                        ├─HAD_OUTCOME→ OutcomeOccurrence
                                        └─SUPPORTED_BY_TEST/_IMAGING/_PROCEDURE (evidence back-links)
   (labs/imaging/dx-procedures can also ─TEST_GAVE_MEDICATION→ MedicationOccurrence)
```
- Diagnostics attach to the **sign**; treatments/outcomes attach to the **diagnosis**.
- Each `*Occurrence` points `INSTANCE_OF` → a canonical **`RefStub`** name tag (e.g. brand
  "Vetoryl" → "trilostane"). Aggregate by RefStub, not raw occurrence names.
- Conditions = `DiagnosisOccurrence` (event) → `Condition`/`RefStub` (canonical). There is
  no `ConditionOccurrence`.

**The one canonical "everything in an episode" traversal:**
```cypher
MATCH (e:Episode {id:$episodeId})
  -[:HAD_SIGN|HAD_DIAGNOSIS|HAD_DIAGNOSTIC_TEST|HAD_TREATMENT_MEDICATION|HAD_IMAGING|
    HAD_TREATMENT_PROCEDURE|HAD_DIAGNOSTIC_PROCEDURE|HAD_OUTCOME|SUPPORTED_BY_TEST|
    SUPPORTED_BY_PROCEDURE|SUPPORTED_BY_IMAGING|PROC_GAVE_MEDICATION|TEST_GAVE_MEDICATION*1..6]->(o)
WITH DISTINCT o
OPTIONAL MATCH (o)-[:INSTANCE_OF]->(tag:RefStub)
RETURN [l IN labels(o) WHERE l ENDS WITH 'Occurrence'][0] AS kind,
       coalesce(tag.name, o.name) AS item
```
(verified to reach 100% of event nodes)

### Aggregation hygiene (for the forecast query)
- Match the complaint against **`Sign` tags** (recorded at presentation), not the full
  narrative (the narrative leaks the diagnosis/treatment).
- Cohort filter by **species** (canine/feline) — and optionally `life_stage`.
- **Noise floor:** only surface a service seen in ≥N similar cases.
- `MedicationOccurrence.indication_type`: `therapeutic`/`treatment` = real Rx; exclude
  `procedural` (anesthesia) unless asked.
- `DiagnosisOccurrence.diagnosis_status`: `diagnosed` vs `suspected`.
- Decide what the sheet estimates: **whole episode** (case end-to-end) vs **day-1 only**
  (`o.timestamp = e.start_date`, ~78% of events). Default: whole episode = "expected case estimate".

### Semantic search
`episode_narrative_idx` — vector index on `Episode.narrativeEmbedding` (3072-dim cosine,
text-embedding-3-large). Use for fuzzy "find visits like this" as a secondary signal.

## Tooling in this repo
- **Neo4j MCP server** (`.mcp.json`, v1.5.2) → tools `get-schema`, `read-cypher`,
  `write-cypher`, `list-gds-procedures`. Points at graphathon-team-1.
- **Vendored skills** (`.claude/skills/`): cypher, mcp, graphrag, vector-index, modeling,
  python-driver, query-tuning, cli-tools. Read-on-demand.
- **`.venv/`** — Python env (neo4j driver, python-dotenv, openai, the MCP server).
- **`data/`** — the loaded dump + tarball (gitignored). Reload with
  `scripts/load_patient_graph.py` (uses `TARGET_NEO4J_*` env vars; refuses a non-empty target).
- **`scripts/export_patient_graph.py`** — provenance of how the dump was made (reads the
  SOURCE KG; not used in normal graphathon flow).

## Stack
TBD — pick when the build starts. Leaning: Python (Neo4j driver) backend + a quick demo UI
(Streamlit or minimal web) so the "ask why → trace path" view is the centerpiece.
