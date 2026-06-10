"""
Export the patient/clinical layer of the Neo4j KG to a portable JSONL dump.

Includes (label whitelist):
  - Clinical spine: Patient, Episode, all *Occurrence labels
  - Ops layer: Client, Veterinarian, VetClinic, City, State
  - Taxonomy targets: Breed, Species
  - INSTANCE_OF bridge edges + name-only stubs of their reference-layer targets

Excludes: all textbook/reference content (Condition descriptions, HAS_SYMPTOM
probabilities, treatments, etc.) — stubs carry name + labels only.

Sampling mode (--patients N): exports only the N "richest" patients
(most episodes + recorded events), breed-stratified — every breed/mix
combination gets its richest patient before any breed gets a second slot
(round-robin). The full subgraph of each selected patient is included.

Output: exports/patient_graph/
  nodes/<Label>.jsonl.gz            {"eid", "labels", "props"}
  nodes/_ref_stubs.jsonl.gz         name-only reference targets (+RefStub label)
  rels/<TYPE>.jsonl.gz              {"start", "end", "props"}
  manifest.json                     counts for load-time verification
  sampled_patients.json             (sampling mode) selection + scores

Usage (from repo root):
  .venv/bin/python scripts/export_patient_graph.py                 # full layer
  .venv/bin/python scripts/export_patient_graph.py --patients 2000 # sampled
"""

import argparse
import gzip
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp_client import get_client  # noqa: E402

import neo4j.time  # noqa: E402

# ---------------------------------------------------------------- whitelist

FULL_LABELS = [
    # clinical spine
    "Patient",
    "Episode",
    "ClinicalSignOccurrence",
    "MedicationOccurrence",
    "DiagnosticTestOccurrence",
    "DiagnosisOccurrence",
    "TreatmentProcedureOccurrence",
    "OutcomeOccurrence",
    "ImagingOccurrence",
    "DiagnosticProcedureOccurrence",
    # ops layer
    "Client",
    "Veterinarian",
    "VetClinic",
    "City",
    "State",
    # taxonomy targets of IS_OF_BREED / IS_OF_SPECIES
    "Breed",
    "Species",
]

# Universal superlabels — kept on full nodes (faithful copy), stripped on stubs.
SUPER_LABELS = {"Entity", "Embedded"}

# Edges that hang occurrence chains off an Episode (for subgraph traversal).
OCC_RELS = (
    "HAD_SIGN|HAD_DIAGNOSIS|HAD_DIAGNOSTIC_TEST|HAD_TREATMENT_MEDICATION"
    "|HAD_IMAGING|HAD_TREATMENT_PROCEDURE|HAD_DIAGNOSTIC_PROCEDURE|HAD_OUTCOME"
    "|SUPPORTED_BY_TEST|SUPPORTED_BY_PROCEDURE|SUPPORTED_BY_IMAGING"
    "|PROC_GAVE_MEDICATION|TEST_GAVE_MEDICATION"
)

NODE_PROP_BATCH_DEFAULT = 2000
NODE_PROP_BATCH = {"Episode": 100}  # 3072-dim narrativeEmbedding per node
REL_BATCH = 5000
EID_BATCH = 500


# ------------------------------------------------------------- serialization

def encode_value(v):
    """Convert neo4j driver types to JSON-safe tagged values (lossless)."""
    if isinstance(v, neo4j.time.DateTime):
        return {"$dt": "datetime", "v": v.iso_format()}
    if isinstance(v, neo4j.time.Date):
        return {"$dt": "date", "v": v.iso_format()}
    if isinstance(v, neo4j.time.Time):
        return {"$dt": "time", "v": v.iso_format()}
    if isinstance(v, neo4j.time.Duration):
        return {
            "$dt": "duration",
            "months": v.months,
            "days": v.days,
            "seconds": v.seconds,
            "nanoseconds": v.nanoseconds,
        }
    if isinstance(v, bytes):
        import base64
        return {"$dt": "bytes", "v": base64.b64encode(v).decode("ascii")}
    if isinstance(v, list):
        return [encode_value(x) for x in v]
    if type(v).__module__.startswith("neo4j.spatial"):
        raise NotImplementedError(f"Spatial point export not supported: {v!r}")
    return v


