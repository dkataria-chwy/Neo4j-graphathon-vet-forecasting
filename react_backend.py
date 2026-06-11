"""React inventory tracker backend with Neo4j and Codex CLI chat loop."""

from __future__ import annotations

import csv
import asyncio
import html
import io
import json
import math
import os
import re
import subprocess
import tempfile
import textwrap
import time
from urllib.parse import quote_plus
import zipfile
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

import pandas as pd
from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route
from starlette.staticfiles import StaticFiles

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")
FRONTEND_DIR = BASE_DIR / "react_app"
CLINIC_NAME = "Florida Plantation Clinic"
GRAPH_GAP_LABEL = "Not in graph"
KG_VENDOR_OPTION = "Use KG supplier"
STOCKABLE_CLASSES = {"INVENTORY", "PRESCRIPTION"}
MIN_SUPPORT_CASES = 3
VENDOR_CATALOG = {
    "Amazon": {
        "website": "https://www.amazon.com",
        "search_url": "https://www.amazon.com/s?k={query}",
        "cart_mode": "Search draft only",
    },
    "Chewy": {
        "website": "https://www.chewy.com",
        "search_url": "https://www.chewy.com/s?query={query}",
        "cart_mode": "Search draft only",
    },
    "Covetrus": {
        "website": "https://northamerica.covetrus.com",
        "search_url": "https://northamerica.covetrus.com/search?text={query}",
        "cart_mode": "Search draft only",
    },
    "MWI": {
        "website": "https://www.mwiah.com",
        "search_url": "https://www.mwiah.com/search?text={query}",
        "cart_mode": "Search draft only",
    },
    "Patterson": {
        "website": "https://www.pattersonvet.com",
        "search_url": "https://www.pattersonvet.com/search?keyword={query}",
        "cart_mode": "Search draft only",
    },
    "Med-Vet International": {
        "website": "https://www.shopmedvet.com",
        "search_url": "https://www.shopmedvet.com/search?keywords={query}",
        "cart_mode": "Visible add-to-cart automation",
    },
}
VENDOR_OPTIONS = [*VENDOR_CATALOG.keys(), KG_VENDOR_OPTION]
UNKNOWN_VALUES = {"", "unknown", "not documented", "dose not documented", "none", "nan", "n/a"}
QUANTITY_RE = re.compile(r"[-+]?\d*\.?\d+")
CACHE_TTL_SECONDS = 300
MAX_PAYLOAD_CACHE_ENTRIES = 64
PAYLOAD_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
EVIDENCE_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def get_driver() -> Driver:
    username = os.getenv("NEO4J_USERNAME") or os.getenv("NEO4J_USER") or os.getenv("E") or "neo4j"
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(username, os.environ["NEO4J_PASSWORD"]),
        connection_timeout=5,
    )
    driver.verify_connectivity()
    return driver


def run_query(cypher: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
    database = os.getenv("NEO4J_DATABASE", "neo4j")
    with get_driver().session(database=database) as session:
        result = session.run(cypher, params or {})
        return pd.DataFrame([record.data() for record in result])


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, list):
        return all(is_missing(item) for item in value)
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip().lower() in UNKNOWN_VALUES


def clean_text(value: Any) -> str:
    return "" if is_missing(value) else str(value).strip()


def normalize_vendor(value: Any) -> str:
    vendor = clean_text(value)
    return vendor if vendor in VENDOR_OPTIONS else "Amazon"


def vendor_metadata(vendor: str) -> dict[str, str]:
    if vendor == KG_VENDOR_OPTION:
        return {"website": "", "search_url": "", "cart_mode": "KG supplier values only"}
    return VENDOR_CATALOG.get(vendor, VENDOR_CATALOG["Amazon"])


def vendor_search_url(vendor: str, item_name: Any) -> str:
    metadata = vendor_metadata(vendor)
    template = metadata.get("search_url", "")
    if not template:
        return ""
    return template.format(query=quote_plus(clean_text(item_name)))


def slugify(value: Any) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", clean_text(value).lower()).strip("_")
    return slug or "vendor"


def json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    return value


def parse_date(value: Any) -> date | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text[:10]).date()
    except ValueError:
        return None


