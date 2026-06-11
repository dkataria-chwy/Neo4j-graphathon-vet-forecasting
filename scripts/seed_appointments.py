"""
Seed ~20 simulated FUTURE scheduled appointments into graphathon-team-1.

Each appointment is a real patient + a natural-language presenting complaint,
grounded in this clinic's actual case mix (derm/GI/dental for dogs; GI/renal/URI
for cats) so the estimate generator's retrieval lands on real episodes.

Model:
  (:Appointment {appointment_id, scheduled_date (date), presenting_complaint,
                 species, life_stage, status})
  (:Patient)-[:HAS_APPOINTMENT]->(:Appointment)

species + life_stage are copied from the patient at seed time (single source of truth).

Idempotent: MERGE on appointment_id. Re-run to update. `--reset` deletes all seeded
appointments first.

Usage (from project root, with .env set):
  ./.venv/bin/python scripts/seed_appointments.py
  ./.venv/bin/python scripts/seed_appointments.py --reset
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# (patient_id, scheduled_date, presenting_complaint) — dates within 4 weeks of 2026-06-10
APPOINTMENTS = [
    ("11815486", "2026-06-12", "Constant scratching and chewing his front paws; the skin between his toes looks red and inflamed."),
    ("11828709", "2026-06-13", "Soft, loose stool for three days and threw up twice; still playful and eating."),
    ("11415825", "2026-06-15", "Shaking his head a lot and pawing at his right ear, which has a bad smell."),
    ("11469749", "2026-06-16", "Scooting his bottom across the floor and licking back there constantly."),
    ("11516962", "2026-06-18", "Itchy all over and chewing at his sides; a few bald patches on his flank."),
    ("11358821", "2026-06-19", "On-and-off vomiting for about a week and eating much less than usual."),
    ("11367613", "2026-06-20", "Really bad breath with brown tartar; seems to chew only on one side."),
    ("11408479", "2026-06-23", "Red, itchy ears again and scratching at them; he's had ear infections before."),
    ("11341406", "2026-06-24", "Lower energy lately, drinking more water than normal, and vomited a couple of times."),
    ("11358466", "2026-06-25", "Stiff and slow getting up, reluctant on walks and hesitant on the stairs."),
    ("11358644", "2026-06-27", "Noticed a lump on his skin last week that seems to be getting a bit bigger."),
    ("11794883", "2026-06-30", "Sneezing a lot with watery, goopy eyes for the past several days."),
    ("11737722", "2026-07-01", "Loose stool and not finishing her meals over the last few days."),
    ("11527013", "2026-07-02", "Over-grooming her belly to the point of bald patches."),
    ("11711809", "2026-07-03", "Vomiting hairballs more than usual lately; otherwise eating fine."),
    ("11438705", "2026-07-04", "Putting on weight and noticeably less active than she used to be."),
    ("11625074", "2026-07-06", "Bad breath and drooling a little; seems uncomfortable when eating."),
    ("11469625", "2026-07-07", "Drinking and urinating a lot, and losing weight despite a good appetite."),
    ("11492538", "2026-07-07", "Losing weight over the past month with occasional vomiting."),
    ("11524305", "2026-07-08", "A heart murmur was heard at her last visit; now she's breathing a bit fast at rest."),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reset", action="store_true", help="delete all seeded appointments first")
    args = ap.parse_args()

    uri = os.getenv("NEO4J_URI"); user = os.getenv("NEO4J_USERNAME")
    pwd = os.getenv("NEO4J_PASSWORD"); db = os.getenv("NEO4J_DATABASE", "neo4j")
    if not (uri and user and pwd):
        sys.exit("Set NEO4J_URI / NEO4J_USERNAME / NEO4J_PASSWORD in .env")

    d = GraphDatabase.driver(uri, auth=(user, pwd))
    def q(c, **p): return d.execute_query(c, parameters_=p, database_=db).records

    q("CREATE CONSTRAINT appointment_id IF NOT EXISTS "
      "FOR (a:Appointment) REQUIRE a.appointment_id IS UNIQUE")

    if args.reset:
        n = q("MATCH (a:Appointment) WHERE a.status='scheduled' DETACH DELETE a "
              "RETURN count(*) AS c")
        print("reset: removed prior scheduled appointments")

    rows = [{"aid": f"appt:{i+1:03d}", "pid": pid, "date": date, "complaint": c}
            for i, (pid, date, c) in enumerate(APPOINTMENTS)]

    result = q("""
        UNWIND $rows AS row
        MATCH (p:Patient {patient_id: row.pid})
        MERGE (a:Appointment {appointment_id: row.aid})
        SET a.scheduled_date = date(row.date),
            a.presenting_complaint = row.complaint,
            a.species = p.species,
            a.life_stage = p.life_stage,
            a.status = 'scheduled'
        MERGE (p)-[:HAS_APPOINTMENT]->(a)
        RETURN a.appointment_id AS aid, p.name AS pet, a.species AS sp,
               a.life_stage AS ls, toString(a.scheduled_date) AS date
        ORDER BY a.scheduled_date
    """, rows=rows)

    print(f"\nSeeded {len(result)} appointments:")
    for r in result:
        print(f"  {r['date']}  {r['aid']}  {r['pet']:14s} {r['sp']:7s} {r['ls']}")

    missing = {r["pid"] for r in rows} - {
        x["pid"] for x in q("MATCH (p:Patient)-[:HAS_APPOINTMENT]->() RETURN p.patient_id AS pid")
    }
    if missing:
        print(f"\nWARNING: patient_ids not found (no appointment created): {missing}")
    d.close()


if __name__ == "__main__":
    main()
