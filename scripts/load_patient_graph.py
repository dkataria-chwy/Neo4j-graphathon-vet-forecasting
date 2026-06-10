"""
Load a patient-graph dump (produced by export_patient_graph.py) into a target
Neo4j instance (Aura or self-hosted).

Target credentials come from TARGET_* env vars (set in .env or shell):
  TARGET_NEO4J_URI=neo4j+s://xxxx.databases.neo4j.io
  TARGET_NEO4J_USERNAME=neo4j
  TARGET_NEO4J_PASSWORD=...
  TARGET_NEO4J_DATABASE=neo4j        (optional, default neo4j)

Safety: refuses to run against the SOURCE instance (NEO4J_URI), and refuses a
non-empty target unless --force is given.

Every loaded node gets an extra `_Imported` label and `_import_id` property
(the source elementId) — used as the MERGE key and for provenance. Remove later
with:  MATCH (n:_Imported) REMOVE n:_Imported, n._import_id

Usage:
  .venv/bin/python scripts/load_patient_graph.py --dir exports/patient_graph
  optional: --create-vector-index   (recreates the 3072-dim cosine index on
            Episode.narrativeEmbedding, named episode_narrative_idx)
"""

import argparse
import gzip
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase
import neo4j.time

load_dotenv()

NODE_BATCH = 500
REL_BATCH = 2000


def decode_value(v):
    if isinstance(v, dict) and "$dt" in v:
        t = v["$dt"]
        if t == "date":
            return neo4j.time.Date.from_iso_format(v["v"])
        if t == "time":
            return neo4j.time.Time.from_iso_format(v["v"])
        if t == "datetime":
            return neo4j.time.DateTime.from_iso_format(v["v"])
        if t == "duration":
            return neo4j.time.Duration(
                months=v["months"], days=v["days"],
                seconds=v["seconds"], nanoseconds=v["nanoseconds"],
            )
        if t == "bytes":
            import base64
            return base64.b64decode(v["v"])
        raise ValueError(f"Unknown tagged type: {t}")
    if isinstance(v, list):
        return [decode_value(x) for x in v]
    return v


def decode_props(props: dict) -> dict:
    return {k: decode_value(v) for k, v in props.items()}


def read_jsonl(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            yield json.loads(line)


def label_fragment(labels):
    return "".join(f":`{l}`" for l in labels)


def load_nodes(driver, db, path: Path) -> int:
    """MERGE nodes grouped by exact label-set (labels must be literal in Cypher)."""
    groups = defaultdict(list)
    total = 0
    for rec in read_jsonl(path):
        groups[tuple(sorted(rec["labels"]))].append(
            {"eid": rec["eid"], "props": decode_props(rec["props"])}
        )
    for labels, rows in groups.items():
        q = (
            "UNWIND $rows AS row "
            "MERGE (n:_Imported {_import_id: row.eid}) "
            "SET n += row.props "
            f"SET n{label_fragment(labels)}"
        )
        for i in range(0, len(rows), NODE_BATCH):
            driver.execute_query(q, rows=rows[i : i + NODE_BATCH], database_=db)
        total += len(rows)
    return total


def load_rels(driver, db, rel_type: str, path: Path) -> int:
    q = (
        "UNWIND $rows AS row "
        "MATCH (a:_Imported {_import_id: row.start}) "
        "MATCH (b:_Imported {_import_id: row.end}) "
        f"CREATE (a)-[r:`{rel_type}`]->(b) "
        "SET r += row.props"
    )
    buf, total = [], 0
    for rec in read_jsonl(path):
        buf.append(
            {"start": rec["start"], "end": rec["end"], "props": decode_props(rec["props"])}
        )
        if len(buf) >= REL_BATCH:
            driver.execute_query(q, rows=buf, database_=db)
            total += len(buf)
            buf = []
    if buf:
        driver.execute_query(q, rows=buf, database_=db)
        total += len(buf)
    return total


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default="exports/patient_graph")
    ap.add_argument("--force", action="store_true", help="allow non-empty target")
    ap.add_argument("--create-vector-index", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.dir)
    manifest = json.loads((out_dir / "manifest.json").read_text())

    uri = os.getenv("TARGET_NEO4J_URI")
    user = os.getenv("TARGET_NEO4J_USERNAME")
    pwd = os.getenv("TARGET_NEO4J_PASSWORD")
    db = os.getenv("TARGET_NEO4J_DATABASE", "neo4j")
    if not (uri and user and pwd):
        sys.exit("Set TARGET_NEO4J_URI / TARGET_NEO4J_USERNAME / TARGET_NEO4J_PASSWORD")
    if uri == os.getenv("NEO4J_URI"):
        sys.exit("Refusing: TARGET_NEO4J_URI equals the SOURCE NEO4J_URI.")

    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    n = driver.execute_query(
        "MATCH (n) RETURN count(n) AS c", database_=db
    ).records[0]["c"]
    if n and not args.force:
        sys.exit(f"Refusing: target already has {n} nodes (use --force to override).")

    driver.execute_query(
        "CREATE CONSTRAINT _import_id_unique IF NOT EXISTS "
        "FOR (x:_Imported) REQUIRE x._import_id IS UNIQUE",
        database_=db,
    )

    print("Loading nodes...", flush=True)
    node_files = sorted((out_dir / "nodes").glob("*.jsonl.gz"))
    for path in node_files:
        t0 = time.time()
        cnt = load_nodes(driver, db, path)
        print(f"  {path.name}: {cnt} ({time.time()-t0:.1f}s)", flush=True)

    print("Loading relationships...", flush=True)
    for path in sorted((out_dir / "rels").glob("*.jsonl.gz")):
        rel_type = path.name.replace(".jsonl.gz", "")
        t0 = time.time()
        cnt = load_rels(driver, db, rel_type, path)
        print(f"  {rel_type}: {cnt} ({time.time()-t0:.1f}s)", flush=True)

    if args.create_vector_index:
        driver.execute_query(
            "CREATE VECTOR INDEX episode_narrative_idx IF NOT EXISTS "
            "FOR (e:Episode) ON e.narrativeEmbedding "
            "OPTIONS {indexConfig: {`vector.dimensions`: 3072, "
            "`vector.similarity_function`: 'cosine'}}",
            database_=db,
        )
        print("Created vector index episode_narrative_idx", flush=True)

    print("\nVerifying against manifest...", flush=True)
    failures = 0
    for label, expected in manifest["nodes"].items():
        lbl = "RefStub" if label == "_ref_stubs" else label
        got = driver.execute_query(
            f"MATCH (n:`{lbl}`) RETURN count(n) AS c", database_=db
        ).records[0]["c"]
        ok = "OK " if got == expected else "MISMATCH"
        if got != expected:
            failures += 1
        print(f"  {ok} {lbl}: {got}/{expected}")
    for rt, expected in manifest["rels"].items():
        got = driver.execute_query(
            f"MATCH ()-[r:`{rt}`]->() RETURN count(r) AS c", database_=db
        ).records[0]["c"]
        ok = "OK " if got == expected else "MISMATCH"
        if got != expected:
            failures += 1
        print(f"  {ok} {rt}: {got}/{expected}")

    driver.close()
    if failures:
        sys.exit(f"{failures} count mismatches — inspect before using the target.")
    print("\nAll counts match the manifest. Load complete.")


if __name__ == "__main__":
    main()