def parse_number(value: Any) -> float | None:
    if is_missing(value):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if math.isnan(float(value)):
            return None
        return float(value)
    match = QUANTITY_RE.search(str(value).replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def join_unique(values: pd.Series, limit: int = 4) -> str:
    seen: list[str] = []
    for value in values:
        text = clean_text(value)
        if text and text not in seen:
            seen.append(text)
        if len(seen) >= limit:
            break
    return ", ".join(seen)


def extract_search_terms(query: str) -> list[str]:
    stop_words = {
        "appointment",
        "visit",
        "with",
        "and",
        "the",
        "for",
        "due",
        "from",
        "that",
        "this",
        "have",
        "has",
        "patient",
    }
    terms: list[str] = []
    for word in re.findall(r"[A-Za-z][A-Za-z'-]+", query.lower()):
        if len(word) < 3 or word in stop_words or word in terms:
            continue
        terms.append(word)
    return terms[:14]


def get_graph_health() -> dict[str, Any]:
    totals = run_query(
        "MATCH (n) WITH count(n) AS nodes "
        "OPTIONAL MATCH ()-[r]->() "
        "RETURN nodes, count(r) AS relationships"
    )
    return {
        "nodes": int(totals.iloc[0]["nodes"]) if not totals.empty else 0,
        "relationships": int(totals.iloc[0]["relationships"]) if not totals.empty else 0,
        "database": os.getenv("NEO4J_DATABASE", "neo4j"),
    }


def get_episode_date_bounds() -> tuple[date, date]:
    bounds = run_query(
        "MATCH (e:Episode) "
        "WHERE e.start_date IS NOT NULL AND e.start_date <> 'unknown' "
        "RETURN min(e.start_date) AS min_date, max(e.start_date) AS max_date"
    )
    if bounds.empty or pd.isna(bounds.iloc[0]["min_date"]):
        today = date.today()
        return today - timedelta(days=365), today
    min_date = parse_date(bounds.iloc[0]["min_date"]) or date.today() - timedelta(days=365)
    max_date = parse_date(bounds.iloc[0]["max_date"]) or date.today()
    return min_date, max_date


def get_appointment_suggestions() -> list[str]:
    rows = run_query(
        """
        MATCH (:Episode)-[:HAD_SIGN]->(sign:ClinicalSignOccurrence)
        OPTIONAL MATCH (sign)-[:INSTANCE_OF]->(tag:RefStub)
        WITH coalesce(tag.name, sign.name) AS sign_name, count(*) AS support
        WHERE sign_name IS NOT NULL AND sign_name <> 'unknown clinical sign'
        RETURN sign_name AS title
        ORDER BY support DESC
        LIMIT 40
        """
    )
    if rows.empty:
        return ["vomiting", "wellness exam", "diarrhea", "pruritus", "dental calculus", "limping"]

    defaults = ["vomiting", "wellness exam", "diarrhea", "pruritus", "dental calculus", "limping", "ear debris"]
    suggestions = defaults + [clean_text(item) for item in rows["title"].dropna()]
    deduped: list[str] = []
    for item in suggestions:
        if item not in deduped:
            deduped.append(item)
    return deduped[:30]


def get_species_life_stage_options() -> dict[str, Any]:
    rows = run_query(
        """
        MATCH (p:Patient)
        WHERE p.species IS NOT NULL
        RETURN p.species AS species, p.life_stage AS life_stage, count(*) AS patients
        ORDER BY species, patients DESC
        """
    )
    species: list[str] = []
    life_stages: dict[str, list[str]] = {"all": []}
    if rows.empty:
        return {"species": ["all", "canine", "feline"], "lifeStages": {"all": ["all"]}}
    for _, row in rows.iterrows():
        species_name = clean_text(row["species"])
        stage = clean_text(row["life_stage"])
        if species_name and species_name not in species:
            species.append(species_name)
        if species_name and stage:
            life_stages.setdefault(species_name, [])
            if stage not in life_stages[species_name]:
                life_stages[species_name].append(stage)
            if stage not in life_stages["all"]:
                life_stages["all"].append(stage)
    options = {key: ["all"] + value for key, value in life_stages.items()}
    return {"species": ["all"] + species, "lifeStages": options}


def exact_sign_fallbacks(query: str) -> list[str]:
    terms = set(extract_search_terms(query))
    wellness_terms = {"wellness", "annual", "preventive", "prevention", "vaccine", "vaccines", "vaccination", "exam"}
    if terms & wellness_terms:
        return ["unknown clinical sign"]
    return []


def load_similar_appointments(
    query: str,
    start_date: str,
    end_date: str,
    limit: int,
    species: str,
    life_stage: str,
) -> pd.DataFrame:
    search = query.strip()
    terms = extract_search_terms(search)
    exact_signs = exact_sign_fallbacks(search)
    if not search or (not terms and not exact_signs):
        return pd.DataFrame()

    return run_query(
        """
        MATCH (p:Patient)-[:HAD_EPISODE]->(e:Episode)-[:HAD_SIGN]->(sgn:ClinicalSignOccurrence)
        OPTIONAL MATCH (sgn)-[:INSTANCE_OF]->(sign_tag:RefStub)
        WITH p, e,
          coalesce(sign_tag.name, sgn.name, 'unknown clinical sign') AS sign_name,
          toLower(coalesce(sign_tag.name, sgn.name, 'unknown clinical sign')) AS sign_text
        WHERE e.start_date IS NOT NULL
          AND e.start_date >= $start_date
          AND e.start_date <= $end_date
          AND ($species = 'all' OR p.species = $species)
          AND ($life_stage = 'all' OR p.life_stage = $life_stage)
        WITH p, e, sign_name, sign_text,
          [term IN $terms WHERE sign_text CONTAINS term] AS matched_terms,
          CASE WHEN sign_text IN $exact_signs THEN 2 ELSE 0 END AS exact_score
        WITH p, e,
          collect(DISTINCT sign_name) AS presentation_signs,
          collect(DISTINCT CASE WHEN size(matched_terms) > 0 OR exact_score > 0 THEN sign_name ELSE NULL END) AS raw_matched_signs,
          sum(size(matched_terms)) + sum(exact_score) AS match_score
        WITH p, e, presentation_signs,
          [sign IN raw_matched_signs WHERE sign IS NOT NULL] AS matched_signs,
          match_score
        WHERE size(matched_signs) > 0
        RETURN
          e.id AS episode_id,
          e.episode_title AS appointment,
          e.start_date AS appointment_date,
          p.species AS species,
          p.life_stage AS life_stage,
          matched_signs,
          presentation_signs,
          match_score,
          substring(coalesce(e.narrative, ''), 0, 240) AS narrative
        ORDER BY match_score DESC, e.start_date DESC
        LIMIT $limit
        """,
        {
            "terms": terms,
            "exact_signs": exact_signs,
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit,
            "species": species,
            "life_stage": life_stage,
        },
    )


def line_query(match_pattern: str, graph_path: str, item_alias: str) -> str:
    return f"""
    MATCH {match_pattern}
    WHERE e.id IN $episode_ids
      AND ($forecast_scope <> 'day1' OR coalesce({item_alias}.timestamp, dx.timestamp, sgn.timestamp, e.start_date) = e.start_date)
      AND (
        $include_procedural
        OR coalesce({item_alias}.indication_type, 'therapeutic') IN $included_indications
      )
    OPTIONAL MATCH (sgn)-[:INSTANCE_OF]->(sign_tag:RefStub)
    OPTIONAL MATCH (dx)-[:INSTANCE_OF]->(dx_tag:RefStub)
    OPTIONAL MATCH ({item_alias})-[:INSTANCE_OF]->(med_tag:RefStub)
    RETURN DISTINCT
      e.id AS episode_id,
      e.episode_title AS appointment,
      e.start_date AS service_date,
      'Medication' AS category,
      coalesce(med_tag.name, {item_alias}.name, {item_alias}.name_original, 'Unnamed medication') AS item,
      coalesce({item_alias}.id, elementId({item_alias})) AS line_id,
      coalesce(sign_tag.name, sgn.name, 'unknown clinical sign') AS presentation_sign,
      coalesce(dx_tag.name, dx.name, 'Diagnosis not documented') AS source_reason,
      dx.diagnosis_status AS diagnosis_status,
      coalesce({item_alias}.indication_type, 'therapeutic') AS indication_type,
      '{graph_path}' AS graph_path,
      {item_alias}.dose AS unit_size,
      {item_alias}.route AS route,
      {item_alias}.frequency AS frequency,
      {item_alias}['#_dispensed'] AS quantity_raw,
      coalesce(
        properties({item_alias})['supplier'],
        properties({item_alias})['vendor'],
        properties({item_alias})['store'],
        properties({item_alias})['supplier_or_store'],
        properties({item_alias})['Supplier or Store']
      ) AS supplier,
      coalesce(
        properties({item_alias})['unit_price'],
        properties({item_alias})['price'],
        properties({item_alias})['price_paid'],
        properties({item_alias})['invoice_price'],
        properties({item_alias})['Price Paid']
      ) AS unit_price
    """


def load_medication_lines(episode_ids: list[str], forecast_scope: str, include_procedural: bool) -> pd.DataFrame:
    if not episode_ids:
        return pd.DataFrame()

    queries = [
        line_query(
            "(e:Episode)-[:HAD_SIGN]->(sgn:ClinicalSignOccurrence)-[:HAD_DIAGNOSIS]->(dx:DiagnosisOccurrence)-[:HAD_TREATMENT_MEDICATION]->(line:MedicationOccurrence)",
            "Episode > Sign > Diagnosis > Treatment Medication",
            "line",
        ),
    ]
    if include_procedural:
        queries.append(
            line_query(
                "(e:Episode)-[:HAD_SIGN]->(sgn:ClinicalSignOccurrence)-[:HAD_DIAGNOSIS]->(dx:DiagnosisOccurrence)-[:HAD_TREATMENT_PROCEDURE]->(tp:TreatmentProcedureOccurrence)-[:PROC_GAVE_MEDICATION]->(line:MedicationOccurrence)",
                "Episode > Sign > Diagnosis > Procedure > Procedure Medication",
                "line",
            )
        )

    params = {
        "episode_ids": episode_ids,
        "forecast_scope": forecast_scope,
        "include_procedural": include_procedural,
        "included_indications": ["therapeutic", "treatment", "preventive", "preventive care"],
    }
    frames = [run_query(query, params) for query in queries]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return pd.DataFrame()
    lines = pd.concat(frames, ignore_index=True)
    return lines.drop_duplicates(subset=["episode_id", "category", "line_id"])


def prepare_medication_lines(raw_lines: pd.DataFrame) -> pd.DataFrame:
    if raw_lines.empty:
        return raw_lines
    lines = raw_lines.copy()
    lines["line_qty"] = lines["quantity_raw"].apply(parse_number).fillna(1.0)
    return lines


def build_medication_predictions(lines: pd.DataFrame, similar_count: int, min_cases: int = 3) -> pd.DataFrame:
    if lines.empty or similar_count == 0:
        return pd.DataFrame()

    records: list[dict[str, Any]] = []
    for (_category, item), group in lines.groupby(["category", "item"], dropna=False):
        seen_appointments = group["episode_id"].nunique()
        likelihood = seen_appointments / similar_count
        if seen_appointments < min_cases:
            continue

        avg_qty = float(group["line_qty"].sum() / similar_count)
        recommended_qty = max(1.0, round(avg_qty, 1))
        unit_price = group["unit_price"].apply(parse_number).dropna()
        confidence = "High" if likelihood >= 0.1 and seen_appointments >= 8 else "Medium" if likelihood >= 0.04 else "Low"
        status = "Top match" if confidence == "High" else "Supported" if confidence == "Medium" else "Possible"

        records.append(
            {
                "Action": status,
                "Medication name": clean_text(item) or "Unnamed medication",
                "Predicted qty": recommended_qty,
                "Likelihood": likelihood,
                "Seen in appointments": seen_appointments,
                "Similar appointments": similar_count,
                "Typical dose/unit": join_unique(group["unit_size"], 3) or GRAPH_GAP_LABEL,
                "Route": join_unique(group["route"], 3) or GRAPH_GAP_LABEL,
                "Frequency": join_unique(group["frequency"], 3) or GRAPH_GAP_LABEL,
                "Reason matched": join_unique(group["source_reason"], 4) or "Similar appointment medication history",
                "Presentation signs": join_unique(group["presentation_sign"], 4) or GRAPH_GAP_LABEL,
                "Diagnosis status": join_unique(group["diagnosis_status"], 3) or GRAPH_GAP_LABEL,
                "Indication type": join_unique(group["indication_type"], 3) or GRAPH_GAP_LABEL,
                "Graph path": join_unique(group["graph_path"], 2) or GRAPH_GAP_LABEL,
                "Supplier or Store": join_unique(group["supplier"], 3) or GRAPH_GAP_LABEL,
                "Price Paid": unit_price.median() if not unit_price.empty else math.nan,
                "Confidence": confidence,
                "Evidence appointments": join_unique(group["appointment"], 3),
            }
        )

    predictions = pd.DataFrame(records)
    if predictions.empty:
        return predictions
    order = {"Top match": 0, "Supported": 1, "Possible": 2}
    predictions["_order"] = predictions["Action"].map(order).fillna(9)
    predictions = predictions.sort_values(
        ["_order", "Likelihood", "Seen in appointments"],
        ascending=[True, False, False],
    )
    return predictions.drop(columns=["_order"]).reset_index(drop=True)


def build_inventory_sheet(predictions: pd.DataFrame, purchase_date: date, vendor: str) -> pd.DataFrame:
    if predictions.empty:
        return pd.DataFrame(
            columns=[
                "Medication Name",
                "Product Type",
                "Quantity Needed",
                "Expected Units",
                "Unit Size",
                "Forecasted Appointments",
                "Date To Purchase",
                "Supplier or Store",
                "Expected Cost",
            ]
        )

    records: list[dict[str, Any]] = []
    for _, row in predictions.iterrows():
        quantity_needed = math.ceil(parse_number(row["Predicted qty"]) or 1)
        price = row["Price Paid"]
        use_kg_supplier = vendor == KG_VENDOR_OPTION
        supplier = row["Supplier or Store"] if use_kg_supplier else vendor
        price_text = f"${price:,.2f}" if pd.notna(price) else GRAPH_GAP_LABEL
        if not use_kg_supplier:
            price_text = "Vendor quote needed"
        records.append(
            {
                "Medication Name": row["Medication name"],
                "Product Type": "Medication",
                "Quantity Needed": quantity_needed,
                "Expected Units": quantity_needed,
                "Unit Size": row["Typical dose/unit"],
                "Forecasted Appointments": int(row.get("Seen in appointments") or 0),
                "Date To Purchase": purchase_date.isoformat(),
                "Supplier or Store": supplier,
                "Expected Cost": price_text,
                "Price Paid": price_text,
            }
        )
    return pd.DataFrame(records)


def build_vendor_invoice(inventory: pd.DataFrame, vendor: str) -> list[dict[str, Any]]:
    if inventory.empty:
        return []
    rows: list[dict[str, Any]] = []
    metadata = vendor_metadata(vendor)
    for index, row in inventory.reset_index(drop=True).iterrows():
        quantity = int(parse_number(row["Quantity Needed"]) or 1)
        item_name = row["Medication Name"]
        rows.append(
            {
                "Line": index + 1,
                "Vendor": vendor,
                "Medication Name": item_name,
                "Quantity": quantity,
                "Unit Size": row["Unit Size"],
                "Price": row.get("Expected Cost") or row.get("Price Paid") or "Vendor quote needed",
                "Search URL": vendor_search_url(vendor, item_name),
                "Website": metadata.get("website", ""),
                "Cart Status": "Ready for cart draft" if vendor != KG_VENDOR_OPTION else "Using KG supplier value",
            }
        )
    return rows


def build_provenance_summary(predictions: pd.DataFrame) -> list[dict[str, Any]]:
    if predictions.empty:
        return []
    rows: list[dict[str, Any]] = []
    for _, row in predictions.iterrows():
        rows.append(
            {
                "Medication": row["Medication name"],
                "Support Cases": int(row["Seen in appointments"]),
                "Similar Cases": int(row["Similar appointments"]),
                "Presentation Signs": row["Presentation signs"],
                "Diagnosis Basis": row["Reason matched"],
                "Diagnosis Status": row["Diagnosis status"],
                "Indication": row["Indication type"],
                "Graph Path": row["Graph path"],
                "Example Appointments": row["Evidence appointments"],
            }
        )
    return rows


def graph_credentials_available() -> bool:
    return bool(os.getenv("NEO4J_URI") and os.getenv("NEO4J_PASSWORD"))


def require_graph_credentials() -> None:
    if not graph_credentials_available():
        raise RuntimeError("Neo4j credentials are required for this dashboard.")


def strict_graph_health() -> dict[str, Any]:
    require_graph_credentials()
    return get_graph_health()


def forecast_item_parts(item_name: Any) -> tuple[str, str]:
    parts = [part.strip() for part in clean_text(item_name).split("|") if part.strip()]
    if not parts:
        return GRAPH_GAP_LABEL, "Each"
    return parts[0], " | ".join(parts[1:]) if len(parts) > 1 else "Each"


def forecast_options_from_rows(rows: pd.DataFrame) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for _, row in rows.iterrows():
        complaint = clean_text(row.get("complaint"))
        label = (
            f"{row.get('date')} · {row.get('pet')} · "
            f"{row.get('species')} {row.get('life_stage')} · {complaint[:70]}"
        )
        options.append(
            {
                "id": row.get("appointment_id"),
                "label": label,
                "date": row.get("date"),
                "pet": row.get("pet"),
                "species": row.get("species"),
                "lifeStage": row.get("life_stage"),
                "complaint": complaint,
                "expectedTotalCost": 0,
                "stockableRows": 0,
                "evidenceCount": int(row.get("evidence_count") or 0),
            }
        )
    return options


def load_kg_forecast_options() -> list[dict[str, Any]]:
    require_graph_credentials()
    rows = run_query(
        """
        MATCH (pet:Patient)-[:HAS_APPOINTMENT]->(appointment:Appointment)
        WHERE coalesce(appointment.is_future, false) = true
        OPTIONAL MATCH (appointment)-[:EVIDENCED_BY]->(past:Appointment)
        WITH appointment, pet, count(past) AS evidence_count
        RETURN
            appointment.appointment_id AS appointment_id,
            pet.name AS pet,
            coalesce(appointment.species, pet.species) AS species,
            coalesce(appointment.life_stage, pet.life_stage) AS life_stage,
            toString(appointment.scheduled_date) AS date,
            coalesce(appointment.chief_complaint, appointment.presenting_complaint, "") AS complaint,
            evidence_count
        ORDER BY appointment.scheduled_date, appointment.appointment_id
        """
    )
    if rows.empty:
        raise RuntimeError("No future appointments were found in Neo4j. Run seed_future_appointments.py and generate_forecast.py first.")
    return forecast_options_from_rows(rows)


def load_kg_future_appointment_count() -> int:
    require_graph_credentials()
    rows = run_query(
        """
        MATCH (appointment:Appointment)
        WHERE coalesce(appointment.is_future, false) = true
        RETURN count(appointment) AS future_count
        """
    )
    return int(rows.iloc[0]["future_count"]) if not rows.empty else 0


def load_kg_future_summary() -> dict[str, Any]:
    require_graph_credentials()
    rows = run_query(
        """
        MATCH (appointment:Appointment)
        WHERE coalesce(appointment.is_future, false) = true
        OPTIONAL MATCH (appointment)-[edge:EVIDENCED_BY]->(:Appointment)
        RETURN
            count(DISTINCT appointment) AS forecast_visits,
            count(edge) AS evidence_links,
            min(toString(appointment.scheduled_date)) AS start_date,
            max(toString(appointment.scheduled_date)) AS end_date
        """
    )
    if rows.empty:
        return {
            "forecast_visits": 0,
            "evidence_links": 0,
            "start_date": date.today().isoformat(),
            "end_date": date.today().isoformat(),
        }
    row = rows.iloc[0]
    return {
        "forecast_visits": int(row.get("forecast_visits") or 0),
        "evidence_links": int(row.get("evidence_links") or 0),
        "start_date": clean_text(row.get("start_date")) or date.today().isoformat(),
        "end_date": clean_text(row.get("end_date")) or date.today().isoformat(),
    }


def load_kg_total_expected_billing() -> float:
    require_graph_credentials()
    rows = run_query(
        """
        MATCH (future:Appointment)
        WHERE coalesce(future.is_future, false) = true
        MATCH (future)-[:EVIDENCED_BY]->(past:Appointment)
        WITH future, collect(DISTINCT past.appointment_id) AS past_ids, count(DISTINCT past) AS k
        WHERE k > 0
        MATCH (past:Appointment)-[:HAS_INVOICE]->(:Invoice)-[:HAS_INVOICE]->(invoice_item:Item)
        WHERE past.appointment_id IN past_ids
        WITH future, k, sum(toFloat(coalesce(invoice_item.charged_price, invoice_item.item_unit_price, 0.0))) AS total_cost
        WITH future, total_cost * 1.0 / k AS expected_cost
        RETURN round(sum(expected_cost), 2) AS expected_total
        """
    )
    if rows.empty:
        return 0.0
    return float(rows.iloc[0].get("expected_total") or 0.0)


def load_kg_forecast(params: dict[str, Any]) -> dict[str, Any]:
    require_graph_credentials()
    requested_id = clean_text(params.get("forecastId") or params.get("appointmentId"))
    if requested_id:
        appointment_rows = run_query(
            """
            MATCH (pet:Patient)-[:HAS_APPOINTMENT]->(appointment:Appointment {appointment_id:$appointment_id})
            WHERE coalesce(appointment.is_future, false) = true
            OPTIONAL MATCH (appointment)-[:EVIDENCED_BY]->(past:Appointment)
            WITH appointment, pet, count(past) AS evidence_count
            RETURN
                appointment.appointment_id AS appointment_id,
                pet.name AS pet,
                coalesce(appointment.species, pet.species) AS species,
                coalesce(appointment.life_stage, pet.life_stage) AS life_stage,
                toString(appointment.scheduled_date) AS date,
                coalesce(appointment.chief_complaint, appointment.presenting_complaint, "") AS complaint,
                evidence_count
            LIMIT 1
            """,
            {"appointment_id": requested_id},
        )
    else:
        appointment_rows = run_query(
            """
            MATCH (pet:Patient)-[:HAS_APPOINTMENT]->(appointment:Appointment)
            WHERE coalesce(appointment.is_future, false) = true
            OPTIONAL MATCH (appointment)-[:EVIDENCED_BY]->(past:Appointment)
            WITH appointment, pet, count(past) AS evidence_count
            RETURN
                appointment.appointment_id AS appointment_id,
                pet.name AS pet,
                coalesce(appointment.species, pet.species) AS species,
                coalesce(appointment.life_stage, pet.life_stage) AS life_stage,
                toString(appointment.scheduled_date) AS date,
                coalesce(appointment.chief_complaint, appointment.presenting_complaint, "") AS complaint,
                evidence_count
            ORDER BY appointment.scheduled_date, appointment.appointment_id
            LIMIT 1
            """
        )
    if appointment_rows.empty:
        raise RuntimeError("The selected future appointment was not found in Neo4j.")

    appointment = appointment_rows.iloc[0].to_dict()
    similar_count = int(appointment.get("evidence_count") or 0)
    if similar_count == 0:
        raise RuntimeError(
            f"Future appointment {appointment['appointment_id']} has no EVIDENCED_BY forecast edges in Neo4j. "
            "Run scripts/generate_forecast.py before opening the dashboard."
        )

    line_rows = run_query(
        """
        MATCH (future:Appointment {appointment_id:$appointment_id})-[:EVIDENCED_BY]->(past:Appointment)
        WITH collect(DISTINCT past.appointment_id) AS past_ids, count(DISTINCT past) AS k
        MATCH (past:Appointment)-[:HAS_INVOICE]->(:Invoice)-[:HAS_INVOICE]->(invoice_item:Item)
        WHERE past.appointment_id IN past_ids
          AND invoice_item.line_name IS NOT NULL
        WITH k,
             invoice_item.line_name AS item,
             coalesce(invoice_item.class, "UNKNOWN") AS class,
             count(DISTINCT past.appointment_id) AS support,
             sum(toFloat(coalesce(invoice_item.total_quanity, 1.0))) AS total_qty,
             sum(toFloat(coalesce(invoice_item.charged_price, invoice_item.item_unit_price, 0.0))) AS total_cost
        RETURN
            item,
            class,
            support,
            round(support * 1.0 / k, 2) AS prevalence,
            round(total_qty * 1.0 / k, 2) AS expected_units,
            round(total_cost * 1.0 / k, 2) AS expected_cost
        ORDER BY prevalence DESC, expected_cost DESC, item
        """,
        {"appointment_id": appointment["appointment_id"]},
    )
    if line_rows.empty:
        raise RuntimeError(f"Neo4j returned no invoice item rows for forecast {appointment['appointment_id']}.")
    lines = line_rows.to_dict(orient="records")
    return {
        "appointment_id": appointment["appointment_id"],
        "pet": appointment.get("pet"),
        "species": appointment.get("species"),
        "life_stage": appointment.get("life_stage"),
        "date": appointment.get("date"),
        "complaint": appointment.get("complaint"),
        "n_similar": similar_count,
        "expected_total_cost": round(sum(float(line.get("expected_cost") or 0) for line in lines), 2),
        "lines": lines,
    }


def forecast_line_support(forecast: dict[str, Any], line: dict[str, Any]) -> int:
    if parse_number(line.get("support")) is not None:
        return int(parse_number(line.get("support")) or 0)
    similar_count = int(forecast.get("n_similar") or 0)
    return int(round(float(line.get("prevalence") or 0) * similar_count))


def all_stockable_forecast_lines(forecast: dict[str, Any]) -> list[dict[str, Any]]:
    return [line for line in forecast.get("lines", []) if line.get("class") in STOCKABLE_CLASSES]


def stockable_forecast_lines(forecast: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        line
        for line in all_stockable_forecast_lines(forecast)
        if forecast_line_support(forecast, line) >= MIN_SUPPORT_CASES
    ]


def money(value: Any) -> str:
    number = parse_number(value)
    if number is None:
        return GRAPH_GAP_LABEL
    return f"${number:,.2f}"


def purchase_date_for_forecast(forecast: dict[str, Any]) -> date:
    appointment_date = parse_date(forecast.get("date")) or date.today() + timedelta(days=7)
    return max(date.today(), appointment_date - timedelta(days=2))


def build_inventory_from_forecast(forecast: dict[str, Any], vendor: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    purchase_date = purchase_date_for_forecast(forecast).isoformat()
    for line in stockable_forecast_lines(forecast):
        name, unit_size = forecast_item_parts(line.get("item"))
        expected_units = float(line.get("expected_units") or 0)
        expected_cost = float(line.get("expected_cost") or 0)
        quantity_needed = max(1, int(math.ceil(expected_units)))
        supplier = vendor if vendor != KG_VENDOR_OPTION else GRAPH_GAP_LABEL
        rows.append(
            {
                "Medication Name": name,
                "Product Type": line.get("class", "Medication"),
                "Quantity Needed": quantity_needed,
                "Expected Units": round(expected_units, 2),
                "Unit Size": unit_size,
                "Forecasted Appointments": forecast_line_support(forecast, line),
                "Date To Purchase": purchase_date,
                "Supplier or Store": supplier,
                "Expected Cost": money(expected_cost) if expected_cost > 0 else "Vendor quote needed",
                "Price Paid": money(expected_cost) if expected_cost > 0 else "Vendor quote needed",
                "_sourceItem": line.get("item"),
                "_expectedUnits": round(expected_units, 2),
                "_expectedCost": round(expected_cost, 2),
                "_prevalence": round(float(line.get("prevalence") or 0), 2),
                "_supportCases": forecast_line_support(forecast, line),
            }
        )
    return pd.DataFrame(rows)


def build_charge_lines(forecast: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in forecast.get("lines", []):
        rows.append(
            {
                "Charge Item": line.get("item"),
                "Class": line.get("class"),
                "Expected Units": line.get("expected_units"),
                "Expected Cost": money(line.get("expected_cost")),
            }
        )
    return rows


def build_forecast_provenance(forecast: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    similar_count = int(forecast.get("n_similar") or 0)
    for line in stockable_forecast_lines(forecast):
        name, unit_size = forecast_item_parts(line.get("item"))
        support = forecast_line_support(forecast, line)
        rows.append(
            {
                "Medication": name,
                "Product Type": line.get("class"),
                "Quantity Needed": max(1, int(math.ceil(float(line.get("expected_units") or 0)))),
                "Unit Size": unit_size,
                "Historical Invoice Support": f"{support} of {similar_count} similar visits",
                "Expected Cost": money(line.get("expected_cost")),
            }
        )
    return rows


def build_inventory_rollup(vendor: str) -> list[dict[str, Any]]:
    require_graph_credentials()
    rows = run_query(
        """
        MATCH (future:Appointment)
        WHERE coalesce(future.is_future, false) = true
        MATCH (future)-[:EVIDENCED_BY]->(past:Appointment)
        WITH future, collect(DISTINCT past.appointment_id) AS past_ids, count(DISTINCT past) AS k
        WHERE k > 0
        MATCH (past:Appointment)-[:HAS_INVOICE]->(:Invoice)-[:HAS_INVOICE]->(invoice_item:Item)
        WHERE past.appointment_id IN past_ids
          AND invoice_item.class IN $stockable_classes
          AND invoice_item.line_name IS NOT NULL
        WITH future, k,
             invoice_item.line_name AS item,
             coalesce(invoice_item.class, "UNKNOWN") AS class,
             count(DISTINCT past.appointment_id) AS support,
             sum(toFloat(coalesce(invoice_item.total_quanity, 1.0))) AS total_qty,
             sum(toFloat(coalesce(invoice_item.charged_price, invoice_item.item_unit_price, 0.0))) AS total_cost
        WHERE support >= $min_support
        WITH future, item, class, total_qty * 1.0 / k AS expected_units, total_cost * 1.0 / k AS expected_cost
        WITH item, class,
             sum(expected_units) AS expected_units,
             sum(expected_cost) AS expected_cost,
             count(DISTINCT future) AS appointments
        RETURN item, class, expected_units, expected_cost, appointments
        ORDER BY expected_units DESC
        LIMIT 50
        """,
        {"stockable_classes": list(STOCKABLE_CLASSES), "min_support": MIN_SUPPORT_CASES},
    )

    rollup_rows: list[dict[str, Any]] = []
    for _, row in rows.iterrows():
        name, unit_size = forecast_item_parts(row.get("item"))
        expected_units = float(row.get("expected_units") or 0)
        expected_cost = float(row.get("expected_cost") or 0)
        rollup_rows.append(
            {
                "Medication Name": name,
                "Product Type": row.get("class"),
                "Unit Size": unit_size,
                "Expected Units": round(expected_units, 1),
                "Expected Cost": money(expected_cost),
                "Appointments": int(row.get("appointments") or 0),
                "Supplier or Store": vendor if vendor != KG_VENDOR_OPTION else GRAPH_GAP_LABEL,
                "Order Units": max(1, int(math.ceil(expected_units))),
                "_sourceItem": row.get("item"),
                "_expectedUnits": round(expected_units, 2),
                "_expectedCost": round(expected_cost, 2),
            }
        )
    return rollup_rows


def build_inventory_from_rollup(rollup: list[dict[str, Any]], vendor: str, purchase_date: date) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for row in rollup:
        expected_cost = float(row.get("_expectedCost") or 0)
        expected_cost_text = money(expected_cost) if expected_cost > 0 else "Vendor quote needed"
        rows.append(
            {
                "Medication Name": row.get("Medication Name"),
                "Product Type": row.get("Product Type") or "Medication",
                "Quantity Needed": int(row.get("Order Units") or 1),
                "Expected Units": row.get("_expectedUnits"),
                "Unit Size": row.get("Unit Size") or "Each",
                "Forecasted Appointments": row.get("Appointments"),
                "Date To Purchase": purchase_date.isoformat(),
                "Supplier or Store": vendor if vendor != KG_VENDOR_OPTION else row.get("Supplier or Store", GRAPH_GAP_LABEL),
                "Expected Cost": expected_cost_text,
                "Cost Source": "Historical invoices" if expected_cost > 0 else "Vendor quote needed",
                "Price Paid": expected_cost_text,
                "_sourceItem": row.get("_sourceItem"),
                "_expectedUnits": row.get("_expectedUnits"),
                "_expectedCost": row.get("_expectedCost"),
                "_appointments": row.get("Appointments"),
            }
        )
    return pd.DataFrame(rows)


def build_aggregate_charge_lines(rollup: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "Charge Item": row.get("_sourceItem") or row.get("Medication Name"),
            "Class": row.get("Product Type"),
            "Expected Units": row.get("Expected Units"),
            "Expected Cost": row.get("Expected Cost"),
            "Future Appointments": row.get("Appointments"),
        }
        for row in rollup
    ]


def build_aggregate_provenance(rollup: list[dict[str, Any]], summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in rollup:
        rows.append(
            {
                "Medication": row.get("Medication Name"),
                "Product Type": row.get("Product Type"),
                "Quantity Needed": row.get("Order Units"),
                "Unit Size": row.get("Unit Size"),
                "Forecasted Appointments": row.get("Appointments"),
                "Forecast Period": f"{summary.get('start_date')} to {summary.get('end_date')}",
                "Expected Cost": row.get("Expected Cost"),
            }
        )
    return rows


def purchase_date_for_future_summary(summary: dict[str, Any]) -> date:
    start = parse_date(summary.get("start_date")) or date.today()
    return max(date.today(), start - timedelta(days=2))


def load_evidence_trail(forecast: dict[str, Any], item_name: str = "", limit: int = 12) -> list[dict[str, Any]]:
    item_name = clean_text(item_name)
    cache_key = json.dumps(
        {"appointment_id": forecast.get("appointment_id"), "item_name": item_name, "limit": limit},
        sort_keys=True,
    )
    cached = EVIDENCE_CACHE.get(cache_key)
    now = time.monotonic()
    if cached and now - cached[0] <= CACHE_TTL_SECONDS:
        return cached[1]
    require_graph_credentials()
    try:
        if item_name:
            rows = run_query(
                """
                MATCH (future:Appointment {appointment_id:$appointment_id})-[r:EVIDENCED_BY]->(past:Appointment)
                MATCH (past)-[:HAS_INVOICE]->(:Invoice)-[:HAS_INVOICE]->(invoice_item:Item)
                WHERE toLower(coalesce(invoice_item.line_name, "")) = toLower($item_name)
                OPTIONAL MATCH (pet:Patient)-[:HAS_APPOINTMENT]->(past)
                WITH past, pet, r,
                     collect({
                        name: invoice_item.line_name,
                        class: coalesce(invoice_item.class, ""),
                        qty: coalesce(invoice_item.total_quanity, 1.0),
                        price: coalesce(invoice_item.charged_price, invoice_item.item_unit_price, 0.0)
                     })[0..4] AS items
                RETURN
                    coalesce(r.rank, 999) + 1 AS rank,
                    past.appointment_id AS appointment_id,
                    pet.name AS pet,
                    coalesce(past.chief_complaint, past.presenting_complaint, "") AS complaint,
                    coalesce(toString(past.scheduled_date), toString(past.appointment_date), "") AS appointment_date,
                    coalesce(past.species, pet.species) AS species,
                    coalesce(past.life_stage, pet.life_stage) AS life_stage,
                    r.score AS score,
                    items AS invoice_items
                ORDER BY rank
                LIMIT $limit
                """,
                {"appointment_id": forecast["appointment_id"], "item_name": item_name, "limit": limit},
            )
        else:
            rows = run_query(
                """
                MATCH (future:Appointment {appointment_id:$appointment_id})-[r:EVIDENCED_BY]->(past:Appointment)
                OPTIONAL MATCH (pet:Patient)-[:HAS_APPOINTMENT]->(past)
                OPTIONAL MATCH (past)-[:HAS_INVOICE]->(:Invoice)-[:HAS_INVOICE]->(invoice_item:Item)
                WITH past, pet, r,
                     collect({
                        name: coalesce(invoice_item.line_name, ""),
                        class: coalesce(invoice_item.class, ""),
                        qty: coalesce(invoice_item.total_quanity, 1.0),
                        price: coalesce(invoice_item.charged_price, invoice_item.item_unit_price, 0.0)
                     }) AS raw_items
                WITH past, pet, r, [item IN raw_items WHERE item.name <> ""][0..4] AS items
                RETURN
                    coalesce(r.rank, 999) + 1 AS rank,
                    past.appointment_id AS appointment_id,
                    pet.name AS pet,
                    coalesce(past.chief_complaint, past.presenting_complaint, "") AS complaint,
                    coalesce(toString(past.scheduled_date), toString(past.appointment_date), "") AS appointment_date,
                    coalesce(past.species, pet.species) AS species,
                    coalesce(past.life_stage, pet.life_stage) AS life_stage,
                    r.score AS score,
                    items AS invoice_items
                ORDER BY rank
                LIMIT $limit
                """,
                {"appointment_id": forecast["appointment_id"], "limit": limit},
            )
    except Exception as exc:
        raise RuntimeError("Neo4j evidence query failed.") from exc
    if rows.empty:
        return []

    trail: list[dict[str, Any]] = []
    for _, row in rows.iterrows():
        items = row.get("invoice_items") or []
        item_text = "; ".join(
            f"{item.get('name')} ({item.get('class')}, qty {item.get('qty')}, {money(item.get('price'))})"
            for item in items[:4]
            if isinstance(item, dict) and item.get("name")
        )
        trail.append(
            {
                "Rank": int(row.get("rank") or len(trail) + 1),
                "Past Appointment": row.get("appointment_id"),
                "Pet": row.get("pet") or "",
                "Date": row.get("appointment_date") or "",
                "Complaint": row.get("complaint") or "",
                "Cohort": f"{row.get('species') or ''} · {row.get('life_stage') or ''}",
                "Similarity": round(float(row.get("score") or 0), 3),
                "Invoice Items": item_text or GRAPH_GAP_LABEL,
            }
        )
    EVIDENCE_CACHE[cache_key] = (now, trail)
    if len(EVIDENCE_CACHE) > MAX_PAYLOAD_CACHE_ENTRIES * 4:
        oldest_key = min(EVIDENCE_CACHE, key=lambda item: EVIDENCE_CACHE[item][0])
        EVIDENCE_CACHE.pop(oldest_key, None)
    return trail


def load_aggregate_evidence_sample(limit: int = 12) -> list[dict[str, Any]]:
    cache_key = json.dumps({"scope": "all_future", "limit": limit}, sort_keys=True)
    cached = EVIDENCE_CACHE.get(cache_key)
    now = time.monotonic()
    if cached and now - cached[0] <= CACHE_TTL_SECONDS:
        return cached[1]
    require_graph_credentials()
    rows = run_query(
        """
        MATCH (future:Appointment)
        WHERE coalesce(future.is_future, false) = true
        MATCH (future)-[r:EVIDENCED_BY]->(past:Appointment)
        OPTIONAL MATCH (future_pet:Patient)-[:HAS_APPOINTMENT]->(future)
        OPTIONAL MATCH (past_pet:Patient)-[:HAS_APPOINTMENT]->(past)
        OPTIONAL MATCH (past)-[:HAS_INVOICE]->(:Invoice)-[:HAS_INVOICE]->(invoice_item:Item)
        WITH future, future_pet, past, past_pet, r,
             collect({
                name: coalesce(invoice_item.line_name, ""),
                class: coalesce(invoice_item.class, ""),
                qty: coalesce(invoice_item.total_quanity, 1.0),
                price: coalesce(invoice_item.charged_price, invoice_item.item_unit_price, 0.0)
             }) AS raw_items
        WITH future, future_pet, past, past_pet, r, [item IN raw_items WHERE item.name <> ""][0..4] AS items
        RETURN
            future.appointment_id AS future_id,
            future_pet.name AS future_pet,
            toString(future.scheduled_date) AS future_date,
            coalesce(future.chief_complaint, future.presenting_complaint, "") AS future_complaint,
            coalesce(r.rank, 999) + 1 AS rank,
            past.appointment_id AS past_id,
            past_pet.name AS past_pet,
            coalesce(past.chief_complaint, past.presenting_complaint, "") AS past_complaint,
            coalesce(toString(past.scheduled_date), toString(past.appointment_date), "") AS past_date,
            r.score AS score,
            items AS invoice_items
        ORDER BY future.scheduled_date, future.appointment_id, rank
        LIMIT $limit
        """,
        {"limit": limit},
    )
    if rows.empty:
        return []
    trail: list[dict[str, Any]] = []
    for _, row in rows.iterrows():
        items = row.get("invoice_items") or []
        item_text = "; ".join(
            f"{item.get('name')} ({item.get('class')}, qty {item.get('qty')}, {money(item.get('price'))})"
            for item in items[:4]
            if isinstance(item, dict) and item.get("name")
        )
        trail.append(
            {
                "Future Appointment": row.get("future_id"),
                "Future Date": row.get("future_date"),
                "Future Pet": row.get("future_pet") or "",
                "Future Complaint": row.get("future_complaint") or "",
                "Evidence Rank": int(row.get("rank") or len(trail) + 1),
                "Past Appointment": row.get("past_id"),
                "Past Date": row.get("past_date") or "",
                "Past Complaint": row.get("past_complaint") or "",
                "Similarity": round(float(row.get("score") or 0), 3),
                "Invoice Items": item_text or GRAPH_GAP_LABEL,
            }
        )
    EVIDENCE_CACHE[cache_key] = (now, trail)
    return trail


def load_rollup_item_evidence(item_name: str, limit: int = 8) -> list[dict[str, Any]]:
    item_name = clean_text(item_name)
    if not item_name:
        return []
    cache_key = json.dumps({"scope": "all_future", "item_name": item_name, "limit": limit}, sort_keys=True)
    cached = EVIDENCE_CACHE.get(cache_key)
    now = time.monotonic()
    if cached and now - cached[0] <= CACHE_TTL_SECONDS:
        return cached[1]
    require_graph_credentials()
    rows = run_query(
        """
        MATCH (future:Appointment)
        WHERE coalesce(future.is_future, false) = true
        MATCH (future)-[r:EVIDENCED_BY]->(past:Appointment)
        MATCH (past)-[:HAS_INVOICE]->(:Invoice)-[:HAS_INVOICE]->(invoice_item:Item)
        WHERE toLower(coalesce(invoice_item.line_name, "")) = toLower($item_name)
        OPTIONAL MATCH (future_pet:Patient)-[:HAS_APPOINTMENT]->(future)
        OPTIONAL MATCH (past_pet:Patient)-[:HAS_APPOINTMENT]->(past)
        WITH future, future_pet, past, past_pet, r,
             collect({
                name: invoice_item.line_name,
                class: coalesce(invoice_item.class, ""),
                qty: coalesce(invoice_item.total_quanity, 1.0),
                price: coalesce(invoice_item.charged_price, invoice_item.item_unit_price, 0.0)
             })[0..4] AS items
        RETURN
            future.appointment_id AS future_id,
            future_pet.name AS future_pet,
            toString(future.scheduled_date) AS future_date,
            coalesce(future.chief_complaint, future.presenting_complaint, "") AS future_complaint,
            coalesce(r.rank, 999) + 1 AS rank,
            past.appointment_id AS past_id,
            past_pet.name AS past_pet,
            coalesce(past.chief_complaint, past.presenting_complaint, "") AS past_complaint,
            coalesce(toString(past.scheduled_date), toString(past.appointment_date), "") AS past_date,
            r.score AS score,
            items AS invoice_items
        ORDER BY future.scheduled_date, future.appointment_id, rank
        LIMIT $limit
        """,
        {"item_name": item_name, "limit": limit},
    )
    if rows.empty:
        return []
    trail: list[dict[str, Any]] = []
    for _, row in rows.iterrows():
        items = row.get("invoice_items") or []
        item_text = "; ".join(
            f"{item.get('name')} ({item.get('class')}, qty {item.get('qty')}, {money(item.get('price'))})"
            for item in items[:4]
            if isinstance(item, dict) and item.get("name")
        )
        trail.append(
            {
                "Future Appointment": row.get("future_id"),
                "Future Date": row.get("future_date"),
                "Future Pet": row.get("future_pet") or "",
                "Future Complaint": row.get("future_complaint") or "",
                "Evidence Rank": int(row.get("rank") or len(trail) + 1),
                "Past Appointment": row.get("past_id"),
                "Past Date": row.get("past_date") or "",
                "Past Complaint": row.get("past_complaint") or "",
                "Similarity": round(float(row.get("score") or 0), 3),
                "Invoice Items": item_text or GRAPH_GAP_LABEL,
            }
        )
    EVIDENCE_CACHE[cache_key] = (now, trail)
    return trail


def build_inventory_payload(params: dict[str, Any]) -> dict[str, Any]:
    vendor = normalize_vendor(params.get("vendor"))
    summary = load_kg_future_summary()
    rollup = build_inventory_rollup(vendor)
    purchase_date = purchase_date_for_future_summary(summary)
    inventory = build_inventory_from_rollup(rollup, vendor, purchase_date)
    vendor_invoice = build_vendor_invoice(inventory, vendor)
    charge_lines = build_aggregate_charge_lines(rollup)
    provenance = build_aggregate_provenance(rollup, summary)
    evidence_trail = load_aggregate_evidence_sample(limit=12)
    graph_health = strict_graph_health()
    total_qty = int(inventory["Quantity Needed"].sum()) if not inventory.empty else 0
    forecast_count = int(summary.get("forecast_visits") or 0)
    evidence_count = int(summary.get("evidence_links") or 0)
    expected_total_cost = load_kg_total_expected_billing()
    period = f"{summary.get('start_date')} to {summary.get('end_date')}"

    return json_safe({
        "clinicName": CLINIC_NAME,
        "forecastId": "all_future",
        "appointmentReason": "All upcoming appointments",
        "appointmentDate": period,
        "pet": "All scheduled patients",
        "historyStart": "",
        "historyEnd": "",
        "purchaseDate": purchase_date.isoformat(),
        "maxSimilar": 30,
        "species": "all",
        "lifeStage": "all",
        "forecastScope": "all_future_inventory",
        "includeProcedural": True,
        "minCases": MIN_SUPPORT_CASES,
        "vendor": vendor,
        "vendorOptions": VENDOR_OPTIONS,
        "vendorWebsite": vendor_metadata(vendor).get("website", ""),
        "vendorCartMode": vendor_metadata(vendor).get("cart_mode", ""),
        "forecastOptions": [],
        "selectedForecast": {
            "id": "all_future",
            "date": period,
            "pet": "All scheduled patients",
            "species": "all",
            "lifeStage": "all",
            "complaint": "All upcoming appointments",
            "expectedTotalCost": expected_total_cost,
            "stockableRows": len(inventory),
        },
        "forecastRules": [
            "Every future appointment complaint is embedded once",
            "Each future appointment is matched to invoice-backed historical appointments",
            "Historical invoice items are aggregated into clinic-level inventory demand",
            "EVIDENCED_BY edges preserve the why trail to real past visits",
            f"Inventory rows require at least {MIN_SUPPORT_CASES} supporting visits per forecast target",
        ],
        "metrics": {
            "similarAppointments": forecast_count,
            "medications": len(inventory),
            "quantityNeeded": total_qty,
            "kgEvidence": evidence_count,
            "chargeLines": len(charge_lines),
            "expectedTotalCost": round(expected_total_cost, 2),
            "forecastVisits": forecast_count,
            "fourWeekStockItems": len(rollup),
            "noiseFloor": MIN_SUPPORT_CASES,
            "graphNodes": graph_health["nodes"],
            "graphRelationships": graph_health["relationships"],
            "database": graph_health["database"],
        },
        "inventory": inventory.to_dict(orient="records"),
        "vendorInvoice": vendor_invoice,
        "similarAppointments": evidence_trail,
        "evidenceTrail": evidence_trail,
        "medicationEvidence": charge_lines,
        "chargeLines": charge_lines,
        "inventoryRollup": rollup,
        "provenance": provenance,
        "predictions": provenance,
        "suggestions": [],
    })


def payload_cache_key(params: dict[str, Any]) -> str:
    normalized = {
        "scope": "all_future_inventory",
        "vendor": normalize_vendor(params.get("vendor")),
    }
    return json.dumps(normalized, sort_keys=True)


def get_inventory_payload(params: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    key = payload_cache_key(params)
    now = time.monotonic()
    cached = PAYLOAD_CACHE.get(key)
    if cached and now - cached[0] <= CACHE_TTL_SECONDS:
        return cached[1], True

    payload = build_inventory_payload(params)
    PAYLOAD_CACHE[key] = (now, payload)
    if len(PAYLOAD_CACHE) > MAX_PAYLOAD_CACHE_ENTRIES:
        oldest_key = min(PAYLOAD_CACHE, key=lambda item: PAYLOAD_CACHE[item][0])
        PAYLOAD_CACHE.pop(oldest_key, None)
    return payload, False


def medication_quantity_lines(inventory: list[dict[str, Any]]) -> list[str]:
    return [
        f"- {row['Medication Name']}: {row['Quantity Needed']} needed by {row['Date To Purchase']}"
        for row in inventory
    ]


def supplier_price_lines(inventory: list[dict[str, Any]]) -> list[str]:
    return [
        (
            f"- {row['Medication Name']}: supplier {row['Supplier or Store']}, "
            f"expected cost {row.get('Expected Cost') or row.get('Price Paid')}"
        )
        for row in inventory
    ]


def question_wants_source(text: str) -> bool:
    return any(word in text for word in ["why", "source", "from", "matched", "similar", "evidence", "appointment", "graph", "trail"])


def matching_forecast_line(question: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    text = question.lower()
    candidates: list[dict[str, Any]] = []
    for row in payload.get("inventory", []):
        candidates.append(row)
    for row in payload.get("chargeLines", []):
        source_item = row.get("Charge Item")
        name, _unit_size = forecast_item_parts(source_item)
        candidates.append({"Medication Name": name, "_sourceItem": source_item, "_expectedUnits": row.get("Expected Units")})

    def score(candidate: dict[str, Any]) -> int:
        name = clean_text(candidate.get("Medication Name")).lower()
        source = clean_text(candidate.get("_sourceItem")).lower()
        if source and source in text:
            return len(source)
        if name and name in text:
            return len(name)
        tokens = [token for token in re.findall(r"[a-z0-9]+", name) if len(token) >= 4]
        return max((len(token) for token in tokens if token in text), default=0)

    scored = [(score(candidate), candidate) for candidate in candidates]
    scored = [item for item in scored if item[0] > 0]
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def why_answer_for_line(question: str, payload: dict[str, Any], line: dict[str, Any] | None) -> str:
    if payload.get("forecastScope") == "all_future_inventory":
        item_name = clean_text(line.get("_sourceItem") if line else "") if line else ""
        item_label = clean_text(line.get("Medication Name") if line else "")
        evidence = load_rollup_item_evidence(item_name, limit=8) if item_name else payload.get("evidenceTrail", [])[:8]
        forecast_count = payload["metrics"].get("forecastVisits", 0)
        evidence_count = payload["metrics"].get("kgEvidence", 0)
        period = payload.get("appointmentDate")

        if line:
            expected_units = line.get("_expectedUnits") or line.get("Quantity Needed")
            order_units = line.get("Quantity Needed")
            appointments = line.get("_appointments")
            appointment_text = f" It appears across {appointments} future appointment forecasts." if appointments else ""
            header = (
                f"{item_label} is on the aggregate inventory sheet because Neo4j found matching historical invoice lines "
                f"behind the upcoming appointment forecasts for {period}.{appointment_text} "
                f"The rollup expects {expected_units} units, rounded to {order_units} purchase units."
            )
        else:
            header = (
                f"This sheet is a rollup of {forecast_count} future appointments for {period}. "
                f"Darshan's pipeline wrote {evidence_count} EVIDENCED_BY links from future visits to similar historical "
                "invoice-backed visits, then the dashboard aggregates the stockable invoice items."
            )

        if not evidence:
            return header
        examples = []
        for row in evidence[:5]:
            examples.append(
                f"- Future {row.get('Future Appointment')} ({row.get('Future Date', '')}) -> "
                f"past {row.get('Past Appointment')} ({row.get('Past Date', '')}) · "
                f"{row.get('Invoice Items', GRAPH_GAP_LABEL)}"
            )
        return header + "\n\nEvidence examples:\n" + "\n".join(examples)

    appointment = {
        "appointment_id": payload.get("forecastId"),
        "evidence": [row.get("Past Appointment") for row in payload.get("evidenceTrail", []) if row.get("Past Appointment")],
    }
    item_name = clean_text(line.get("_sourceItem") if line else "") if line else ""
    item_label = clean_text(line.get("Medication Name") if line else "")
    evidence = load_evidence_trail(appointment, item_name, limit=8) if item_name else payload.get("evidenceTrail", [])[:8]
    similar_count = payload["metrics"].get("similarAppointments", 0)
    complaint = payload.get("appointmentReason")
    cohort = f"{payload.get('species')} · {payload.get('lifeStage')}"

    if line:
        support = ""
        prevalence = parse_number(line.get("_prevalence"))
        if prevalence is not None and similar_count:
            support = f" It appears in about {int(round(prevalence * similar_count))} of {similar_count} similar invoice-backed visits."
        expected_units = line.get("_expectedUnits") or line.get("Quantity Needed")
        header = (
            f"{item_label} is on the sheet because the pipeline matched this future appointment "
            f"('{complaint}') to {similar_count} similar historical appointments in the {cohort} cohort, "
            f"then aggregated the real invoice items from those visits.{support} Expected units: {expected_units}."
        )
    else:
        header = (
            f"This sheet is based on {similar_count} similar historical appointments for '{complaint}' "
            f"in the {cohort} cohort. The generated pipeline writes EVIDENCED_BY edges from the future appointment "
            "to those past visits, then reads the past invoice items."
        )

    if not evidence:
        return header
    examples = []
    for row in evidence[:5]:
        examples.append(
            f"- #{row.get('Rank')}: {row.get('Past Appointment')} · {row.get('Date', '')} · "
            f"{row.get('Complaint', '')} · {row.get('Invoice Items', GRAPH_GAP_LABEL)}"
        )
    return header + "\n\nEvidence examples:\n" + "\n".join(examples)


def fast_inventory_answer(question: str, payload: dict[str, Any]) -> str | None:
    inventory = payload["inventory"]
    if not inventory:
        return "No medication inventory rows are available for the current Neo4j forecast."

    text = question.lower()
    total_qty = payload["metrics"].get("quantityNeeded", 0)
    med_count = payload["metrics"].get("medications", len(inventory))
    similar_count = payload["metrics"].get("similarAppointments", 0)
    evidence_count = payload["metrics"].get("kgEvidence", 0)
    purchase_date = payload["purchaseDate"]
    appointment_date = payload["appointmentDate"]
    appointment_reason = payload["appointmentReason"]
    species = payload.get("species", "all")
    life_stage = payload.get("lifeStage", "all")
    is_aggregate = payload.get("forecastScope") == "all_future_inventory"

    wants_supplier = any(word in text for word in ["supplier", "vendor", "store", "price", "cost"])
    wants_quantity = any(
        word in text
        for word in ["medication", "medicine", "medications", "quantity", "qty", "need", "needed", "order", "purchase", "buy", "stock"]
    )
    wants_source = question_wants_source(text)
    wants_date = any(word in text for word in ["when", "date", "purchase by", "buy by"])
    wants_codex = any(word in text for word in ["codex", "deep", "deeper", "analyze", "analysis"])

    if wants_codex:
        return None

    if wants_supplier:
        return (
            f"Vendor selected: {payload.get('vendor', KG_VENDOR_OPTION)}. The price column shows expected historical "
            "invoice cost from the matched past visits; exact vendor purchase prices still need the vendor quote/cart.\n\n"
            + "\n".join(supplier_price_lines(inventory[:12]))
        )

    if wants_source:
        return why_answer_for_line(question, payload, matching_forecast_line(question, payload))

    if wants_date:
        if is_aggregate:
            return (
                f"Purchase by {purchase_date} for the upcoming appointment forecast period {appointment_date}.\n\n"
                + "\n".join(medication_quantity_lines(inventory))
            )
        return (
            f"Purchase by {purchase_date} for the {appointment_date} appointment.\n\n"
            + "\n".join(medication_quantity_lines(inventory))
        )

    if wants_quantity or len(text.split()) <= 6:
        if is_aggregate:
            forecast_count = payload["metrics"].get("forecastVisits", 0)
            return (
                f"For all upcoming appointments in {appointment_date}, prepare {med_count} medication/supply rows "
                f"with {total_qty} purchase units. The forecast covers {forecast_count} future appointments and "
                f"{evidence_count} KG evidence links. Purchase by {purchase_date}.\n\n"
                + "\n".join(medication_quantity_lines(inventory[:14]))
            )
        return (
            f"For {payload.get('pet', 'this patient')} on {appointment_date}, prepare {med_count} stockable medication/supply rows "
            f"with {total_qty} purchase units. The forecast is based on {similar_count} similar invoice-backed appointments "
            f"and {evidence_count} KG evidence links. Purchase by {purchase_date}.\n\n"
            + "\n".join(medication_quantity_lines(inventory[:14]))
        )

    return None


def excel_column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def dataframe_to_xlsx_bytes(df: pd.DataFrame) -> bytes:
    rows = [df.columns.tolist()] + df.fillna("").astype(str).values.tolist()
    sheet_rows: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for col_index, value in enumerate(row, start=1):
            cell_ref = f"{excel_column_name(col_index)}{row_index}"
            cells.append(f'<c r="{cell_ref}" t="inlineStr"><is><t>{xml_escape(str(value))}</t></is></c>')
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    worksheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<cols>'
        + "".join(f'<col min="{i}" max="{i}" width="20" customWidth="1"/>' for i in range(1, len(rows[0]) + 1))
        + '</cols><sheetData>'
        + "".join(sheet_rows)
        + "</sheetData></worksheet>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Medication Inventory" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>'
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)
    return output.getvalue()


def pdf_escape(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def text_lines_to_pdf_bytes(lines: list[str]) -> bytes:
    page_width = 792
    page_height = 612
    margin_x = 44
    margin_y = 42
    line_height = 13
    lines_per_page = int((page_height - margin_y * 2) / line_height)
    pages = [lines[i : i + lines_per_page] for i in range(0, len(lines), lines_per_page)] or [[]]
    objects: list[bytes] = [b""] * (3 + len(pages) * 2)

    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[2] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    page_ids: list[int] = []

    for page_index, page_lines in enumerate(pages):
        page_id = 4 + page_index * 2
        content_id = page_id + 1
        page_ids.append(page_id)
        commands = ["BT", "/F1 10 Tf", f"{line_height} TL", f"{margin_x} {page_height - margin_y} Td"]
        for line in page_lines:
            commands.append(f"({pdf_escape(line)}) Tj")
            commands.append("T*")
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1", "replace")
        objects[content_id - 1] = b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        objects[page_id - 1] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_width} {page_height}] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode("latin-1")

    objects[1] = (
        f"<< /Type /Pages /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] "
        f"/Count {len(page_ids)} >>"
    ).encode("latin-1")

    output = io.BytesIO()
    output.write(b"%PDF-1.4\n")
    offsets = [0]
    for object_id, content in enumerate(objects, start=1):
        offsets.append(output.tell())
        output.write(f"{object_id} 0 obj\n".encode())
        output.write(content)
        output.write(b"\nendobj\n")
    xref_offset = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n".encode())
    output.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode())
    output.write((f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF").encode())
    return output.getvalue()


def inventory_pdf_bytes(payload: dict[str, Any]) -> bytes:
    inventory = payload["inventory"]
    is_aggregate = payload.get("forecastScope") == "all_future_inventory"
    lines = [
        "Medication Inventory Tracker",
        f"Clinic: {payload['clinicName']}",
        f"Forecast: {'All upcoming appointments' if is_aggregate else payload['appointmentReason']}",
        f"{'Forecast Period' if is_aggregate else 'Appointment Date'}: {payload['appointmentDate']}",
        f"Purchase By: {payload['purchaseDate']}",
        f"Vendor: {payload.get('vendor', KG_VENDOR_OPTION)}",
        "",
    ]
    if not inventory:
        lines.append("No medication inventory rows were predicted for this forecast.")
    for index, row in enumerate(inventory, start=1):
        lines.append(f"{index}. {row['Medication Name']}")
        detail = (
            f"Product Type: {row['Product Type']} | Quantity Needed: {row['Quantity Needed']} | "
            f"Expected Units: {row.get('Expected Units', '')} | Unit Size: {row['Unit Size']} | "
            f"Forecasted Appointments: {row.get('Forecasted Appointments', '')}"
        )
        purchase = (
            f"Date To Purchase: {row['Date To Purchase']} | Supplier or Store: {row['Supplier or Store']} | "
            f"Expected Cost: {row.get('Expected Cost') or row.get('Price Paid')} | Cost Source: {row.get('Cost Source', '')}"
        )
        lines.extend(textwrap.wrap(detail, width=102))
        lines.extend(textwrap.wrap(purchase, width=102))
        lines.append("")
    return text_lines_to_pdf_bytes(lines)


def inventory_df_from_payload(payload: dict[str, Any]) -> pd.DataFrame:
    visible_columns = [
        "Medication Name",
        "Product Type",
        "Quantity Needed",
        "Expected Units",
        "Unit Size",
        "Forecasted Appointments",
        "Date To Purchase",
        "Supplier or Store",
        "Expected Cost",
    ]
    rows = []
    for row in payload["inventory"]:
        rows.append({column: row.get(column, "") for column in visible_columns})
    return pd.DataFrame(rows, columns=visible_columns)


def fallback_chat_answer(question: str, payload: dict[str, Any]) -> str:
    inventory = payload["inventory"]
    if not inventory:
        return "No medication inventory rows are available for the current Neo4j forecast."
    text = question.lower()
    if question_wants_source(text):
        return why_answer_for_line(question, payload, matching_forecast_line(question, payload))
    if any(word in text for word in ["supplier", "vendor", "store", "price", "cost"]):
        return f"Vendor selected: {payload.get('vendor', KG_VENDOR_OPTION)}. Exact vendor prices need quote/cart confirmation."
    if any(word in text for word in ["qty", "quantity", "order", "purchase", "needed"]):
        return "Quantity needed: " + "; ".join(
            f"{row['Medication Name']}: {row['Quantity Needed']} by {row['Date To Purchase']}"
            for row in inventory[:8]
        )
    return "Inventory rows: " + "; ".join(
        f"{row['Medication Name']} quantity {row['Quantity Needed']}, supplier {row['Supplier or Store']}, expected cost {row.get('Expected Cost') or row.get('Price Paid')}"
        for row in inventory[:8]
    )


def build_vendor_cart_response(
    payload: dict[str, Any],
    item_limit: int | None = None,
    automate: bool = False,
    visible: bool = False,
) -> dict[str, Any]:
    invoice = payload.get("vendorInvoice") or []
    if item_limit is None or item_limit <= 0:
        items = invoice
    else:
        item_limit = max(1, min(len(invoice), item_limit))
        items = invoice[:item_limit]
    vendor = payload.get("vendor", "Amazon")
    metadata = vendor_metadata(vendor)
    response: dict[str, Any] = {
        "vendor": vendor,
        "website": metadata.get("website", ""),
        "cartMode": metadata.get("cart_mode", ""),
        "requestedItems": len(items),
        "totalInvoiceItems": len(invoice),
        "items": items,
        "headless": automate and not visible,
        "visible": visible,
        "status": "draft_ready",
        "message": f"Cart draft created for {len(items)} {vendor} invoice items.",
    }

    if not items:
        response.update({"status": "empty", "message": "No invoice rows are available for the selected vendor."})
        return response
    if not automate:
        return response
    if vendor == KG_VENDOR_OPTION:
        response.update({"status": "unsupported_vendor", "message": "KG supplier rows do not have a vendor website to automate."})
        return response
    if vendor != "Med-Vet International":
        response.update(
            {
                "status": "manual_review",
                "message": (
                    f"{vendor} cart automation is prepared as search links only. Automatic add-to-cart is enabled "
                    "for Med-Vet International first because other vendors often require login, account pricing, or CAPTCHA."
                ),
            }
        )
        return response

    response.update(run_medvet_cart(items, metadata, visible=visible))
    return response


def run_medvet_cart(items: list[dict[str, Any]], metadata: dict[str, str], visible: bool = False) -> dict[str, Any]:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "status": "dependency_missing",
            "message": "Playwright is not installed yet. The app created the Med-Vet cart draft and search links.",
        }

    results: list[dict[str, Any]] = []
    browser_closed = False
    chrome_path = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    launch_args: dict[str, Any] = {"headless": not visible}
    if visible:
        launch_args["slow_mo"] = 350
    if chrome_path.exists():
        launch_args["executable_path"] = str(chrome_path)

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(**launch_args)
            context = browser.new_context()
            page = context.new_page()
            if visible:
                page.bring_to_front()
            page.set_default_timeout(3000)
            page.set_default_navigation_timeout(18000)
            initial_cart_count: int | None = None

            def get_cart_count() -> int | None:
                count_text = join_unique(
                    pd.Series(
                        page.locator(".header-mini-cart-menu-cart-legend").evaluate_all(
                            "els => els.map((el) => (el.innerText || el.textContent || '').trim())"
                        )
                    ),
                    1,
                )
                count = parse_number(count_text)
                return int(count) if count is not None else None

            def wait_for_cart_increase(previous_count: int | None, timeout_seconds: float = 15.0) -> int | None:
                deadline = time.monotonic() + timeout_seconds
                latest = get_cart_count()
                while time.monotonic() < deadline:
                    if previous_count is not None and latest is not None and latest > previous_count:
                        return latest
                    page.wait_for_timeout(500)
                    latest = get_cart_count()
                return latest

            def dismiss_medvet_popup() -> None:
                close = page.locator('button.klaviyo-close-form[aria-label="Close dialog"]').first
                try:
                    if close.count() and close.is_visible(timeout=600):
                        close.click(timeout=3000, force=True)
                        page.wait_for_timeout(500)
                except Exception:
                    pass

            def click_first_visible_add_to_cart() -> bool:
                dismiss_medvet_popup()
                locators = [
                    page.locator('button[data-type="add-to-cart"], button.cart-add-to-cart-button-button'),
                    page.get_by_role("button", name=re.compile("add to cart", re.I)),
                    page.locator("button, a").filter(has_text=re.compile("add to cart", re.I)),
                    page.locator('input[type="submit"][value*="Add" i], input[type="button"][value*="Add" i]'),
                ]
                for locator in locators:
                    for index in range(min(locator.count(), 4)):
                        candidate = locator.nth(index)
                        try:
                            if not candidate.is_visible(timeout=300) or not candidate.is_enabled(timeout=300):
                                continue
                            candidate.scroll_into_view_if_needed(timeout=3000)
                            candidate.click(timeout=9000)
                            return True
                        except Exception:
                            continue
                return False

            def is_browser_closed_error(exc: Exception) -> bool:
                text = str(exc).lower()
                return "target page, context or browser has been closed" in text or "browser has been closed" in text

            for index, item in enumerate(items):
                result = {
                    "Medication Name": item["Medication Name"],
                    "Quantity": item["Quantity"],
                    "Search URL": item["Search URL"],
                }
                try:
                    page.goto(item["Search URL"] or metadata["website"], wait_until="domcontentloaded", timeout=18000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=2500)
                    except PlaywrightTimeoutError:
                        pass
                    before_count = get_cart_count()
                    if initial_cart_count is None and before_count is not None:
                        initial_cart_count = before_count
                    if click_first_visible_add_to_cart():
                        after_count = wait_for_cart_increase(before_count)
                        if before_count is not None and after_count is not None and after_count > before_count:
                            result.update(
                                {
                                    "status": "added_to_cart",
                                    "detail": f"Med-Vet cart count changed from {before_count} to {after_count}.",
                                }
                            )
                        else:
                            result.update(
                                {
                                    "status": "click_no_cart_change",
                                    "detail": "Clicked Add To Cart, but Med-Vet did not report a cart-count increase.",
                                }
                            )
                    else:
                        result.update({"status": "not_added", "detail": "No visible add-to-cart control was found on the search page."})
                except PlaywrightTimeoutError as exc:
                    result.update({"status": "not_confirmed", "detail": "Med-Vet did not confirm this item before the wait expired."})
                except Exception as exc:
                    if is_browser_closed_error(exc):
                        result.update({"status": "cart_stopped", "detail": "The browser was closed before this item finished."})
                        browser_closed = True
                    else:
                        result.update({"status": "not_confirmed", "detail": "Med-Vet did not confirm this item."})
                results.append(result)
                if browser_closed:
                    remaining = len(items) - index - 1
                    if remaining > 0:
                        results.append(
                            {
                                "Medication Name": f"{remaining} remaining item{'s' if remaining != 1 else ''}",
                                "Quantity": remaining,
                                "status": "not_processed",
                                "detail": "The cart run stopped before these items were processed.",
                            }
                        )
                    break
            final_cart_count = None if browser_closed else get_cart_count()
            if visible and not browser_closed:
                page.wait_for_timeout(12000)
            if not browser_closed:
                browser.close()
    except Exception as exc:
        if results:
            return {
                "status": "cart_partial",
                "message": "Med-Vet cart run stopped before every item could be confirmed.",
                "results": results,
            }
        return {"status": "cart_stopped", "message": "Med-Vet cart run stopped before items could be added.", "results": []}

    confirmed_added = sum(1 for result in results if result.get("status") == "added_to_cart")
    if initial_cart_count is not None and final_cart_count is not None:
        total_added = max(0, final_cart_count - initial_cart_count)
        late_to_confirm = min(total_added, len(items)) - confirmed_added
        for result in results:
            if late_to_confirm <= 0:
                break
            if result.get("status") == "click_no_cart_change":
                result.update(
                    {
                        "status": "added_to_cart_late",
                        "detail": "Med-Vet cart count confirmed this add after the per-item wait.",
                    }
                )
                late_to_confirm -= 1

    added = sum(1 for result in results if result.get("status") == "added_to_cart")
    added += sum(1 for result in results if result.get("status") == "added_to_cart_late")
    return {
        "status": "cart_partial" if browser_closed else "cart_complete",
        "message": (
            f"Med-Vet cart run finished. Added {added} of {len(items)} items to the cart."
            if not browser_closed
            else f"Med-Vet cart run stopped. Added {added} of {len(items)} items before it stopped."
        ),
        "results": results,
    }


def call_codex_cli(question: str, payload: dict[str, Any], history: list[dict[str, str]]) -> tuple[str, str]:
    context = {
        "clinic": payload["clinicName"],
        "forecastId": payload.get("forecastId"),
        "pet": payload.get("pet"),
        "appointmentReason": payload["appointmentReason"],
        "appointmentDate": payload["appointmentDate"],
        "purchaseDate": payload["purchaseDate"],
        "species": payload["species"],
        "lifeStage": payload["lifeStage"],
        "forecastScope": payload.get("forecastScope", "future appointment complaint -> similar historical invoice-backed appointments"),
        "vendor": payload.get("vendor", KG_VENDOR_OPTION),
        "vendorOptions": payload.get("vendorOptions", VENDOR_OPTIONS),
        "vendorInvoice": payload.get("vendorInvoice", [])[:20],
        "forecastRules": payload["forecastRules"],
        "metrics": payload["metrics"],
        "inventory": payload["inventory"][:20],
        "chargeLines": payload.get("chargeLines", [])[:40],
        "inventoryRollup": payload.get("inventoryRollup", [])[:20],
        "provenance": payload["provenance"][:20],
        "evidenceTrail": payload.get("evidenceTrail", [])[:12],
    }
    prompt = f"""
You are the medication inventory assistant for {CLINIC_NAME}.

Answer the user's question using only the Neo4j-derived forecast and evidence context below.
This dashboard uses Darshan's pipeline: future appointment complaints are embedded, similar historical appointments
with real invoices are retrieved, invoice line items are aggregated into inventory demand, and EVIDENCED_BY edges explain the "why" trail.
Do not invent supplier, price, stock, or vendor values. If a field says "{GRAPH_GAP_LABEL}", say it is missing or not loaded.
Keep the answer short and operational.

Recent chat:
{json.dumps(history[-6:], indent=2)}

KG context:
{json.dumps(context, indent=2, default=str)}

User question: {question}
""".strip()

    with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False) as output_file:
        output_path = output_file.name
    try:
        command = [
            "codex",
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--output-last-message",
            output_path,
        ]
        codex_model = clean_text(os.getenv("CODEX_CHAT_MODEL") or os.getenv("CODEX_MODEL"))
        if codex_model:
            command.extend(["--model", codex_model])
        command.append("-")
        result = subprocess.run(
            command,
            input=prompt,
            text=True,
            cwd=str(BASE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=90,
            check=False,
        )
        answer = Path(output_path).read_text().strip()
        if result.returncode != 0 or not answer:
            fallback = fallback_chat_answer(question, payload)
            detail = (result.stderr or result.stdout).strip()[-500:]
            return fallback, f"fallback: codex exit {result.returncode}; {detail}"
        return answer, "codex"
    except (subprocess.TimeoutExpired, OSError) as exc:
        return fallback_chat_answer(question, payload), f"fallback: {exc}"
    finally:
        Path(output_path).unlink(missing_ok=True)


async def api_bootstrap(_request) -> JSONResponse:
    options = load_kg_forecast_options()
    dates = [parse_date(option.get("date")) for option in options]
    dates = [item for item in dates if item is not None]
    min_date = min(dates) if dates else date.today()
    max_date = max(dates) if dates else date.today() + timedelta(days=28)
    species = sorted({clean_text(option.get("species")) for option in options if clean_text(option.get("species"))})
    life_stages: dict[str, list[str]] = {"all": ["all"]}
    for option in options:
        species_name = clean_text(option.get("species"))
        stage = clean_text(option.get("lifeStage"))
        if species_name and stage:
            life_stages.setdefault(species_name, ["all"])
            if stage not in life_stages[species_name]:
                life_stages[species_name].append(stage)
    return JSONResponse(
        {
            "clinicName": CLINIC_NAME,
            "forecastOptions": options,
            "defaultForecastId": options[0]["id"] if options else "",
            "suggestions": [option["complaint"] for option in options[:30]],
            "species": ["all", *species] if species else ["all", "canine", "feline"],
            "lifeStages": life_stages,
            "minHistoryDate": min_date.isoformat(),
            "maxHistoryDate": max_date.isoformat(),
            "defaultHistoryStart": min_date.isoformat(),
            "defaultAppointmentDate": options[0]["date"] if options else (date.today() + timedelta(days=7)).isoformat(),
            "graph": strict_graph_health(),
            "vendorOptions": VENDOR_OPTIONS,
        }
    )


async def api_inventory(request) -> JSONResponse:
    payload, _cached = get_inventory_payload(await request.json())
    return JSONResponse(payload)


async def api_chat(request) -> JSONResponse:
    started = time.monotonic()
    body = await request.json()
    question = clean_text(body.get("message") or body.get("question"))
    if not question:
        return JSONResponse({"answer": "Ask a question about the medication inventory sheet.", "source": "validation"})
    payload, cached = get_inventory_payload(body.get("filters") or {})
    answer = fast_inventory_answer(question, payload)
    if answer is not None:
        return JSONResponse(
            {
                "answer": answer,
                "source": "kg-fast-cache" if cached else "kg-fast",
                "latencyMs": int((time.monotonic() - started) * 1000),
                "inventory": payload["inventory"],
                "metrics": payload["metrics"],
            }
        )
    answer, source = call_codex_cli(question, payload, body.get("history") or [])
    return JSONResponse(
        {
            "answer": answer,
            "source": source,
            "latencyMs": int((time.monotonic() - started) * 1000),
            "inventory": payload["inventory"],
            "metrics": payload["metrics"],
        }
    )


async def api_vendor_cart(request) -> JSONResponse:
    body = await request.json()
    payload, _cached = get_inventory_payload(body.get("filters") or body)
    item_limit_value = parse_number(body.get("itemLimit"))
    item_limit = int(item_limit_value) if item_limit_value is not None else None
    automate = bool(body.get("automate") or body.get("headless"))
    visible = bool(body.get("visible"))
    if automate:
        result = await asyncio.to_thread(build_vendor_cart_response, payload, item_limit, True, visible)
    else:
        result = build_vendor_cart_response(payload, item_limit, False, False)
    return JSONResponse(json_safe(result))


async def api_export(request) -> Response:
    export_type = request.path_params["export_type"]
    payload, _cached = get_inventory_payload(await request.json())
    stem = f"florida_plantation_medication_inventory_{slugify(payload.get('vendor'))}_{slugify(payload['appointmentDate'])}"
    df = inventory_df_from_payload(payload)
    if export_type == "csv":
        buffer = io.StringIO()
        df.to_csv(buffer, index=False)
        return Response(
            buffer.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{stem}.csv"'},
        )
    if export_type == "xlsx":
        return Response(
            dataframe_to_xlsx_bytes(df),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{stem}.xlsx"'},
        )
    if export_type == "pdf":
        return Response(
            inventory_pdf_bytes(payload),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{stem}.pdf"'},
        )
    return JSONResponse({"error": "Unsupported export type"}, status_code=404)


async def index(_request) -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


routes = [
    Route("/api/bootstrap", api_bootstrap, methods=["GET"]),
    Route("/api/inventory", api_inventory, methods=["POST"]),
    Route("/api/chat", api_chat, methods=["POST"]),
    Route("/api/vendor-cart", api_vendor_cart, methods=["POST"]),
    Route("/api/export/{export_type}", api_export, methods=["POST"]),
    Route("/", index, methods=["GET"]),
]

app = Starlette(routes=routes)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")
