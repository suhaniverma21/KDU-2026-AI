# Phase 1 Results

## Summary
- Baseline model: `gpt-4o`
- Fine-tuned model: `ft:gpt-4.1-mini-2025-04-14:kickdrum:ops-phase1:DdsePiWJ`
- Baseline exact-match accuracy: `0.2`
- Fine-tuned exact-match accuracy: `0.3`
- Baseline valid-DSL rate: `1.0`
- Fine-tuned valid-DSL rate: `1.0`
- Average baseline input tokens: `1006.6`
- Average fine-tuned input tokens: `40.6`
- Average input-token reduction: `966.0`
- Average input-token reduction percent: `95.97`

## Case Results

### Case 1
- Request: `Deploy inventory-api to staging during business hours for the QA cycle.`
- Expected: `OPS|INTENT=DEPLOY|SERVICE="inventory-api"|ENV="staging"|PRIORITY=MEDIUM|APPROVAL=AUTO|NOTIFY=YES|WINDOW="BUSINESS_HOURS"|TAGS=["release","inventory"]`
- Baseline output: `OPS|INTENT=DEPLOY|SERVICE="inventory-api"|ENV="staging"|PRIORITY=MEDIUM|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="BUSINESS_HOURS"|TAGS=["deploy","qa"]`
- Fine-tuned output: `OPS|INTENT=DEPLOY|SERVICE="inventory-api"|ENV="staging"|PRIORITY=MEDIUM|APPROVAL=AUTO|NOTIFY=YES|WINDOW="BUSINESS_HOURS"|TAGS=["deployment","inventory"]`
- Baseline exact match: `False`
- Fine-tuned exact match: `False`
- Baseline valid: `True`
- Fine-tuned valid: `True`
- Baseline filler detected: `False`
- Fine-tuned filler detected: `False`

### Case 2
- Request: `Immediately scale checkout-worker in prod because orders are backing up.`
- Expected: `OPS|INTENT=SCALE|SERVICE="checkout-worker"|ENV="prod"|PRIORITY=CRITICAL|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="IMMEDIATE"|TAGS=["scaling","checkout"]`
- Baseline output: `OPS|INTENT=SCALE|SERVICE="checkout-worker"|ENV="prod"|PRIORITY=CRITICAL|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="IMMEDIATE"|TAGS=["scaling","orders"]`
- Fine-tuned output: `OPS|INTENT=SCALE|SERVICE="checkout-worker"|ENV="prod"|PRIORITY=CRITICAL|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="IMMEDIATE"|TAGS=["scaling","checkout"]`
- Baseline exact match: `False`
- Fine-tuned exact match: `True`
- Baseline valid: `True`
- Fine-tuned valid: `True`
- Baseline filler detected: `False`
- Fine-tuned filler detected: `False`

### Case 3
- Request: `Restart report-builder in dev quietly during business hours.`
- Expected: `OPS|INTENT=RESTART|SERVICE="report-builder"|ENV="dev"|PRIORITY=LOW|APPROVAL=AUTO|NOTIFY=NO|WINDOW="BUSINESS_HOURS"|TAGS=["restart","reports"]`
- Baseline output: `OPS|INTENT=RESTART|SERVICE="report-builder"|ENV="dev"|PRIORITY=MEDIUM|APPROVAL=AUTO|NOTIFY=NO|WINDOW="BUSINESS_HOURS"|TAGS=["restart","report"]`
- Fine-tuned output: `OPS|INTENT=RESTART|SERVICE="report-builder"|ENV="dev"|PRIORITY=MEDIUM|APPROVAL=AUTO|NOTIFY=YES|WINDOW="BUSINESS_HOURS"|TAGS=["restart","report"]`
- Baseline exact match: `False`
- Fine-tuned exact match: `False`
- Baseline valid: `True`
- Fine-tuned valid: `True`
- Baseline filler detected: `False`
- Fine-tuned filler detected: `False`

### Case 4
- Request: `Back up audit-db in prod on Saturday 0200Z before the compliance review.`
- Expected: `OPS|INTENT=BACKUP|SERVICE="audit-db"|ENV="prod"|PRIORITY=MEDIUM|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="MAINTENANCE_SAT_0200Z"|TAGS=["backup","compliance"]`
- Baseline output: `OPS|INTENT=BACKUP|SERVICE="audit-db"|ENV="prod"|PRIORITY=HIGH|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="MAINTENANCE_SAT_0200Z"|TAGS=["backup","compliance"]`
- Fine-tuned output: `OPS|INTENT=BACKUP|SERVICE="audit-db"|ENV="prod"|PRIORITY=LOW|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="MAINTENANCE_SAT_0200Z"|TAGS=["backup","audit"]`
- Baseline exact match: `False`
- Fine-tuned exact match: `False`
- Baseline valid: `True`
- Fine-tuned valid: `True`
- Baseline filler detected: `False`
- Fine-tuned filler detected: `False`

### Case 5
- Request: `Restore ledger-db in DR immediately after the outage declaration.`
- Expected: `OPS|INTENT=RESTORE|SERVICE="ledger-db"|ENV="dr"|PRIORITY=CRITICAL|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="IMMEDIATE"|TAGS=["restore","ledger"]`
- Baseline output: `OPS|INTENT=RESTORE|SERVICE="ledger-db"|ENV="dr"|PRIORITY=CRITICAL|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="IMMEDIATE"|TAGS=["restore","outage"]`
- Fine-tuned output: `OPS|INTENT=RESTORE|SERVICE="ledger-db"|ENV="dr"|PRIORITY=CRITICAL|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="IMMEDIATE"|TAGS=["restore","ledger"]`
- Baseline exact match: `False`
- Fine-tuned exact match: `True`
- Baseline valid: `True`
- Fine-tuned valid: `True`
- Baseline filler detected: `False`
- Fine-tuned filler detected: `False`

