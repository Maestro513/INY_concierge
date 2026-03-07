"""
Claude API client for answering member questions about their SOB.
"""

import json
import os
import re

import anthropic

from .config import ANTHROPIC_API_KEY, EXTRACTED_DIR

# PHI patterns to strip from user questions before sending to third-party API
_PHI_PATTERNS = [
    (re.compile(r"\b\d{1}[A-Z]{2}\d{1}-[A-Z]{2}\d{1}-[A-Z]{2}\d{2}\b"), "[MEDICARE_ID]"),   # Medicare number
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),                                           # SSN
    (re.compile(r"\b\d{9}\b"), "[SSN]"),                                                        # SSN without dashes
    (re.compile(r"\b\d{10}\b"), "[PHONE]"),                                                     # Phone number
    (re.compile(r"\b\(\d{3}\)\s*\d{3}-\d{4}\b"), "[PHONE]"),                                   # (xxx) xxx-xxxx
    (re.compile(r"\b\d{3}-\d{3}-\d{4}\b"), "[PHONE]"),                                         # xxx-xxx-xxxx
    (re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"), "[DOB]"),                                     # Date of birth
]


def _scrub_phi(text: str) -> str:
    """Remove PHI patterns (Medicare IDs, SSNs, phone numbers, DOBs) from text."""
    for pattern, replacement in _PHI_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


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


def load_plan_chunks(plan_id: str) -> list[dict] | None:
    """Load pre-extracted chunks for a plan.
    Returns list of {"section": "...", "text": "..."} dicts,
    or plain strings wrapped as {"section": "General", "text": "..."} for backward compat.
    """
    path = _find_extracted_file(plan_id)
    if path is None:
        return None
    with open(path, "r") as f:
        data = json.load(f)
    chunks = data["chunks"]
    # Handle old format (list of plain strings) — wrap them
    if chunks and isinstance(chunks[0], str):
        return [{"section": "General", "text": c} for c in chunks]
    return chunks


_DRUG_SYNONYMS = {
    "drug", "drugs", "prescription", "prescriptions", "formulary",
    "tier", "copay", "copays", "pharmacy", "rx", "medication",
    "medications", "generic", "brand", "specialty", "mail order",
    "retail", "preferred", "non-preferred", "initial coverage",
    "coverage gap", "catastrophic", "deductible",
}

# Maps common question topics to section labels for boosted matching
_TOPIC_SECTION_MAP = {
    "doctor": ["Doctor Visits", "Primary Care", "Office Visits"],
    "pcp": ["Doctor Visits", "Primary Care", "Office Visits"],
    "primary": ["Doctor Visits", "Primary Care", "Office Visits"],
    "specialist": ["Specialist Visits", "Specialist Services"],
    "emergency": ["Emergency Care", "Emergency Room", "Emergency Services"],
    "urgent": ["Urgently Needed Care", "Urgent Care"],
    "hospital": ["Inpatient Hospital", "Outpatient Hospital"],
    "inpatient": ["Inpatient Hospital"],
    "outpatient": ["Outpatient Hospital", "Ambulatory Surgery"],
    "surgery": ["Outpatient Hospital", "Ambulatory Surgery"],
    "nursing": ["Skilled Nursing Facility"],
    "snf": ["Skilled Nursing Facility"],
    "mental": ["Mental Health Services", "Behavioral Health"],
    "behavioral": ["Mental Health Services", "Behavioral Health"],
    "substance": ["Substance Abuse", "Substance Use"],
    "drug": ["Prescription Drug Benefits", "Drug Benefits", "Pharmacy"],
    "prescription": ["Prescription Drug Benefits", "Drug Benefits", "Pharmacy"],
    "pharmacy": ["Prescription Drug Benefits", "Drug Benefits", "Pharmacy"],
    "medication": ["Prescription Drug Benefits", "Drug Benefits", "Pharmacy"],
    "dental": ["Dental Services", "Dental Benefits"],
    "teeth": ["Dental Services", "Dental Benefits"],
    "vision": ["Vision Services", "Vision Benefits"],
    "eye": ["Vision Services", "Vision Benefits"],
    "glasses": ["Vision Services", "Vision Benefits"],
    "hearing": ["Hearing Services", "Hearing Benefits"],
    "lab": ["Lab Services", "Diagnostic Services"],
    "diagnostic": ["Lab Services", "Diagnostic Services"],
    "xray": ["Lab Services", "Diagnostic Services"],
    "imaging": ["Lab Services", "Diagnostic Services"],
    "therapy": ["Rehabilitation Services", "Physical Therapy", "Occupational Therapy"],
    "physical": ["Rehabilitation Services", "Physical Therapy"],
    "rehab": ["Rehabilitation Services", "Physical Therapy"],
    "home": ["Home Health Care", "Home Health Services"],
    "hospice": ["Hospice"],
    "ambulance": ["Ambulance Services", "Ambulance"],
    "equipment": ["Durable Medical Equipment", "Medical Equipment"],
    "dme": ["Durable Medical Equipment", "Medical Equipment"],
    "wheelchair": ["Durable Medical Equipment", "Medical Equipment"],
    "fitness": ["Fitness Benefit", "Fitness Program"],
    "silversneakers": ["Fitness Benefit", "Fitness Program"],
    "otc": ["Over-The-Counter", "Otc Allowance"],
    "over-the-counter": ["Over-The-Counter", "Otc Allowance"],
    "transportation": ["Transportation"],
    "ride": ["Transportation"],
    "telehealth": ["Telehealth", "Virtual Visits"],
    "virtual": ["Telehealth", "Virtual Visits"],
    "chiropractic": ["Chiropractic"],
    "chiropractor": ["Chiropractic"],
    "acupuncture": ["Acupuncture"],
    "podiatry": ["Podiatry", "Foot Care"],
    "foot": ["Podiatry", "Foot Care"],
    "premium": ["Plan Overview", "Monthly Premium", "Plan Costs"],
    "cost": ["Plan Overview", "Plan Costs", "Monthly Premium"],
    "deductible": ["Plan Overview", "Plan Costs"],
    "copay": ["Plan Overview", "Plan Costs"],
    "maximum": ["Plan Overview", "Plan Costs"],
    "out-of-pocket": ["Plan Overview", "Plan Costs"],
}


