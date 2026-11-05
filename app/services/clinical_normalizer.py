import re
from typing import Iterable, List

from app.models import DischargeAnalysisResponse, MedicationInstruction


def _key(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").casefold()).strip()


def merge_duplicate_medications(medicines: Iterable[MedicationInstruction]) -> List[MedicationInstruction]:
    """Merge only records that explicitly agree on identity, strength, and order."""
    merged: List[MedicationInstruction] = []
    positions = {}
    for medicine in medicines:
        identity = _key(medicine.ingredient or medicine.name)
        verbatim_order = _key(medicine.verbatim_order)
        key = (
            identity,
            _key(medicine.dosage),
            _key(medicine.route),
            _key(medicine.frequency),
            medicine.frequency_type,
            _key(medicine.when_to_take),
            _key(medicine.duration),
            _key(medicine.maximum_limit),
            _key(medicine.continuation_status),
            verbatim_order,
        )
        # Do not collapse incomplete records. A verbatim order and identity/strength
        # are required, and every extracted instruction must agree.
        if not identity or not key[1] or not verbatim_order:
            merged.append(medicine)
            continue
        if key not in positions:
            positions[key] = len(merged)
            merged.append(medicine)
            continue
        current = merged[positions[key]]
        current.duplicate_count += medicine.duplicate_count
        current.source_references = list(dict.fromkeys(current.source_references + medicine.source_references))
        current.conflicts = list(dict.fromkeys(current.conflicts + medicine.conflicts))
        current.field_states.update(medicine.field_states)
        if medicine.tips_or_warnings and medicine.tips_or_warnings not in (current.tips_or_warnings or ""):
            current.tips_or_warnings = "; ".join(filter(None, [current.tips_or_warnings, medicine.tips_or_warnings]))
    return merged


def normalize_analysis(analysis: DischargeAnalysisResponse) -> DischargeAnalysisResponse:
    review_items = list(analysis.missing_or_ambiguous_information)
    for medicine in analysis.medication_instructions:
        for field in ("name", "dosage", "route", "frequency", "when_to_take", "duration"):
            if not getattr(medicine, field):
                medicine.field_states.setdefault(field, "missing")
        if any(value == "conflicting" for value in medicine.field_states.values()):
            medicine.state = "conflicting"
        elif any(value == "ambiguous" for value in medicine.field_states.values()):
            medicine.state = "ambiguous"
        for field, value in medicine.field_states.items():
            if value in ("missing", "ambiguous", "conflicting"):
                label = f"{medicine.name or 'Medication'} — {field.replace('_', ' ')}: {value} in the discharge summary."
                if label not in review_items:
                    review_items.append(label)
    for task in analysis.follow_up_tasks:
        if task.type == "appointment":
            if not task.date_time:
                task.field_states.setdefault("date", "missing")
            if not (task.appointment_time or task.time_of_day):
                task.field_states.setdefault("time", "missing")
            if any(value == "conflicting" for value in task.field_states.values()):
                task.state = "conflicting"
            elif any(value == "ambiguous" for value in task.field_states.values()):
                task.state = "ambiguous"
            for field, value in task.field_states.items():
                if value in ("missing", "ambiguous", "conflicting"):
                    label = f"{task.title} — {field}: {value} in the discharge summary."
                    if label not in review_items:
                        review_items.append(label)
    analysis.missing_or_ambiguous_information = review_items
    analysis.medication_instructions = merge_duplicate_medications(analysis.medication_instructions)
    return analysis
