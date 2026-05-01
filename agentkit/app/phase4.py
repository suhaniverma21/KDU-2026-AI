from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from app.logging_utils import StructuredLogger
from app.models import LogEvent


@dataclass(slots=True)
class FlagRecord:
    flag_type: str
    field: str
    status: str
    session_state: str


@dataclass(slots=True)
class Phase4Outcome:
    session_id: str
    input_document_length: int
    compact_summary: str
    case_facts: dict[str, object]
    flags: list[dict[str, str]]
    session_state: str
    follow_up_messages: list[str]
    persisted_snapshot: dict[str, object]
    log_path: str | None
    db_path: str
    logs: list[dict[str, object]] = field(default_factory=list)


class SessionMemoryStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _initialize(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_snapshots (
                    session_id TEXT PRIMARY KEY,
                    compact_summary TEXT NOT NULL,
                    case_facts_json TEXT NOT NULL,
                    session_state TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS flags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    flag_type TEXT NOT NULL,
                    field_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    session_state TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def save_snapshot(
        self,
        session_id: str,
        compact_summary: str,
        case_facts: dict[str, object],
        session_state: str,
    ) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO memory_snapshots (
                    session_id, compact_summary, case_facts_json, session_state
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    compact_summary=excluded.compact_summary,
                    case_facts_json=excluded.case_facts_json,
                    session_state=excluded.session_state
                """,
                (
                    session_id,
                    compact_summary,
                    json.dumps(case_facts),
                    session_state,
                ),
            )
            conn.commit()

    def replace_flags(self, session_id: str, flags: list[FlagRecord]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM flags WHERE session_id = ?", (session_id,))
            conn.executemany(
                """
                INSERT INTO flags (
                    session_id, flag_type, field_name, status, session_state
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        session_id,
                        item.flag_type,
                        item.field,
                        item.status,
                        item.session_state,
                    )
                    for item in flags
                ],
            )
            conn.commit()

    def load_snapshot(self, session_id: str) -> dict[str, object]:
        with sqlite3.connect(self.db_path) as conn:
            snapshot_row = conn.execute(
                """
                SELECT compact_summary, case_facts_json, session_state
                FROM memory_snapshots
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
            flag_rows = conn.execute(
                """
                SELECT flag_type, field_name, status, session_state
                FROM flags
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (session_id,),
            ).fetchall()

        if snapshot_row is None:
            return {}

        return {
            "compact_summary": snapshot_row[0],
            "case_facts": json.loads(snapshot_row[1]),
            "session_state": snapshot_row[2],
            "flags": [
                {
                    "flag_type": row[0],
                    "field": row[1],
                    "status": row[2],
                    "session_state": row[3],
                }
                for row in flag_rows
            ],
        }


class CaseFactsExtractor:
    transaction_pattern = re.compile(
        r"Transaction ID:\s*(?P<transaction_id>TXN-\d+).*?"
        r"Order ID:\s*(?P<order_id>ORD-\d+).*?"
        r"Amount:\s*\$(?P<amount>\d+(?:\.\d{2})?).*?"
        r"Currency:\s*(?P<currency>[A-Z]{3}).*?"
        r"Date:\s*(?P<date>\d{4}-\d{2}-\d{2})",
        re.DOTALL,
    )

    def extract(self, document: str) -> dict[str, object]:
        customer_name = self._extract_customer_name(document)
        banking_details = {
            "routing_number": self._extract_field(document, "Routing Number"),
            "account_number": self._extract_field(document, "Account Number"),
            "cvv": self._extract_field(document, "CVV"),
        }
        transactions = []
        for match in self.transaction_pattern.finditer(document):
            amount_text = match.group("amount")
            transactions.append(
                {
                    "transaction_id": match.group("transaction_id"),
                    "order_id": match.group("order_id"),
                    "amount": float(amount_text),
                    "currency": match.group("currency"),
                    "date": match.group("date"),
                }
            )

        required_fields_status = {
            key: "present" if value else "missing"
            for key, value in banking_details.items()
        }

        return {
            "customer_name": customer_name,
            "transactions": transactions,
            "banking_details": banking_details,
            "required_fields_status": required_fields_status,
            "numerical_data": self._extract_numerical_data(document),
        }

    def _extract_customer_name(self, document: str) -> str | None:
        match = re.search(r"Customer Name:\s*(.+)", document)
        return match.group(1).strip() if match else None

    def _extract_field(self, document: str, label: str) -> str | None:
        match = re.search(rf"{re.escape(label)}:\s*([A-Za-z0-9-]+)", document)
        return match.group(1).strip() if match else None

    def _extract_numerical_data(self, document: str) -> list[str]:
        return re.findall(r"\b\d+(?:\.\d{2})?\b", document)


class MemoryCompactor:
    def build_summary(self, case_facts: dict[str, object], follow_up_messages: list[str]) -> str:
        transactions = case_facts["transactions"]
        transaction_count = len(transactions)
        total_amount = sum(item["amount"] for item in transactions)
        latest_order = transactions[-1]["order_id"] if transactions else "unknown"
        return (
            f"Tracked {transaction_count} transactions for "
            f"{case_facts.get('customer_name') or 'unknown customer'}, totaling "
            f"${total_amount:.2f}. Latest order reference is {latest_order}. "
            f"Ignored {len(follow_up_messages)} low-signal follow-up messages."
        )


class FlagManager:
    required_fields = ("routing_number", "account_number", "cvv")

    def build_flags(self, case_facts: dict[str, object]) -> tuple[list[FlagRecord], str]:
        banking_details = case_facts["banking_details"]
        flags: list[FlagRecord] = []
        for field_name in self.required_fields:
            if not banking_details.get(field_name):
                flags.append(
                    FlagRecord(
                        flag_type="missing_required_field",
                        field=field_name,
                        status="open",
                        session_state="requires_user_input",
                    )
                )

        session_state = "requires_user_input" if flags else "ready"
        return flags, session_state


class Phase4Harness:
    def __init__(self, log_path: Path | None = None, db_path: Path | None = None) -> None:
        self.session_id = f"phase4-{uuid4().hex[:8]}"
        self.logger = StructuredLogger(log_path)
        self.db_path = db_path or Path("data/phase4_memory.db")
        self.store = SessionMemoryStore(self.db_path)
        self.extractor = CaseFactsExtractor()
        self.compactor = MemoryCompactor()
        self.flags = FlagManager()

    def _log(self, event_type: str, step_index: int, **payload_summary: object) -> None:
        self.logger.log(
            LogEvent(
                event_type=event_type,
                session_id=self.session_id,
                agent_name="phase4_memory_manager",
                step_index=step_index,
                payload_summary=payload_summary,
            )
        )

    def run(self, document: str, follow_up_messages: list[str]) -> Phase4Outcome:
        self._log(
            "agent_started",
            0,
            document_length=len(document),
            follow_up_count=len(follow_up_messages),
        )
        case_facts = self.extractor.extract(document)
        generated_flags, session_state = self.flags.build_flags(case_facts)
        compact_summary = self.compactor.build_summary(case_facts, follow_up_messages)

        self.store.save_snapshot(
            session_id=self.session_id,
            compact_summary=compact_summary,
            case_facts=case_facts,
            session_state=session_state,
        )
        self.store.replace_flags(self.session_id, generated_flags)

        for index, flag in enumerate(generated_flags, start=1):
            self._log(
                "missing_required_field",
                index,
                field=flag.field,
                session_state=flag.session_state,
            )

        self._log(
            "memory_compacted",
            len(generated_flags) + 1,
            transaction_count=len(case_facts["transactions"]),
            summary_length=len(compact_summary),
            session_state=session_state,
        )

        persisted_snapshot = self.store.load_snapshot(self.session_id)
        return Phase4Outcome(
            session_id=self.session_id,
            input_document_length=len(document),
            compact_summary=compact_summary,
            case_facts=case_facts,
            flags=[
                {
                    "flag_type": flag.flag_type,
                    "field": flag.field,
                    "status": flag.status,
                    "session_state": flag.session_state,
                }
                for flag in generated_flags
            ],
            session_state=session_state,
            follow_up_messages=follow_up_messages,
            persisted_snapshot=persisted_snapshot,
            log_path=str(self.logger.sink_path) if self.logger.sink_path else None,
            db_path=str(self.db_path),
            logs=list(self.logger.events),
        )


def build_sample_transaction_document(repetitions: int = 120) -> str:
    base = """
Customer Name: Jane Doe
Transaction ID: TXN-10045
Order ID: ORD-77881
Amount: $249.99
Currency: USD
Date: 2026-04-30
Routing Number: 123456789
Account Number: 987654321

Transaction ID: TXN-10046
Order ID: ORD-77882
Amount: $19.95
Currency: USD
Date: 2026-05-01
Routing Number: 123456789
Account Number: 987654321
"""
    filler = (
        "This transactional record captures settlement details, item mapping, "
        "approval trace, and reconciliation annotations for archival review. "
    )
    return base + filler * repetitions
