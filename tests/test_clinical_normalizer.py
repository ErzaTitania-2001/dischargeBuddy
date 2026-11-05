from app.models import MedicationInstruction
from app.services.clinical_normalizer import merge_duplicate_medications


def test_only_matching_medicine_orders_are_deduplicated():
    medicines = [
        MedicationInstruction(
            name="Drug A", ingredient="Ingredient A", dosage="10 mg", frequency="daily",
            verbatim_order="Take one tablet daily", source_references=["Page 1"]
        ),
        MedicationInstruction(
            name="Drug A", ingredient="Ingredient A", dosage="10 mg", frequency="daily",
            verbatim_order="Take one tablet daily", source_references=["Page 2"]
        ),
        MedicationInstruction(
            name="Drug A", ingredient="Ingredient A", dosage="20 mg", frequency="daily",
            verbatim_order="Take one tablet daily", source_references=["Page 3"]
        )
    ]

    merged = merge_duplicate_medications(medicines)
    assert len(merged) == 2
    assert merged[0].duplicate_count == 2
    assert merged[0].source_references == ["Page 1", "Page 2"]
    assert merged[1].dosage == "20 mg"
