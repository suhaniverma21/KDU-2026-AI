from __future__ import annotations

from dataclasses import dataclass


DSL_SPEC = """OPS DSL specification:
- Output exactly one line and nothing else.
- Format:
  OPS|INTENT=<INTENT>|SERVICE="<service>"|ENV="<env>"|PRIORITY=<PRIORITY>|APPROVAL=<APPROVAL>|NOTIFY=<NOTIFY>|WINDOW="<WINDOW>"|TAGS=["tag-one","tag-two"]
- Allowed INTENT values: DEPLOY, SCALE, RESTART, BACKUP, RESTORE, PATCH, BLOCK, MIGRATE, FAILOVER, ROLLBACK
- Allowed ENV values: dev, staging, prod, dr
- Allowed PRIORITY values: LOW, MEDIUM, HIGH, CRITICAL
- Allowed APPROVAL values: AUTO, MANUAL
- Allowed NOTIFY values: YES, NO
- Allowed WINDOW values: IMMEDIATE, BUSINESS_HOURS, AFTER_HOURS, MAINTENANCE_SAT_0200Z, MAINTENANCE_SUN_0100Z
- SERVICE must be lowercase kebab-case
- TAGS must contain 1 to 3 lowercase kebab-case strings with no spaces after commas
- Never use markdown or commentary
"""

SYSTEM_INSTRUCTIONS = (
    "Convert each natural language operations request into exactly one valid OPS DSL line. "
    "Return DSL only with no markdown, no explanations, and no extra text."
)

ZERO_SHOT_INSTRUCTIONS = (
    "You are an OPS DSL compiler. Return exactly one valid OPS line and nothing else."
)


@dataclass(frozen=True)
class Example:
    request: str
    dsl: str


EXAMPLES = [
    Example(
        request="Deploy the payments API to production tonight after hours and notify the release channel.",
        dsl='OPS|INTENT=DEPLOY|SERVICE="payments-api"|ENV="prod"|PRIORITY=HIGH|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="AFTER_HOURS"|TAGS=["release","payments"]',
    ),
    Example(
        request="Scale search-api in prod immediately because traffic is spiking hard.",
        dsl='OPS|INTENT=SCALE|SERVICE="search-api"|ENV="prod"|PRIORITY=CRITICAL|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="IMMEDIATE"|TAGS=["scaling","traffic"]',
    ),
    Example(
        request="Restart the auth worker in staging during business hours as a routine fix.",
        dsl='OPS|INTENT=RESTART|SERVICE="auth-worker"|ENV="staging"|PRIORITY=MEDIUM|APPROVAL=AUTO|NOTIFY=YES|WINDOW="BUSINESS_HOURS"|TAGS=["restart","auth"]',
    ),
    Example(
        request="Take a Saturday 0200Z backup of the customer DB in production.",
        dsl='OPS|INTENT=BACKUP|SERVICE="customer-db"|ENV="prod"|PRIORITY=LOW|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="MAINTENANCE_SAT_0200Z"|TAGS=["backup","database"]',
    ),
    Example(
        request="Restore analytics-db in the DR environment right now. This is critical.",
        dsl='OPS|INTENT=RESTORE|SERVICE="analytics-db"|ENV="dr"|PRIORITY=CRITICAL|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="IMMEDIATE"|TAGS=["restore","disaster-recovery"]',
    ),
    Example(
        request="Patch edge-gateway in production on Sunday 0100Z for the security release.",
        dsl='OPS|INTENT=PATCH|SERVICE="edge-gateway"|ENV="prod"|PRIORITY=HIGH|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="MAINTENANCE_SUN_0100Z"|TAGS=["patch","security"]',
    ),
    Example(
        request="Block the bad actor at the edge firewall in prod immediately and do it automatically.",
        dsl='OPS|INTENT=BLOCK|SERVICE="edge-firewall"|ENV="prod"|PRIORITY=CRITICAL|APPROVAL=AUTO|NOTIFY=YES|WINDOW="IMMEDIATE"|TAGS=["security","network"]',
    ),
    Example(
        request="Migrate billing-db in staging after hours before tomorrow's test window.",
        dsl='OPS|INTENT=MIGRATE|SERVICE="billing-db"|ENV="staging"|PRIORITY=HIGH|APPROVAL=AUTO|NOTIFY=YES|WINDOW="AFTER_HOURS"|TAGS=["migration","billing"]',
    ),
    Example(
        request="Fail over checkout-api to disaster recovery immediately.",
        dsl='OPS|INTENT=FAILOVER|SERVICE="checkout-api"|ENV="dr"|PRIORITY=CRITICAL|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="IMMEDIATE"|TAGS=["failover","checkout"]',
    ),
    Example(
        request="Rollback catalog-api in prod right away because the release is unhealthy.",
        dsl='OPS|INTENT=ROLLBACK|SERVICE="catalog-api"|ENV="prod"|PRIORITY=HIGH|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="IMMEDIATE"|TAGS=["rollback","catalog"]',
    ),
]

