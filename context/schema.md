# KG Schema Context — Vet Charge-Sheet Forecasting

Curated semantic reference for writing correct queries against the graphathon-team-1
patient graph. `get-schema` gives raw structure; THIS file gives the meaning and the
gotchas. Inject this into any agent/LLM prompt that touches the graph.

DB: `neo4j+s://90596fbe.databases.neo4j.io` (graphathon-team-1). One clinic (Chewy Vet
Care Plantation). ~71k nodes / 154k rels. Patient layer only — reference/textbook layer is
reduced to name-only `RefStub` tags.

## The spine — how a visit is recorded
An **Episode** is a *case* (often multi-day). Everything clinical hangs off the **sign** —
there is NO direct Episode→medication/lab edge.

```
Patient ─HAD_EPISODE→ Episode ─HAD_SIGN→ ClinicalSignOccurrence      ← only door into a case
                                  ├─HAD_DIAGNOSTIC_TEST→  DiagnosticTestOccurrence   (LABS)
                                  ├─HAD_IMAGING→          ImagingOccurrence
                                  ├─HAD_DIAGNOSTIC_PROCEDURE→ DiagnosticProcedureOccurrence
                                  └─HAD_DIAGNOSIS→ DiagnosisOccurrence
                                        ├─HAD_TREATMENT_MEDICATION→ MedicationOccurrence (MEDS, incl. vaccines)
                                        ├─HAD_TREATMENT_PROCEDURE→ TreatmentProcedureOccurrence
                                        │      └─PROC_GAVE_MEDICATION→ MedicationOccurrence (anesthesia/sedation)
                                        ├─HAD_OUTCOME→ OutcomeOccurrence
                                        └─SUPPORTED_BY_TEST/_IMAGING/_PROCEDURE (evidence back-links)
   (labs/imaging/dx-procedures can also ─TEST_GAVE_MEDICATION→ MedicationOccurrence)
```
- **Diagnostics attach to the SIGN; treatments/outcomes attach to the DIAGNOSIS.**
- Every `*Occurrence` →`INSTANCE_OF`→ a canonical **`RefStub`** tag. Aggregate by RefStub
  (brand "Vetoryl" and "trilostane" collapse to one), never by raw occurrence name.
- Conditions = `DiagnosisOccurrence` (event) → `Condition`/`RefStub` (canonical). No `ConditionOccurrence`.

## Key properties
- **Patient**: `patient_id`, `name`, `species` (`canine`|`feline` only), `life_stage`
  (`Puppy`/`Kitten`, `Young Adult`, `Mature Adult`, `Senior`), `breed` (+ `IS_OF_BREED`→Breed,
  `IS_OF_SPECIES`→Species), `date_of_birth`, `weight`, `sex`, `neuter_status`.
- **Episode**: `id`, `episode_title`, `narrative`, `narrativeEmbedding` (3072-dim),
  `start_date`/`end_date` (strings).
- **MedicationOccurrence**: `name`, `dose`, `route`, `frequency`, `duration_days`,
  `indication_type`, `timestamp`. `ClinicalSignOccurrence`/`DiagnosisOccurrence`/etc.: `name`,
  `timestamp`; DxOcc adds `diagnosis_status`; OutcomeOcc adds `status`.
- **Appointment** (added for this project): `appointment_id`, `scheduled_date` (date),
  `presenting_complaint`, `species`, `life_stage`, `status`. `(:Patient)-[:HAS_APPOINTMENT]->(:Appointment)`.

## Query gotchas (these cause WRONG results, not errors)
1. **`WITH DISTINCT` after every fan-out hop** — Episode→CSO and CSO→DxOcc both fan out;
   without it, counts inflate Cartesian-style. Use `count(DISTINCT e)` in aggregates.
2. **`MedicationOccurrence.indication_type`** — `therapeutic`/`treatment` = real Rx;
   `procedural` = anesthesia/sedation. Filter, or anesthesia tops your "meds" list.
