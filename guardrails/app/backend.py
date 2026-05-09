from langsmith import traceable


@traceable(run_type="tool", name="mock_backend_fetch")
def get_customer_record() -> dict[str, str]:
    return {
        "name": "Alice Johnson",
        "email": "alice.johnson@example.com",
        "ssn": "123-45-6789",
    }
