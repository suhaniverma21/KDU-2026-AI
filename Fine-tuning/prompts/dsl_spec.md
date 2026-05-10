# OPS DSL Specification

## Purpose
The proprietary DSL for this lab is a strict single-line operations command format called `OPS`.

## Output Contract
- Output exactly one line.
- Output DSL only.
- Do not include markdown fences.
- Do not include explanations, bullets, or conversational text.
- Do not reorder fields.

## Canonical Format
```text
OPS|INTENT=<INTENT>|SERVICE="<service>"|ENV="<env>"|PRIORITY=<PRIORITY>|APPROVAL=<APPROVAL>|NOTIFY=<NOTIFY>|WINDOW="<WINDOW>"|TAGS=["tag-one","tag-two"]
```

## Allowed Values

### `INTENT`
- `DEPLOY`
- `SCALE`
- `RESTART`
- `BACKUP`
- `RESTORE`
- `PATCH`
- `BLOCK`
- `MIGRATE`
- `FAILOVER`
- `ROLLBACK`

### `ENV`
- `dev`
- `staging`
- `prod`
- `dr`

### `PRIORITY`
- `LOW`
- `MEDIUM`
- `HIGH`
- `CRITICAL`

### `APPROVAL`
- `AUTO`
- `MANUAL`

### `NOTIFY`
- `YES`
- `NO`

### `WINDOW`
- `IMMEDIATE`
- `BUSINESS_HOURS`
- `AFTER_HOURS`
- `MAINTENANCE_SAT_0200Z`
- `MAINTENANCE_SUN_0100Z`

## String Rules
- `SERVICE` must be lowercase kebab-case with letters, digits, and hyphens only.
- `TAGS` must contain 1 to 3 lowercase kebab-case strings.
- `TAGS` must not contain spaces after commas.

## Valid Example
```text
OPS|INTENT=DEPLOY|SERVICE="billing-api"|ENV="prod"|PRIORITY=HIGH|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="AFTER_HOURS"|TAGS=["release","billing"]
```

## Invalid Examples

Wrong order:
```text
OPS|SERVICE="billing-api"|INTENT=DEPLOY|ENV="prod"|PRIORITY=HIGH|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="AFTER_HOURS"|TAGS=["release","billing"]
```

Markdown contamination:
~~~text
```dsl
OPS|INTENT=DEPLOY|SERVICE="billing-api"|ENV="prod"|PRIORITY=HIGH|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="AFTER_HOURS"|TAGS=["release","billing"]
```
~~~

Conversational filler:
```text
Sure, here is the DSL:
OPS|INTENT=DEPLOY|SERVICE="billing-api"|ENV="prod"|PRIORITY=HIGH|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="AFTER_HOURS"|TAGS=["release","billing"]
```