### Case 6
- Request: `Patch session-gateway in prod on Sunday 0100Z for a security remediation.`
- Expected: `OPS|INTENT=PATCH|SERVICE="session-gateway"|ENV="prod"|PRIORITY=HIGH|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="MAINTENANCE_SUN_0100Z"|TAGS=["patch","security"]`
- Baseline output: `OPS|INTENT=PATCH|SERVICE="session-gateway"|ENV="prod"|PRIORITY=HIGH|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="MAINTENANCE_SUN_0100Z"|TAGS=["patch","security"]`
- Fine-tuned output: `OPS|INTENT=PATCH|SERVICE="session-gateway"|ENV="prod"|PRIORITY=HIGH|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="MAINTENANCE_SUN_0100Z"|TAGS=["patch","security"]`
- Baseline exact match: `True`
- Fine-tuned exact match: `True`
- Baseline valid: `True`
- Fine-tuned valid: `True`
- Baseline filler detected: `False`
- Fine-tuned filler detected: `False`

### Case 7
- Request: `Block suspicious traffic at api-firewall in prod right now.`
- Expected: `OPS|INTENT=BLOCK|SERVICE="api-firewall"|ENV="prod"|PRIORITY=CRITICAL|APPROVAL=AUTO|NOTIFY=YES|WINDOW="IMMEDIATE"|TAGS=["security","network"]`
- Baseline output: `OPS|INTENT=BLOCK|SERVICE="api-firewall"|ENV="prod"|PRIORITY=CRITICAL|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="IMMEDIATE"|TAGS=["security","traffic"]`
- Fine-tuned output: `OPS|INTENT=BLOCK|SERVICE="api-firewall"|ENV="prod"|PRIORITY=CRITICAL|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="IMMEDIATE"|TAGS=["security","api"]`
- Baseline exact match: `False`
- Fine-tuned exact match: `False`
- Baseline valid: `True`
- Fine-tuned valid: `True`
- Baseline filler detected: `False`
- Fine-tuned filler detected: `False`

### Case 8
- Request: `Migrate user-db in staging after hours ahead of the integration test.`
- Expected: `OPS|INTENT=MIGRATE|SERVICE="user-db"|ENV="staging"|PRIORITY=HIGH|APPROVAL=AUTO|NOTIFY=YES|WINDOW="AFTER_HOURS"|TAGS=["migration","users"]`
- Baseline output: `OPS|INTENT=MIGRATE|SERVICE="user-db"|ENV="staging"|PRIORITY=HIGH|APPROVAL=AUTO|NOTIFY=YES|WINDOW="AFTER_HOURS"|TAGS=["migration","user"]`
- Fine-tuned output: `OPS|INTENT=MIGRATE|SERVICE="user-db"|ENV="staging"|PRIORITY=HIGH|APPROVAL=AUTO|NOTIFY=YES|WINDOW="AFTER_HOURS"|TAGS=["migration","database"]`
- Baseline exact match: `False`
- Fine-tuned exact match: `False`
- Baseline valid: `True`
- Fine-tuned valid: `True`
- Baseline filler detected: `False`
- Fine-tuned filler detected: `False`

### Case 9
- Request: `Fail over notification-api to DR immediately.`
- Expected: `OPS|INTENT=FAILOVER|SERVICE="notification-api"|ENV="dr"|PRIORITY=CRITICAL|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="IMMEDIATE"|TAGS=["failover","notifications"]`
- Baseline output: `OPS|INTENT=FAILOVER|SERVICE="notification-api"|ENV="dr"|PRIORITY=CRITICAL|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="IMMEDIATE"|TAGS=["failover","notification"]`
- Fine-tuned output: `OPS|INTENT=FAILOVER|SERVICE="notification-api"|ENV="dr"|PRIORITY=CRITICAL|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="IMMEDIATE"|TAGS=["failover","notification"]`
- Baseline exact match: `False`
- Fine-tuned exact match: `False`
- Baseline valid: `True`
- Fine-tuned valid: `True`
- Baseline filler detected: `False`
- Fine-tuned filler detected: `False`

### Case 10
- Request: `Rollback pricing-api in prod immediately due to a broken release.`
- Expected: `OPS|INTENT=ROLLBACK|SERVICE="pricing-api"|ENV="prod"|PRIORITY=HIGH|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="IMMEDIATE"|TAGS=["rollback","pricing"]`
- Baseline output: `OPS|INTENT=ROLLBACK|SERVICE="pricing-api"|ENV="prod"|PRIORITY=HIGH|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="IMMEDIATE"|TAGS=["rollback","pricing"]`
- Fine-tuned output: `OPS|INTENT=ROLLBACK|SERVICE="pricing-api"|ENV="prod"|PRIORITY=CRITICAL|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="IMMEDIATE"|TAGS=["rollback","pricing"]`
- Baseline exact match: `True`
- Fine-tuned exact match: `False`
- Baseline valid: `True`
- Fine-tuned valid: `True`
- Baseline filler detected: `False`
- Fine-tuned filler detected: `False`
