"""
Claude API client for answering member questions about their SOB.
"""

import os
import json
import anthropic
from .config import ANTHROPIC_API_KEY, EXTRACTED_DIR


def normalize_plan_id(plan_id: str) -> str:
    """
    H1234-567-000 → H1234-567
    Zoho stores the full 3-segment ID but SOB files are keyed by 2 segments.
    """
    pid = plan_id.strip()
    if pid.endswith("-000"):
        pid = pid[:-4]
    return pid


def load_plan_chunks(plan_id: str) -> list[str] | None:
    """Load pre-extracted chunks for a plan."""
    pid = normalize_plan_id(plan_id)
    path = os.path.join(EXTRACTED_DIR, f"{pid}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        data = json.load(f)
    return data["chunks"]


_DRUG_SYNONYMS = {
    "drug", "drugs", "prescription", "prescriptions", "formulary",
    "tier", "copay", "copays", "pharmacy", "rx", "medication",
    "medications", "generic", "brand", "specialty", "mail order",
    "retail", "preferred", "non-preferred", "initial coverage",
    "coverage gap", "catastrophic", "deductible",
}


def find_relevant_chunks(chunks: list[str], question: str, max_chunks: int = 5) -> str:
    """Keyword matching to find most relevant chunks.
    Uses synonym expansion for drug-related queries so that
    'how much is Eliquis' also pulls in chunks about tiers/formulary.
    TODO: Replace with embeddings/vector search for production.
    """
    question_lower = question.lower()
    keywords = [w for w in question_lower.split() if len(w) > 2]

    # Expand: if any keyword is drug-related, add all drug synonyms
    # Also check for short drug terms ("rx") that the length filter dropped
    is_drug_q = (
        any(kw in _DRUG_SYNONYMS for kw in keywords)
        or " rx " in f" {question_lower} "
    )
    if is_drug_q:
        keywords = list(set(keywords) | _DRUG_SYNONYMS)

    scored = []
    for chunk in chunks:
        chunk_lower = chunk.lower()
        score = sum(1 for kw in keywords if kw in chunk_lower)
        scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [chunk for score, chunk in scored[:max_chunks] if score > 0]

    # If no keyword matches, return first few chunks (they usually have overview info)
    if not top:
        top = chunks[:max_chunks]

    return "\n\n---\n\n".join(top)


SYSTEM_PROMPT = """You are a Medicare benefits assistant for InsuranceNYou members.

Your job: answer the member's question using their Summary of Benefits document. Give the answer directly.

Rules:
- Lead with the answer. Say the dollar amount or yes/no first, then explain briefly if needed.
- One to two sentences max. No filler, no preamble.
- Use plain English. Say "you pay" not "the cost-sharing obligation is."
- If the document has the exact dollar amount, state it: "Your specialist copay is $40 per visit."
- If something is $0, say "That's covered at no cost to you."
- If it's not in the document, say: "I don't see that in your plan details. Call us at (844) 463-2931 and we'll look into it."
- Never guess or make up numbers.
- Remember: this will be read aloud to elderly members, so keep it natural and conversational."""


def ask_claude(question: str, plan_number: str) -> dict:
    """Send a question to Claude with plan-specific SOB context."""
    plan_id = normalize_plan_id(plan_number)
    chunks = load_plan_chunks(plan_id)

    if chunks is None:
        return {
            "answer": f"I don't have the benefits document for plan {plan_id} yet. "
                      "Please call us at (844) 463-2931 and we'll help you directly.",
            "plan_number": plan_id,
            "has_context": False,
        }

    context = find_relevant_chunks(chunks, question)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"""Plan ID: {plan_id}

Summary of Benefits sections:

{context}

---

Question: {question}""",
            }
        ],
    )

    return {
        "answer": message.content[0].text,
        "plan_number": plan_id,
        "has_context": True,
    }