def find_relevant_chunks(chunks: list[dict], question: str, max_chunks: int = 5) -> str:
    """Section-aware TF-IDF scoring to find the most relevant chunks.
    Combines section label matching with TF-IDF text scoring,
    bigram matching, and synonym expansion for drug queries.
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

    # Find section labels that match the question topic
    boosted_sections = set()
    for word in question_lower.split():
        word_clean = word.strip("?.,!\"'")
        if word_clean in _TOPIC_SECTION_MAP:
            for s in _TOPIC_SECTION_MAP[word_clean]:
                boosted_sections.add(s.lower())

    # Extract text from chunks (handles both dict and string formats)
    texts = []
    sections = []
    for chunk in chunks:
        if isinstance(chunk, dict):
            texts.append(chunk["text"])
            sections.append(chunk.get("section", "").lower())
        else:
            texts.append(chunk)
            sections.append("")

    # Compute document frequency (how many chunks contain each term)
    n_docs = len(texts)
    doc_freq = {}
    texts_lower = [t.lower() for t in texts]
    for term in all_terms:
        doc_freq[term] = sum(1 for tl in texts_lower if term in tl)

    # Score each chunk using TF * IDF + section boost
    scored = []
    for i, text_lower in enumerate(texts_lower):
        score = 0.0

        # TF-IDF text scoring
        for term in all_terms:
            if term not in text_lower:
                continue
            tf = text_lower.count(term)
            df = doc_freq.get(term, 0)
            idf = math.log((n_docs + 1) / (df + 1)) + 1.0
            weight = 2.0 if " " in term else 1.0
            score += tf * idf * weight

        # Section label boost: +5 if section matches a topic keyword
        section = sections[i]
        if section and boosted_sections:
            if any(s in section or section in s for s in boosted_sections):
                score += 5.0

        # Keyword hits in section label itself
        for kw in words:
            if kw in section:
                score += 1.0

        scored.append((score, chunks[i]))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [chunk for score, chunk in scored[:max_chunks] if score > 0]

    # If no matches, return first few chunks (they usually have overview info)
    if not top:
        top = chunks[:max_chunks]

    # Format with section labels for Claude context
    parts = []
    for c in top:
        if isinstance(c, dict):
            parts.append(f"[{c['section']}]\n{c['text']}")
        else:
            parts.append(c)

    return "\n\n---\n\n".join(parts)


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

    # H9: Scrub PHI from user question before sending to third-party API
    safe_question = _scrub_phi(question)
    context = find_relevant_chunks(chunks, question)  # Use original for relevance matching

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=60.0)

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

Question: {safe_question}""",
            }
        ],
    )

    return {
        "answer": message.content[0].text,
        "plan_number": plan_id,
        "has_context": True,
    }
