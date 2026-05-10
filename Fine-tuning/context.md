Hands-on Lab: Fine-tuning, Evals & ROI of Model Optimization

Objective
Replace an expensive, prompt-heavy system using a large model with a cost-efficient, fine-tuned smaller model, and prove its effectiveness quantitatively using evaluation pipelines and cost analysis.

Problem Statement
You are currently using a large model (GPT-4o) with a massive few-shot prompt to generate outputs in a highly specific proprietary DSL format.

This approach is:
- Expensive (high token usage per request)
- Hard to scale
- Inefficient for production

Your goal is to:
- Replace this setup with a fine-tuned GPT-4o-mini model
- Ensure equal or better output quality
- Demonstrate clear cost savings and ROI

Rules of Engagement
You must:
- Use the raw OpenAI SDK (no abstraction frameworks)
- Manually prepare training data in JSONL format
- Perform Supervised Fine-Tuning (SFT)
- Build an automated evaluation pipeline (LLM-as-a-judge)
- Perform a cost-benefit analysis (ROI calculation)

You are NOT allowed to:
- Rely only on prompt engineering
- Skip evaluation or cost analysis
- Use pre-built fine-tuning pipelines

Phase 1: Try to Break It — Few-shot Bloat & Mini Model Failure

Your Task
1. Create a large system prompt containing:
   - 10 few-shot examples
   - Each example converts natural language -> proprietary DSL
2. Use GPT-4o to:
   - Generate 50 high-quality training examples
   - Format them into JSONL dataset
3. Fine-tune:
   - Model: gpt-4o-mini
   - Epochs: 3
4. After training:
   - Query the fine-tuned model using zero-shot prompts

Challenge
Base models struggle with:
- Strict syntax
- Structured outputs
- Proprietary formats

Without fine-tuning:
- Output becomes inconsistent
- Hallucinated syntax appears
- Extra conversational text is added

Questions to Answer
- Did the fine-tuned model produce correct DSL output in zero-shot mode?
- Did it eliminate conversational filler completely?
- If even one training sample contained formatting issues (e.g., markdown), how did it affect model behavior?
- How many input tokens per request were reduced compared to the few-shot approach?

Phase 2: Code Read & Audit — Automated Evals & Feedback Loop

Your Task
1. Split dataset:
   - Training set
   - Validation set (20 examples)
2. Build an evaluation pipeline:
   - Input: Model output + Ground truth
   - Use GPT-4o as a Grader Model
   - Output: Strict score -> 1 (correct) / 0 (incorrect)
3. Run evaluation across validation set

Challenge
Traditional testing fails because:
- Outputs are not deterministic
- Regex-based validation is brittle
- Semantic correctness is hard to measure

Questions to Answer
- Why is LLM-as-a-judge better than regex-based validation?
- If 5 outputs fail, how would you:
  - Improve dataset?
  - Introduce Reinforcement Fine-Tuning (RFT)?
- What was the final training loss? What does it indicate?
- Did evaluation scores align with real output quality?

Phase 3: Map & Optimize — ROI & Cost Engineering

Your Task
1. Build a cost comparison matrix for:
   Approach: Few-shot Prompt
   Model: GPT-4o
   Tokens per Request: High
   Cost per Request: Expensive

   Approach: Fine-tuned
   Model: GPT-4o-mini
   Tokens per Request: Low
   Cost per Request: Cheap
2. Simulate:
   - 1,000,000 requests
3. Calculate:
   - Total cost (before vs after)
   - Fine-tuning training cost
   - Break-even point

Challenge
Fine-tuning introduces:
- Upfront cost
- Engineering complexity
- Maintenance overhead

Questions to Answer
- After how many requests does fine-tuning become profitable?
- What % cost reduction did you achieve?
- Why is SFT not suitable for teaching new knowledge?
- What additional DevOps challenges arise with:
  - Open-source models (QLoRA)?
  - Model versioning and deployment?

Expectations
Your system should demonstrate:
- Ability to replace prompt-heavy systems with fine-tuned models
- Understanding of SFT vs Prompt Engineering trade-offs
- Implementation of automated evaluation pipelines
- Clear understanding of token economics and cost optimization
- Practical knowledge of production trade-offs (cost vs quality vs complexity)

Deliverables
1. Code
   - Fine-tuning pipeline (dataset + training script)
   - Evaluation pipeline (LLM grader)
2. Dataset
   - Training JSONL file
   - Validation dataset
3. Analysis
   - Evaluation results (accuracy scores)
   - Error analysis
4. Cost Report
   - Token usage comparison
   - Cost matrix
   - Break-even analysis

Key Learning Outcomes
- Why prompt engineering does not scale
- When to use fine-tuning vs base models
- How to build evaluation systems for LLMs
- How to think in terms of ROI, not just accuracy
- Real-world LLMOps decision making

LLM Usage & Cost Guidelines

LLM Provider Guidelines
- Use OpenAI API (GPT-4o mini / GPT-3.5 class models preferred)
- If OpenAI API keys are provided/allowed, use them as the primary provider
- Use OpenRouter as fallback if OpenAI is unavailable
- Avoid high-cost models unless explicitly required

Cost & Usage Guidelines
- Focus is on architecture and understanding, not output quality
- Always prefer the cheapest models during all hands-on/development phases
- Avoid unnecessary retries, loops, and repeated API calls
- Keep context small to reduce token usage (avoid sending large inputs repeatedly)

Project Note
This file is the source of truth for the lab requirements unless explicitly superseded by the user.
