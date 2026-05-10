# Phase 2 Error Analysis

## Training Loss Context
- final_train_loss=0.1770010143518448, final_valid_loss=0.12154380798339844
- Lower loss usually indicates the model fit the training distribution better, but it does not by itself prove real generalization or semantic correctness.

## Why LLM-as-a-Judge Beats Regex Alone
- Regex and structural validators are good at catching malformed syntax, filler text, markdown fences, and field-order issues.
- They are weak at judging semantic correctness when two outputs are both well-formed but one encodes the wrong operational intent or wrong decision values.
- A strict LLM judge can compare request meaning, expected DSL, and predicted DSL in one pass and decide whether the output is actually correct.

## Recommended Improvement Loop
- Expand training coverage for intents or environments with the highest failure counts. In this run the failed intents were `{'DEPLOY': 2}` and the failed environments were `{'dev': 1, 'staging': 1}`.
- Add more phrasing diversity around categories that failed repeatedly. In this run the only repeated failure category was `{'wrong-field-value': 2}`.
- Remove or isolate contaminated markdown examples before retraining.
- Re-run SFT on the cleaned dataset before considering more complex interventions.
- If residual failures remain after data cleanup, use RFT or preference optimization on those hard cases.

## Failure Categories
- `{'wrong-field-value': 2}`

## Failed Cases

### Case 17
- Request: `Deploy the new search feature to the dev environment immediately.`
- Expected DSL: `OPS|INTENT=DEPLOY|SERVICE="search-feature"|ENV="dev"|PRIORITY=MEDIUM|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="IMMEDIATE"|TAGS=["deployment","search"]`
- Predicted DSL: `OPS|INTENT=DEPLOY|SERVICE="search-feature"|ENV="dev"|PRIORITY=HIGH|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="IMMEDIATE"|TAGS=["deployment","search"]`
- Judge reason: `PRIORITY value is incorrect; expected MEDIUM, found HIGH.`
- Failure category: `wrong-field-value`
- Validator errors: `[]`

### Case 20
- Request: `Deploy the new version of the user service to staging during business hours.`
- Expected DSL: `OPS|INTENT=DEPLOY|SERVICE="user-service"|ENV="staging"|PRIORITY=MEDIUM|APPROVAL=MANUAL|NOTIFY=YES|WINDOW="BUSINESS_HOURS"|TAGS=["deployment","user"]`
- Predicted DSL: `OPS|INTENT=DEPLOY|SERVICE="user-service"|ENV="staging"|PRIORITY=MEDIUM|APPROVAL=AUTO|NOTIFY=YES|WINDOW="BUSINESS_HOURS"|TAGS=["deployment","user"]`
- Judge reason: `APPROVAL field value is incorrect; expected MANUAL, found AUTO.`
- Failure category: `wrong-field-value`
- Validator errors: `[]`