3. **`DiagnosisOccurrence.diagnosis_status`** — `diagnosed` vs `suspected`/`unknown`/`not_diagnosed`.
4. **Match complaints on Sign tags, not the narrative** — the narrative already names the
   diagnosis+treatment (leakage). Narrative-vector search is a *secondary* signal only.
5. **Cohort filter**: hard-filter `species`; treat `life_stage` as a *soft preference*
   (rank same-stage first, fall back to species-only if below the noise floor).
6. **Noise floor**: only surface a service seen in ≥N similar cases (drop one-offs).

## Vector index
`episode_narrative_idx` — `Episode.narrativeEmbedding`, 3072-dim cosine
(text-embedding-3-large). `CALL db.index.vector.queryNodes('episode_narrative_idx', $k, $vec)`.

## Golden queries

### A. Similar episodes by sign + species + life_stage (the retrieval core)
```cypher
// $signIds = elementIds of resolved Sign/ClinicalSign RefStubs; $species, $lifeStage, $k
MATCH (tag) WHERE elementId(tag) IN $signIds
MATCH (tag)<-[:INSTANCE_OF]-(:ClinicalSignOccurrence)<-[:HAD_SIGN]-(e:Episode)<-[:HAD_EPISODE]-(p:Patient)
WHERE p.species = $species
WITH e, p, count(DISTINCT tag) AS sign_overlap
RETURN elementId(e) AS episode_id, e.episode_title AS title,
       sign_overlap, (p.life_stage = $lifeStage) AS same_stage
ORDER BY same_stage DESC, sign_overlap DESC
LIMIT $k
```

### B. Aggregate what was done across a set of episodes (services + frequencies)
```cypher
// $episodeIds = elementIds from query A
MATCH (e:Episode) WHERE elementId(e) IN $episodeIds
MATCH (e)-[:HAD_SIGN|HAD_DIAGNOSIS|HAD_DIAGNOSTIC_TEST|HAD_TREATMENT_MEDICATION|HAD_IMAGING|
          HAD_TREATMENT_PROCEDURE|HAD_DIAGNOSTIC_PROCEDURE|PROC_GAVE_MEDICATION|TEST_GAVE_MEDICATION*1..6]->(o)
WHERE o:MedicationOccurrence OR o:DiagnosticTestOccurrence OR o:ImagingOccurrence
   OR o:TreatmentProcedureOccurrence OR o:DiagnosticProcedureOccurrence
WITH e, o,
     CASE WHEN o:MedicationOccurrence AND coalesce(o.indication_type,'') IN ['procedural','procedure']
          THEN true ELSE false END AS is_anesthesia
WHERE NOT is_anesthesia
OPTIONAL MATCH (o)-[:INSTANCE_OF]->(svc:RefStub)
WITH [l IN labels(o) WHERE l ENDS WITH 'Occurrence'][0] AS category,
     coalesce(svc.name, o.name) AS service,
     count(DISTINCT e) AS used_in_cases
WHERE used_in_cases >= $noiseFloor
RETURN category, service, used_in_cases
ORDER BY used_in_cases DESC
```
`used_in_cases / total_similar = % of similar cases` → "most/least/common prescribed."
Keep the matched episode_ids per service for provenance ("why").

### C. Provenance for one service line (the "ask why")
```cypher
// $service, $episodeIds → the actual cases that justify the line
MATCH (e:Episode) WHERE elementId(e) IN $episodeIds
MATCH (e)-[:HAD_SIGN|HAD_DIAGNOSIS|HAD_TREATMENT_MEDICATION|HAD_DIAGNOSTIC_TEST|HAD_IMAGING|
          HAD_TREATMENT_PROCEDURE|HAD_DIAGNOSTIC_PROCEDURE|PROC_GAVE_MEDICATION|TEST_GAVE_MEDICATION*1..6]->(o)
OPTIONAL MATCH (o)-[:INSTANCE_OF]->(svc:RefStub)
WITH e, coalesce(svc.name, o.name) AS service WHERE service = $service
RETURN DISTINCT e.id AS episode_id, e.episode_title AS title
```
