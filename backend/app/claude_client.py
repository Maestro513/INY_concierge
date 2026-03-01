"""
Claude API client for answering member questions about their SOB.
"""

import json
import os

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


def _find_extracted_file(plan_id: str) -> str | None:
    """Find extracted JSON — tries both H1234-567.json and H1234-567-000.json."""
    pid = normalize_plan_id(plan_id)  # H1234-567
    for candidate in [f"{pid}.json", f"{pid}-000.json"]:
        path = os.path.join(EXTRACTED_DIR, candidate)
        if os.path.exists(path):
            return path
    return None


def load_plan_chunks(plan_id: str) -> list[str] | None:
    """Load pre-extracted chunks for a plan."""
    path = _find_extracted_file(plan_id)
    if path is None:
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
    """TF-IDF inspired scoring to find the most relevant chunks.
    Uses term frequency with IDF-like weighting: rarer terms score higher.
    Also supports bigram matching and synonym expansion for drug queries.
    """
    import math
    question_lower = question.lower()

    # Build unigrams (len > 2) and bigrams from the question
    words = [w for w in question_lower.split() if len(w) > 2]
    bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]

    # Expand: if any keyword is drug-related, add all drug synonyms
    is_drug_q = (
        any(kw in _DRUG_SYNONYMS for kw in words)
        or " rx " in f" {question_lower} "
    )
    if is_drug_q:
        words = list(set(words) | _DRUG_SYNONYMS)

    all_terms = words + bigrams

    # Compute document frequency (how many chunks contain each term)
    n_docs = len(chunks)
    doc_freq = {}
    chunks_lower = [c.lower() for c in chunks]
    for term in all_terms:
        doc_freq[term] = sum(1 for cl in chunks_lower if term in cl)

    # Score each chunk using TF * IDF
    scored = []
    for i, chunk_lower in enumerate(chunks_lower):
        score = 0.0
        for term in all_terms:
            if term not in chunk_lower:
                continue
            # Term frequency: count occurrences in this chunk
            tf = chunk_lower.count(term)
            # IDF: rarer terms across chunks get higher weight
            df = doc_freq.get(term, 0)
            idf = math.log((n_docs + 1) / (df + 1)) + 1.0
            # Bigrams get a 2x boost
            weight = 2.0 if " " in term else 1.0
            score += tf * idf * weight
        scored.append((score, chunks[i]))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [chunk for score, chunk in scored[:max_chunks] if score > 0]

    # If no matches, return first few chunks (they usually have overview info)
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