def encode_props(props: dict) -> dict:
    return {k: encode_value(v) for k, v in props.items()}


def chunks(seq, size):
    seq = list(seq)
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


# ----------------------------------------------------------------- sampling

def select_patients(c, n: int) -> list[dict]:
    """Pick the n richest patients, breed-stratified round-robin."""
    all_pids = [r["eid"] for r in c.execute_cypher(
        "MATCH (p:Patient) RETURN elementId(p) AS eid"
    )]
    print(f"  scoring {len(all_pids)} patients...", flush=True)

    scored = {}
    for batch in chunks(all_pids, 250):
        rows = c.execute_cypher(
            "MATCH (p:Patient) WHERE elementId(p) IN $b "
            "OPTIONAL MATCH (p)-[:HAD_EPISODE|HAS_EPISODE]->(e:Episode) "
            f"OPTIONAL MATCH (e)-[:{OCC_RELS}*1..6]->(o) "
            "RETURN elementId(p) AS eid, count(DISTINCT e) AS eps, "
            "count(DISTINCT o) AS occs",
            {"b": batch},
        )
        for r in rows:
            scored[r["eid"]] = {
                "eid": r["eid"],
                "episodes": r["eps"],
                "events": r["occs"],
                "richness": r["eps"] + r["occs"],
            }
    for batch in chunks(all_pids, 1000):
        rows = c.execute_cypher(
            "MATCH (p:Patient) WHERE elementId(p) IN $b "
            "OPTIONAL MATCH (p)-[:IS_OF_BREED]->(b2:Breed) "
            "RETURN elementId(p) AS eid, p.name AS name, "
            "collect(DISTINCT b2.name) AS breeds",
            {"b": batch},
        )
        for r in rows:
            scored[r["eid"]]["name"] = r["name"]
            scored[r["eid"]]["breeds"] = sorted(b for b in r["breeds"] if b)

    # Bucket by breed combination; round-robin richest-first across buckets.
    buckets = defaultdict(list)
    for p in scored.values():
        buckets["|".join(p["breeds"]) or "(no breed)"].append(p)
    for v in buckets.values():
        v.sort(key=lambda p: -p["richness"])

    selected = []
    while len(selected) < n:
        live = [k for k in buckets if buckets[k]]
        if not live:
            break
        for k in sorted(live, key=lambda k: -buckets[k][0]["richness"]):
            selected.append(buckets[k].pop(0))
            if len(selected) == n:
                break
    print(
        f"  selected {len(selected)} patients across "
        f"{len({'|'.join(p['breeds']) for p in selected})} breed combos",
        flush=True,
    )
    return selected


