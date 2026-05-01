from __future__ import annotations

from app.models import ToolError, ToolResult


def query_internal_database(query: str) -> ToolResult:
    return ToolResult(
        ok=False,
        data=None,
        error=ToolError(
            code="HTTP_500",
            message=f"Internal database unavailable for query: {query}",
        ),
        retryable=True,
        tool_name="query_internal_database",
    )


def get_salary(employee_name: str) -> ToolResult:
    salary_directory = {
        "john": {
            "employee_name": "John",
            "annual_salary_usd": 125000,
            "currency": "USD",
        }
    }
    record = salary_directory.get(employee_name.strip().lower())
    if record is None:
        return ToolResult(
            ok=False,
            data=None,
            error=ToolError(
                code="NOT_FOUND",
                message=f"No salary record found for {employee_name}.",
            ),
            retryable=False,
            tool_name="get_salary",
        )
    return ToolResult(
        ok=True,
        data=record,
        error=None,
        retryable=False,
        tool_name="get_salary",
    )


def update_banking_details(employee_name: str, routing_number: str) -> ToolResult:
    return ToolResult(
        ok=True,
        data={
            "employee_name": employee_name,
            "routing_number": routing_number,
            "status": "pending_additional_verification",
        },
        error=None,
        retryable=False,
        tool_name="update_banking_details",
    )


def get_pto_balance(employee_name: str) -> ToolResult:
    pto_directory = {
        "john": {
            "employee_name": "John",
            "pto_hours": 64,
            "pto_days_assuming_8h": 8,
        }
    }
    record = pto_directory.get(employee_name.strip().lower())
    if record is None:
        return ToolResult(
            ok=False,
            data=None,
            error=ToolError(
                code="NOT_FOUND",
                message=f"No PTO record found for {employee_name}.",
            ),
            retryable=False,
            tool_name="get_pto_balance",
        )
    return ToolResult(
        ok=True,
        data=record,
        error=None,
        retryable=False,
        tool_name="get_pto_balance",
    )
