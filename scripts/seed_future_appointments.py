"""
Seed mock FUTURE scheduled appointments — the forecast targets — ~8 per clinic-day
for the next 4 weeks (from 2026-06-11). Real patients; complaints grounded in the
clinic's actual case mix. These have NO invoice (that's what we forecast).

Marked with appointment_id 'future:NNNN' and is_future=true so they're easy to find
and never confused with the 12k historical (billed) appointments.

Model: (:Patient)-[:HAS_APPOINTMENT]->(:Appointment {is_future:true, status:'scheduled',
        scheduled_date (date), chief_complaint, species, life_stage})

Usage:
  ./.venv/bin/python scripts/seed_future_appointments.py [--reset] [--per-day 8]
"""

import argparse
import os
import random
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
random.seed(42)

START = date(2026, 6, 11)      # tomorrow, relative to "today" 2026-06-10
WEEKS = 4

# complaint templates grounded in the clinic's real case mix (derm/GI/dental/ENT/ortho/
# urinary/ocular/mass/wellness). {sp} omitted — patient species drives cohorting.
COMPLAINTS = [
    "Itchy all over, scratching and licking the front paws; skin looks red between the toes",
    "Recurring ear infection — head shaking, scratching at the ear, and a bad smell",
    "Losing hair with a bald patch from over-grooming the belly",
    "Red irritated hot spot on the flank that appeared over the weekend",
    "Vomiting and soft stool for several days, eating less than usual",
    "Diarrhea for a few days, otherwise bright and active",
    "Decreased appetite with occasional vomiting over the past week",
    "Bad breath and heavy tartar; seems to chew on one side and drops food",
    "Sneezing with watery, goopy eyes for several days",
    "Coughing on and off for about a week",
    "Limping on a hind leg and stiff getting up in the mornings",
    "Reluctant to jump and slowing down on walks",
    "Straining to urinate and going more frequently than normal",
    "Noticed a lump under the skin that seems to be getting bigger",
    "Squinting and discharge from one eye",
    "Annual wellness exam, due for vaccines",
    "Senior wellness check with full bloodwork",
    "Puppy/kitten visit — next vaccine in the series",
    "Spay/neuter consultation",
    "Nail trim and anal gland expression",
    "Drinking and urinating a lot, with some weight loss",
    "Scooting and licking the rear end",
]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--per-day", type=int, default=8)
    args = ap.parse_args()

    uri, user, pwd = os.getenv("NEO4J_URI"), os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD")
    db = os.getenv("NEO4J_DATABASE", "neo4j")
    if not (uri and user and pwd):
        sys.exit("Need NEO4J_* in .env")
    d = GraphDatabase.driver(uri, auth=(user, pwd))
    def q(c, **p): return d.execute_query(c, parameters_=p, database_=db).records

    # appointment_id already has a NODE KEY constraint from the invoice data load — reuse it.
    if args.reset:
        q("MATCH (a:Appointment) WHERE a.is_future = true DETACH DELETE a")
        print("reset: removed prior future appointments")

    # clinic days = next 4 weeks, skip Sundays
    days = []
    cur = START
    while cur < START + timedelta(weeks=WEEKS):
        if cur.weekday() != 6:  # 6 = Sunday
            days.append(cur)
        cur += timedelta(days=1)

    # patient pool (real patients), shuffled
    pool = [(r["pid"], r["sp"], r["ls"]) for r in q(
        "MATCH (p:Patient) WHERE p.patient_id IS NOT NULL "
        "RETURN p.patient_id AS pid, p.species AS sp, p.life_stage AS ls")]
    random.shuffle(pool)

    rows, idx, pi = [], 1, 0
    for day in days:
        for _ in range(args.per_day):
            pid, sp, ls = pool[pi % len(pool)]; pi += 1
            rows.append({
                "aid": f"future:{idx:04d}", "pid": pid,
                "date": day.isoformat(),
                "cc": random.choice(COMPLAINTS),
            })
            idx += 1

    res = q("""
        UNWIND $rows AS row
        MATCH (p:Patient {patient_id: row.pid})
        MERGE (a:Appointment {appointment_id: row.aid})
        SET a.is_future = true, a.status = 'scheduled',
            a.scheduled_date = date(row.date),
            a.chief_complaint = row.cc,
            a.species = p.species, a.life_stage = p.life_stage
        MERGE (p)-[:HAS_APPOINTMENT]->(a)
        RETURN count(a) AS n
    """, rows=rows)
    print(f"seeded {res[0]['n']} future appointments across {len(days)} clinic-days "
          f"({args.per_day}/day)")
    for r in q("""MATCH (a:Appointment {is_future:true})
                  RETURN a.species AS sp, count(*) AS c ORDER BY c DESC"""):
        print(f"   {r['sp']}: {r['c']}")
    d.close()


if __name__ == "__main__":
    main()
