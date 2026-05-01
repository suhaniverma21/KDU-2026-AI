from __future__ import annotations

from pathlib import Path

from app.phase4 import Phase4Harness, build_sample_transaction_document


def test_case_facts_preserve_transactional_details(tmp_path: Path) -> None:
    harness = Phase4Harness(db_path=tmp_path / "memory.db")
    result = harness.run(
        document=build_sample_transaction_document(repetitions=5),
        follow_up_messages=["okay", "cool"],
    )

    assert result.case_facts["customer_name"] == "Jane Doe"
    assert result.case_facts["transactions"][0]["transaction_id"] == "TXN-10045"
    assert result.case_facts["transactions"][0]["order_id"] == "ORD-77881"
    assert result.case_facts["transactions"][0]["amount"] == 249.99
    assert result.case_facts["banking_details"]["routing_number"] == "123456789"


def test_missing_cvv_creates_flag_and_requires_user_input(tmp_path: Path) -> None:
    harness = Phase4Harness(db_path=tmp_path / "memory.db")
    result = harness.run(
        document=build_sample_transaction_document(repetitions=3),
        follow_up_messages=["okay", "cool"],
    )

    flagged_fields = [flag["field"] for flag in result.flags]
    assert "cvv" in flagged_fields
    assert result.session_state == "requires_user_input"
    assert result.case_facts["required_fields_status"]["cvv"] == "missing"


def test_persisted_snapshot_survives_compaction_and_noise(tmp_path: Path) -> None:
    harness = Phase4Harness(db_path=tmp_path / "memory.db")
    result = harness.run(
        document=build_sample_transaction_document(repetitions=4),
        follow_up_messages=["okay", "cool", "nice"],
    )

    snapshot = result.persisted_snapshot
    assert snapshot["case_facts"]["transactions"][1]["order_id"] == "ORD-77882"
    assert snapshot["case_facts"]["banking_details"]["account_number"] == "987654321"
    assert "Ignored 3 low-signal follow-up messages" in snapshot["compact_summary"]
    assert snapshot["session_state"] == "requires_user_input"


def test_logs_include_memory_compaction_and_missing_field_events(tmp_path: Path) -> None:
    harness = Phase4Harness(db_path=tmp_path / "memory.db")
    result = harness.run(
        document=build_sample_transaction_document(repetitions=2),
        follow_up_messages=["okay"],
    )

    event_types = [entry["event_type"] for entry in result.logs]
    assert "memory_compacted" in event_types
    assert "missing_required_field" in event_types
