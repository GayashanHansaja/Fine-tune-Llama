"""
Policy ingestion — front-matter parsing + clause-aware chunking.

Why this exists instead of reusing `data/ingestion/ingest_service.py`:

The general ingester splits at CHUNK_SIZE=500 on character boundaries.  Applied
to a rule like

    "Outbound transfers exceeding 25,000 require dual authorization."

that can produce  "...transfers exceeding 25,000 require"  and  "dual
authorization."  as two separate chunks.  Neither is a retrievable rule — the
threshold survives without its consequence, and the judge approves an action it
should have blocked.

So policy documents are split on *clause* boundaries first (headings, numbered
items, blank lines) and only hard-split when a single clause exceeds the limit.
"""
import logging
import os
import re

# pyrefly: ignore [missing-import]
import yaml
from langchain_core.documents import Document as LCDocument

from src.config.settings import settings
from src.types.policy import PolicyMeta

logger = logging.getLogger(__name__)

_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# A new clause starts at: markdown heading, "1." / "1.2" numbering,
# "Section 4", or a lettered "(a)" item — all at line start.
_CLAUSE_START = re.compile(
    r"^(?:#{1,6}\s+"           # markdown heading
    r"|\d+(?:\.\d+)*[.)]\s+"   # 1.  1.2.  3)
    r"|\(?[a-z]\)\s+"          # (a)  b)
    r"|Section\s+\d+"          # Section 4
    r"|Article\s+\d+"          # Article 12
    r")",
    re.MULTILINE | re.IGNORECASE,
)


def parse_front_matter(text: str) -> tuple[PolicyMeta, str]:
    """
    Split a policy document into its YAML front-matter and body.

    Raises ValueError if front-matter is missing or lacks `policy_id` — an
    untagged policy cannot be filtered on, so it must not silently ingest.
    """
    match = _FRONT_MATTER.match(text)
    if not match:
        raise ValueError(
            "policy document has no YAML front-matter block (expected '---' delimited header)"
        )

    raw = yaml.safe_load(match.group(1)) or {}
    if not isinstance(raw, dict):
        raise ValueError("front-matter must be a YAML mapping")
    if not raw.get("policy_id"):
        raise ValueError("front-matter is missing required field 'policy_id'")

    # YAML parses unquoted dates into date objects; payload needs strings.
    if raw.get("effective_date") is not None:
        raw["effective_date"] = str(raw["effective_date"])
    if raw.get("version") is not None:
        raw["version"] = str(raw["version"])

    body = text[match.end():].strip()
    return PolicyMeta(**raw), body


def split_clauses(body: str) -> list[str]:
    """Break the body at clause starts, keeping each clause's text contiguous."""
    boundaries = [m.start() for m in _CLAUSE_START.finditer(body)]
    if not boundaries:
        # No structural markers — fall back to paragraphs.
        return [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]

    if boundaries[0] != 0:
        boundaries.insert(0, 0)   # preamble before the first marker
    boundaries.append(len(body))

    clauses = []
    for start, end in zip(boundaries, boundaries[1:]):
        clause = body[start:end].strip()
        if clause:
            clauses.append(clause)
    return clauses


def _hard_split(clause: str, limit: int) -> list[str]:
    """Last resort for an oversized clause — split on sentence ends, never mid-sentence."""
    sentences = re.split(r"(?<=[.;:])\s+", clause)
    parts: list[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > limit:
            parts.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current.strip():
        parts.append(current.strip())
    return parts


def pack_clauses(clauses: list[str], limit: int) -> list[str]:
    """
    Merge adjacent clauses up to `limit` so chunks aren't uselessly small,
    without ever letting a single clause straddle two chunks.
    """
    chunks: list[str] = []
    current = ""

    for clause in clauses:
        if len(clause) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_hard_split(clause, limit))
            continue

        candidate = f"{current}\n\n{clause}".strip() if current else clause
        if len(candidate) > limit:
            chunks.append(current)
            current = clause
        else:
            current = candidate

    if current:
        chunks.append(current)
    return chunks


def build_policy_documents(text: str, source: str) -> list[LCDocument]:
    """
    Turn one raw policy document into tagged, clause-aligned LangChain Documents.

    Every chunk carries the full front-matter payload, so Qdrant can filter on
    `applies_to_tools` / `mandatory` / `risk_level` without relying on the
    embedding to have ranked the right rule into the top-k.
    """
    meta, body = parse_front_matter(text)
    chunks = pack_clauses(split_clauses(body), settings.POLICY_CHUNK_SIZE)

    base_payload = meta.to_payload()
    docs = [
        LCDocument(
            page_content=chunk,
            metadata={**base_payload, "source": source, "chunk_index": i},
        )
        for i, chunk in enumerate(chunks)
    ]
    logger.info(
        f"policy '{meta.policy_id}' v{meta.version} → {len(docs)} chunk(s) "
        f"| tools={meta.applies_to_tools} | mandatory={meta.mandatory}"
    )
    return docs


def build_policy_documents_from_file(path: str) -> list[LCDocument]:
    """Read a policy file and build its tagged Documents. `source` is the basename."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    return build_policy_documents(text, source=os.path.basename(path))