def build_included_set(
    c,
    patient_eids: list[str],
    episode_eids: list[str] | None = None,
    clinic_eid: str | None = None,
) -> dict[str, set]:
    """Compute eids of every node in the selected patients' subgraphs.

    If episode_eids is given (clinic mode), the episode set is fixed to it —
    patients' episodes at OTHER clinics are deliberately excluded.
    If clinic_eid is given, ONLY that VetClinic node is included: source data
    sometimes tags one episode with several sister clinics, and a clinic-scoped
    export should not drag those along (their IN_CLINIC edges are then dropped
    by the endpoint filter in export_rels).
    """
    inc = {label: set() for label in FULL_LABELS}
    inc["Patient"] = set(patient_eids)

    def collect(query, batch_src, batch_size=EID_BATCH):
        out = []
        for batch in chunks(batch_src, batch_size):
            out.extend(c.execute_cypher(query, {"b": batch}))
        return out

    if episode_eids is not None:
        inc["Episode"] = set(episode_eids)
    else:
        for r in collect(
            "MATCH (p) WHERE elementId(p) IN $b "
            "MATCH (p)-[:HAD_EPISODE|HAS_EPISODE]->(e:Episode) "
            "RETURN DISTINCT elementId(e) AS eid",
            patient_eids, batch_size=1000,
        ):
            inc["Episode"].add(r["eid"])

    ep_eids = list(inc["Episode"])
    for r in collect(
        "MATCH (e) WHERE elementId(e) IN $b "
        f"MATCH (e)-[:{OCC_RELS}*1..6]->(o) "
        "RETURN DISTINCT elementId(o) AS eid, "
        "[l IN labels(o) WHERE NOT l IN ['Entity','Embedded']][0] AS lab",
        ep_eids,
    ):
        if r["lab"] in inc:
            inc[r["lab"]].add(r["eid"])

    if clinic_eid is not None:
        inc["VetClinic"] = {clinic_eid}
        clinic_collects = []
    else:
        clinic_collects = [("IN_CLINIC", "VetClinic", ep_eids)]

    for rel, lab, src in [
        ("SEEN_BY", "Veterinarian", ep_eids),
        *clinic_collects,
        ("IS_OF_BREED", "Breed", patient_eids),
        ("IS_OF_SPECIES", "Species", patient_eids),
    ]:
        for r in collect(
            f"MATCH (x) WHERE elementId(x) IN $b MATCH (x)-[:{rel}]->(t:`{lab}`) "
            "RETURN DISTINCT elementId(t) AS eid",
            src, batch_size=1000,
        ):
            inc[lab].add(r["eid"])

    for r in collect(
        "MATCH (p) WHERE elementId(p) IN $b "
        "MATCH (cl:Client)-[:OWNS]->(p) RETURN DISTINCT elementId(cl) AS eid",
        patient_eids, batch_size=1000,
    ):
        inc["Client"].add(r["eid"])
    for r in collect(
        "MATCH (cl) WHERE elementId(cl) IN $b "
        "MATCH (cl)-[:IN_CITY]->(ct:City) RETURN DISTINCT elementId(ct) AS eid",
        list(inc["Client"]), batch_size=1000,
    ):
        inc["City"].add(r["eid"])
    for r in collect(
        "MATCH (ct) WHERE elementId(ct) IN $b "
        "MATCH (ct)-[:IN_STATE]->(s:State) RETURN DISTINCT elementId(s) AS eid",
        list(inc["City"]), batch_size=1000,
    ):
        inc["State"].add(r["eid"])

    return inc


# ------------------------------------------------------------------- export

