"""
Forecast charge sheets + 4-week inventory demand for the seeded FUTURE appointments.

Per future appointment:
  1. embed its chief_complaint (text-embedding-3-large)
  2. vector-search similar HISTORICAL appointments (same species, prefer same life_stage,
     must have an invoice) via appointment_complaint_idx
  3. pull those neighbors' invoice line items (real prices + quantities)
  4. aggregate -> per-item prevalence, expected units, expected cost
  5. materialize (:Appointment)-[:EVIDENCED_BY]->(:Appointment) for the "ask why" trail

Then roll the per-item expected units up across all future appointments -> the 4-week
inventory demand (filtered to INVENTORY + PRESCRIPTION = the stockable goods).

NO diagnosis, NO episode traversal: we match complaint->complaint and read the invoice.
One appointment = one invoice = one visit, so no whole-episode inflation.

Usage:  ./.venv/bin/python scripts/generate_forecast.py [--k 30] [--out out/forecasts.json]
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
MODEL = os.getenv("embedding_model", "text-embedding-3-large")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--k", type=int, default=30, help="neighbors per appointment")
    ap.add_argument("--out", default="out/forecasts.json")
    args = ap.parse_args()

    uri, user, pwd = os.getenv("NEO4J_URI"), os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD")
    db = os.getenv("NEO4J_DATABASE", "neo4j")
    if not (uri and user and pwd and os.getenv("OPENAI_API_KEY")):
        sys.exit("Need NEO4J_* and OPENAI_API_KEY in .env")
    d = GraphDatabase.driver(uri, auth=(user, pwd))
    oai = OpenAI()
    def q(c, **p): return d.execute_query(c, parameters_=p, database_=db).records

    # 1. future appointments + embed their complaints (store for reuse / EVIDENCED_BY)
    futures = q("""MATCH (p:Patient)-[:HAS_APPOINTMENT]->(a:Appointment {is_future:true})
        RETURN a.appointment_id AS aid, a.chief_complaint AS cc, a.species AS sp,
               a.life_stage AS ls, p.name AS pet, toString(a.scheduled_date) AS date,
               a.complaintEmbedding IS NOT NULL AS has_emb ORDER BY a.scheduled_date""")
    need = [f for f in futures if not f["has_emb"]]
    if need:
        emb = oai.embeddings.create(model=MODEL, input=[f["cc"] for f in need]).data
        q("""UNWIND $rows AS r MATCH (a:Appointment {appointment_id:r.aid})
             SET a.complaintEmbedding = r.e""",
          rows=[{"aid": f["aid"], "e": e.embedding} for f, e in zip(need, emb)])
    print(f"forecasting {len(futures)} future appointments (k={args.k})", flush=True)

    inventory = defaultdict(lambda: {"units": 0.0, "cost": 0.0, "class": "", "appts": 0})
    forecasts, evidence_pairs = [], []

    for n, f in enumerate(futures):
        # 2. similar historical appointments (same species, prefer same life_stage, has invoice)
        nbrs = q("""
            MATCH (a:Appointment {appointment_id:$aid})
            CALL db.index.vector.queryNodes('appointment_complaint_idx', 150, a.complaintEmbedding)
            YIELD node, score
            MATCH (p:Patient)-[:HAS_APPOINTMENT]->(node)
            WHERE coalesce(node.is_future,false)=false AND p.species=$sp
              AND EXISTS { (node)-[:HAS_INVOICE]->(:Invoice) }
            RETURN node.appointment_id AS aid, node.chief_complaint AS cc, score,
                   (p.life_stage=$ls) AS same_stage
            ORDER BY same_stage DESC, score DESC LIMIT $k
        """, aid=f["aid"], sp=f["sp"], ls=f["ls"], k=args.k)
        if not nbrs:
            continue
        K = len(nbrs)
        nbr_ids = [r["aid"] for r in nbrs]
        for rank, r in enumerate(nbrs):
            evidence_pairs.append({"f": f["aid"], "n": r["aid"], "rank": rank, "score": r["score"]})

        # 3. neighbor invoice line items
        items = q("""
            MATCH (n:Appointment)-[:HAS_INVOICE]->(:Invoice)-[:HAS_INVOICE]->(it:Item)
            WHERE n.appointment_id IN $ids
            RETURN n.appointment_id AS nid, it.line_name AS name, it.class AS cls,
                   coalesce(it.total_quanity,1.0) AS qty,
                   coalesce(it.charged_price, it.item_unit_price, 0.0) AS price
        """, ids=nbr_ids)

        # 4. aggregate per item
        agg = defaultdict(lambda: {"nbrs": set(), "qty": 0.0, "cost": 0.0, "class": ""})
        for it in items:
            a = agg[it["name"]]
            a["nbrs"].add(it["nid"]); a["qty"] += it["qty"]; a["cost"] += it["price"]; a["class"] = it["cls"]
        lines = []
        for name, a in agg.items():
            lines.append({
                "item": name, "class": a["class"],
                "prevalence": round(len(a["nbrs"]) / K, 2),
                "expected_units": round(a["qty"] / K, 2),
                "expected_cost": round(a["cost"] / K, 2),
            })
            inv = inventory[name]
            inv["units"] += a["qty"] / K; inv["cost"] += a["cost"] / K
            inv["class"] = a["class"]; inv["appts"] += 1
        lines.sort(key=lambda x: -x["prevalence"])
        forecasts.append({
            "appointment_id": f["aid"], "pet": f["pet"], "species": f["sp"],
            "life_stage": f["ls"], "date": f["date"], "complaint": f["cc"],
            "n_similar": K, "evidence": nbr_ids[:8],
            "expected_total_cost": round(sum(l["expected_cost"] for l in lines), 2),
            "lines": lines,
        })
        if (n + 1) % 50 == 0:
            print(f"  {n+1}/{len(futures)}", flush=True)

    # 5. materialize EVIDENCED_BY for "ask why"
    q("MATCH (:Appointment {is_future:true})-[r:EVIDENCED_BY]->() DELETE r")
    for i in range(0, len(evidence_pairs), 2000):
        q("""UNWIND $pairs AS pr
             MATCH (f:Appointment {appointment_id:pr.f}), (n:Appointment {appointment_id:pr.n})
             MERGE (f)-[r:EVIDENCED_BY]->(n) SET r.rank=pr.rank, r.score=pr.score""",
          pairs=evidence_pairs[i:i+2000])

    Path(ROOT / args.out).parent.mkdir(parents=True, exist_ok=True)
    (ROOT / args.out).write_text(json.dumps(forecasts, indent=2))

    # ---- report ----
    def show(fc):
        print(f"\n  {fc['date']}  {fc['pet']} ({fc['species']}, {fc['life_stage']})  [{fc['appointment_id']}]")
        print(f"  complaint: {fc['complaint']}")
        print(f"  based on {fc['n_similar']} similar past visits  |  expected total ${fc['expected_total_cost']}")
        for l in fc["lines"][:8]:
            print(f"     {int(l['prevalence']*100):>3d}%  {l['item'][:46]:46s} {l['class']:12s} ~{l['expected_units']:>5}u  ${l['expected_cost']}")

    print("\n" + "="*70 + "\nEXAMPLE CHARGE SHEETS")
    for sp in ("canine", "feline"):
        ex = next((fc for fc in forecasts if fc["species"] == sp), None)
        if ex: show(ex)

    print("\n" + "="*70 + "\n4-WEEK INVENTORY DEMAND (stockable goods: INVENTORY + PRESCRIPTION)")
    stock = sorted([(k, v) for k, v in inventory.items() if v["class"] in ("INVENTORY", "PRESCRIPTION")],
                   key=lambda x: -x[1]["units"])
    print(f"  {'item':48s}{'class':13s}{'4wk units':>10s}{'4wk $':>10s}")
    for name, v in stock[:25]:
        print(f"  {name[:46]:48s}{v['class']:13s}{round(v['units'],1):>10}{round(v['cost']):>10}")

    total_rev = sum(fc["expected_total_cost"] for fc in forecasts)
    print(f"\n  total forecast billing across {len(forecasts)} visits: ${round(total_rev)}")
    print(f"  full per-appointment forecasts -> {args.out}")
    d.close()


if __name__ == "__main__":
    main()
