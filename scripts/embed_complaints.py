"""
Embed historical appointment chief_complaints so we can vector-search "similar past
visits" for a new complaint. One-time setup (idempotent: skips already-embedded).

Corpus = appointments that have BOTH a chief_complaint AND an invoice (the only ones
useful as forecast evidence). Stores `complaintEmbedding` (3072-dim, text-embedding-3-large)
on each Appointment and creates the vector index `appointment_complaint_idx`.

Usage (project root, .env set with NEO4J_* + OPENAI_API_KEY):
  ./.venv/bin/python scripts/embed_complaints.py
"""

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase
from openai import OpenAI

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
MODEL = os.getenv("embedding_model", "text-embedding-3-large")
BATCH = 800


def main():
    uri, user, pwd = os.getenv("NEO4J_URI"), os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD")
    db = os.getenv("NEO4J_DATABASE", "neo4j")
    if not (uri and user and pwd and os.getenv("OPENAI_API_KEY")):
        sys.exit("Need NEO4J_* and OPENAI_API_KEY in .env")
    d = GraphDatabase.driver(uri, auth=(user, pwd))
    oai = OpenAI()
    def q(c, **p): return d.execute_query(c, parameters_=p, database_=db).records

    # corpus: appointments with a complaint + an invoice, not yet embedded
    todo = q("""
        MATCH (a:Appointment)-[:HAS_INVOICE]->(:Invoice)
        WHERE a.chief_complaint IS NOT NULL AND a.chief_complaint <> ''
          AND a.complaintEmbedding IS NULL
        RETURN elementId(a) AS eid, a.chief_complaint AS cc
    """)
    print(f"to embed: {len(todo)}", flush=True)

    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        t0 = time.time()
        resp = oai.embeddings.create(model=MODEL, input=[r["cc"] for r in chunk])
        rows = [{"eid": r["eid"], "emb": e.embedding} for r, e in zip(chunk, resp.data)]
        q("""UNWIND $rows AS row MATCH (a) WHERE elementId(a)=row.eid
             SET a.complaintEmbedding = row.emb""", rows=rows)
        print(f"  {min(i+BATCH,len(todo))}/{len(todo)} ({time.time()-t0:.1f}s)", flush=True)

    q("""CREATE VECTOR INDEX appointment_complaint_idx IF NOT EXISTS
         FOR (a:Appointment) ON a.complaintEmbedding
         OPTIONS {indexConfig: {`vector.dimensions`: 3072, `vector.similarity_function`: 'cosine'}}""")
    n = q("MATCH (a:Appointment) WHERE a.complaintEmbedding IS NOT NULL RETURN count(*) AS c")[0]["c"]
    print(f"done. {n} appointments embedded; index appointment_complaint_idx created.", flush=True)
    d.close()


if __name__ == "__main__":
    main()