HOLDOUT_CASES = [
    Example(
        request="Deploy inventory-api to staging during business hours for the QA cycle.",
        dsl='OPS|INTENT=DEPLOY|SERVICE="inventory-api"|ENV="staging"|PRIORITY=MEDIUM|APPROVAL=AUTO|NOTIFY=YES|WINDOW="BUSINESS_HOURS"|TAGS=["release","inventory"]',
    ),
    Example(
        request="Immediately scale checkout-worker in prod because orders are backing up.",
        dsl='OPS|INTENT=SCALE|SERVICE="checkout-worker"|ENV="prod"|PRIORITY=CRITICAL|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="IMMEDIATE"|TAGS=["scaling","checkout"]',
    ),
    Example(
        request="Restart report-builder in dev quietly during business hours.",
        dsl='OPS|INTENT=RESTART|SERVICE="report-builder"|ENV="dev"|PRIORITY=LOW|APPROVAL=AUTO|NOTIFY=NO|WINDOW="BUSINESS_HOURS"|TAGS=["restart","reports"]',
    ),
    Example(
        request="Back up audit-db in prod on Saturday 0200Z before the compliance review.",
        dsl='OPS|INTENT=BACKUP|SERVICE="audit-db"|ENV="prod"|PRIORITY=MEDIUM|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="MAINTENANCE_SAT_0200Z"|TAGS=["backup","compliance"]',
    ),
    Example(
        request="Restore ledger-db in DR immediately after the outage declaration.",
        dsl='OPS|INTENT=RESTORE|SERVICE="ledger-db"|ENV="dr"|PRIORITY=CRITICAL|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="IMMEDIATE"|TAGS=["restore","ledger"]',
    ),
    Example(
        request="Patch session-gateway in prod on Sunday 0100Z for a security remediation.",
        dsl='OPS|INTENT=PATCH|SERVICE="session-gateway"|ENV="prod"|PRIORITY=HIGH|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="MAINTENANCE_SUN_0100Z"|TAGS=["patch","security"]',
    ),
    Example(
        request="Block suspicious traffic at api-firewall in prod right now.",
        dsl='OPS|INTENT=BLOCK|SERVICE="api-firewall"|ENV="prod"|PRIORITY=CRITICAL|APPROVAL=AUTO|NOTIFY=YES|WINDOW="IMMEDIATE"|TAGS=["security","network"]',
    ),
    Example(
        request="Migrate user-db in staging after hours ahead of the integration test.",
        dsl='OPS|INTENT=MIGRATE|SERVICE="user-db"|ENV="staging"|PRIORITY=HIGH|APPROVAL=AUTO|NOTIFY=YES|WINDOW="AFTER_HOURS"|TAGS=["migration","users"]',
    ),
    Example(
        request="Fail over notification-api to DR immediately.",
        dsl='OPS|INTENT=FAILOVER|SERVICE="notification-api"|ENV="dr"|PRIORITY=CRITICAL|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="IMMEDIATE"|TAGS=["failover","notifications"]',
    ),
    Example(
        request="Rollback pricing-api in prod immediately due to a broken release.",
        dsl='OPS|INTENT=ROLLBACK|SERVICE="pricing-api"|ENV="prod"|PRIORITY=HIGH|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="IMMEDIATE"|TAGS=["rollback","pricing"]',
    ),
]

INVALID_EXAMPLES = [
    '```dsl\nOPS|INTENT=DEPLOY|SERVICE="billing-api"|ENV="prod"|PRIORITY=HIGH|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="AFTER_HOURS"|TAGS=["release","billing"]\n```',
    'Sure, here is the DSL: OPS|INTENT=DEPLOY|SERVICE="billing-api"|ENV="prod"|PRIORITY=HIGH|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="AFTER_HOURS"|TAGS=["release","billing"]',
    'OPS|SERVICE="billing-api"|INTENT=DEPLOY|ENV="prod"|PRIORITY=HIGH|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="AFTER_HOURS"|TAGS=["release","billing"]',
]


def build_fewshot_prompt() -> str:
    parts = [
        "You are a compiler that converts natural language operations requests into a strict proprietary DSL called OPS.",
        "",
        "Return exactly one line of DSL and nothing else.",
        "Do not explain.",
        "Do not add markdown.",
        "Do not add prose.",
        "Do not add labels.",
        "Do not add blank lines.",
        "",
        DSL_SPEC.strip(),
        "",
        "Few-shot examples:",
        "",
    ]
    for example in EXAMPLES:
        parts.append(f"Input:\n{example.request}\nOutput:\n{example.dsl}\n")
    parts.append("Your only job is to emit one valid OPS line for each new request.")
    return "\n".join(parts)