def export_nodes(c, out_dir: Path, manifest: dict, included: dict | None) -> set:
    """Export full nodes per whitelisted label. Returns set of exported eids."""
    nodes_dir = out_dir / "nodes"
    nodes_dir.mkdir(parents=True, exist_ok=True)
    exported = set()
    manifest["nodes"] = {}

    for label in FULL_LABELS:
        t0 = time.time()
        if included is None:
            eids = [
                r["eid"]
                for r in c.execute_cypher(
                    f"MATCH (n:`{label}`) RETURN elementId(n) AS eid"
                )
            ]
        else:
            eids = sorted(included[label])
        batch = NODE_PROP_BATCH.get(label, NODE_PROP_BATCH_DEFAULT)
        path = nodes_dir / f"{label}.jsonl.gz"
        written = 0
        with gzip.open(path, "wt", encoding="utf-8") as f:
            for chunk in chunks(eids, batch):
                rows = c.execute_cypher(
                    "MATCH (n) WHERE elementId(n) IN $eids "
                    "RETURN elementId(n) AS eid, labels(n) AS labels, properties(n) AS props",
                    {"eids": chunk},
                )
                for r in rows:
                    if r["eid"] in exported:
                        continue
                    exported.add(r["eid"])
                    f.write(
                        json.dumps(
                            {
                                "eid": r["eid"],
                                "labels": r["labels"],
                                "props": encode_props(r["props"]),
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    written += 1
        manifest["nodes"][label] = written
        print(f"  nodes/{label}: {written} ({time.time()-t0:.1f}s)", flush=True)

    return exported


def export_rels(c, out_dir: Path, manifest: dict, included_eids: set | None) -> set:
    """Export every rel type whose endpoints are both whitelisted (and, in
    sampling mode, both inside the included subgraph). INSTANCE_OF keeps any
    target — their distinct end eids are returned for stub export."""
    rels_dir = out_dir / "rels"
    rels_dir.mkdir(parents=True, exist_ok=True)
    manifest["rels"] = {}
    manifest["rels_skipped_empty"] = []
    stub_targets = set()

    rel_types = [
        r["relationshipType"] for r in c.execute_cypher("CALL db.relationshipTypes()")
    ]

    for rt in sorted(rel_types):
        bridge = rt == "INSTANCE_OF"
        if bridge:
            where = "any(l IN labels(a) WHERE l IN $wl)"
        else:
            where = (
                "any(l IN labels(a) WHERE l IN $wl) "
                "AND any(l IN labels(b) WHERE l IN $wl)"
            )
        t0 = time.time()
        path = rels_dir / f"{rt}.jsonl.gz"
        written = 0
        skip = 0
        f = None
        try:
            while True:
                rows = c.execute_cypher(
                    f"MATCH (a)-[r:`{rt}`]->(b) WHERE {where} "
                    "RETURN elementId(a) AS start, elementId(b) AS end, "
                    "properties(r) AS props "
                    "ORDER BY elementId(r) SKIP $skip LIMIT $limit",
                    {"wl": FULL_LABELS, "skip": skip, "limit": REL_BATCH},
                )
                if not rows:
                    break
                for r in rows:
                    if included_eids is not None:
                        if r["start"] not in included_eids:
                            continue
                        if not bridge and r["end"] not in included_eids:
                            continue
                    if bridge:
                        stub_targets.add(r["end"])
                    if f is None:
                        f = gzip.open(path, "wt", encoding="utf-8")
                    f.write(
                        json.dumps(
                            {
                                "start": r["start"],
                                "end": r["end"],
                                "props": encode_props(r["props"]),
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    written += 1
                skip += REL_BATCH
        finally:
            if f is not None:
                f.close()
        if written:
            manifest["rels"][rt] = written
            print(f"  rels/{rt}: {written} ({time.time()-t0:.1f}s)", flush=True)
        else:
            manifest["rels_skipped_empty"].append(rt)

    return stub_targets


def export_ref_stubs(c, out_dir: Path, stub_eids: set, full_eids: set, manifest: dict):
    """Name-only stubs for INSTANCE_OF targets not already exported as full nodes."""
    path = out_dir / "nodes" / "_ref_stubs.jsonl.gz"
    t0 = time.time()
    written = 0
    eids = sorted(stub_eids - full_eids)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for chunk in chunks(eids, NODE_PROP_BATCH_DEFAULT):
            rows = c.execute_cypher(
                "MATCH (b) WHERE elementId(b) IN $eids "
                "RETURN elementId(b) AS eid, labels(b) AS labels, "
                "b.name AS name, b.id AS ref_id",
                {"eids": chunk},
            )
            for r in rows:
                labels = [l for l in r["labels"] if l not in SUPER_LABELS]
                props = {"name": r["name"]}
                if r["ref_id"] is not None:
                    props["id"] = r["ref_id"]
                f.write(
                    json.dumps(
                        {
                            "eid": r["eid"],
                            "labels": labels + ["RefStub"],
                            "props": encode_props(props),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                written += 1
    manifest["nodes"]["_ref_stubs"] = written
    print(f"  nodes/_ref_stubs: {written} ({time.time()-t0:.1f}s)", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="exports/patient_graph")
    ap.add_argument(
        "--patients", type=int, default=None,
        help="sample the N richest patients (breed-stratified); default = all",
    )
    ap.add_argument(
        "--clinic", default=None,
        help="export only episodes at the clinic matching this name substring "
        "(case-insensitive), e.g. 'Plantation'. Overrides --patients.",
    )
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir.parent / ".gitignore").write_text("*\n")

    c = get_client()
    manifest = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "whitelist": FULL_LABELS,
        "bridge": "INSTANCE_OF + RefStub name-only targets",
        "embeddings": "included (Episode.narrativeEmbedding et al.)",
    }

    included = None
    if args.clinic:
        matches = c.execute_cypher(
            "MATCH (vc:VetClinic) WHERE toLower(vc.name) CONTAINS toLower($q) "
            "RETURN elementId(vc) AS eid, vc.name AS name",
            {"q": args.clinic},
        )
        if len(matches) != 1:
            sys.exit(
                f"--clinic '{args.clinic}' matched {len(matches)} clinics: "
                f"{[m['name'] for m in matches]}"
            )
        vc_eid, vc_name = matches[0]["eid"], matches[0]["name"]
        print(f"Scoping to clinic: {vc_name}", flush=True)
        episode_eids = [
            r["eid"]
            for r in c.execute_cypher(
                "MATCH (e:Episode)-[:IN_CLINIC]->(vc) WHERE elementId(vc) = $id "
                "RETURN DISTINCT elementId(e) AS eid",
                {"id": vc_eid},
            )
        ]
        patient_eids = []
        for batch in chunks(episode_eids, 1000):
            patient_eids.extend(
                r["eid"]
                for r in c.execute_cypher(
                    "MATCH (p:Patient)-[:HAD_EPISODE|HAS_EPISODE]->(e) "
                    "WHERE elementId(e) IN $b RETURN DISTINCT elementId(p) AS eid",
                    {"b": batch},
                )
            )
        patient_eids = list(set(patient_eids))
        print(
            f"  {len(episode_eids)} episodes, {len(patient_eids)} patients",
            flush=True,
        )
        print("Building included subgraph eid set...", flush=True)
        included = build_included_set(
            c, patient_eids, episode_eids=episode_eids, clinic_eid=vc_eid
        )
        manifest["sampling"] = {
            "clinic": vc_name,
            "strategy": "all episodes at this clinic (other-clinic visits and "
            "sister-clinic IN_CLINIC tags excluded)",
            "episodes": len(episode_eids),
            "patients": len(patient_eids),
            "subgraph_nodes": {k: len(v) for k, v in included.items()},
        }
    elif args.patients:
        print(f"Sampling {args.patients} patients (breed-stratified richest)...",
              flush=True)
        selected = select_patients(c, args.patients)
        (out_dir / "sampled_patients.json").write_text(
            json.dumps(selected, indent=2, ensure_ascii=False)
        )
        print("Building included subgraph eid set...", flush=True)
        included = build_included_set(c, [p["eid"] for p in selected])
        manifest["sampling"] = {
            "patients": len(selected),
            "strategy": "breed-stratified round-robin, richest first",
            "breed_combos": len({"|".join(p["breeds"]) for p in selected}),
            "subgraph_nodes": {k: len(v) for k, v in included.items()},
        }

    print("Exporting nodes...", flush=True)
    included_eids = set().union(*included.values()) if included else None
    full_eids = export_nodes(c, out_dir, manifest, included)

    print("Exporting relationships...", flush=True)
    stub_targets = export_rels(c, out_dir, manifest, included_eids)

    print("Exporting reference stubs (INSTANCE_OF targets)...", flush=True)
    export_ref_stubs(c, out_dir, stub_targets, full_eids, manifest)

    manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
    manifest["totals"] = {
        "nodes": sum(manifest["nodes"].values()),
        "rels": sum(manifest["rels"].values()),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(
        f"\nDone. {manifest['totals']['nodes']} nodes, "
        f"{manifest['totals']['rels']} rels -> {out_dir}",
        flush=True,
    )


if __name__ == "__main__":
    main()
