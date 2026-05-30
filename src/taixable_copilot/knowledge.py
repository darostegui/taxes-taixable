"""Free-text tax-knowledge retrieval — the Elasticsearch search showcase.

This is the *conversational* counterpart to :mod:`legislation` (which is keyed by
exact engine citation id). Here the agent can ask open questions like "what is the
183-day rule?" or "double-taxation relief between Germany and Spain" and get back
curated, source-linked passages from a single ``tax-knowledge`` index that fuses
the legislation passages and the treaty articles.

Retrieval is **hybrid**: BM25 (keyword) + dense-vector kNN (semantic, embedded
with Vertex ``gemini-embedding-001``), fused with Reciprocal Rank Fusion. The
Elastic path degrades gracefully:

    RRF retriever  →  separate BM25 + kNN fused in Python  →  BM25 only

and when no ``ELASTIC_URL`` is configured (or Elastic is unreachable) it falls
back to an in-process lexical search so the agent still answers offline.

**No-hallucination contract.** This is an *evidence* layer, never an authority:
it returns passages (title, curated summary, jurisdiction, source URL) and the
deterministic engine remains the only source of figures, rates, articles and
deadlines. The Elastic path fails closed — only documents whose ``citation_id``
is on the local curated allowlist are ever surfaced.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

DATA_DIR = Path(__file__).resolve().parent / "data"
KNOWLEDGE_INDEX = "tax-knowledge"

# A search takes a free-text query (and optional jurisdiction filter) and returns
# a result envelope: ``{"results": [...passages...], "meta": {...}}``.
KnowledgeSearch = Callable[..., dict[str, Any]]

_RRF_RANK_CONSTANT = 60
_DEFAULT_K = 4

# Fields surfaced to the model / UI for each retrieved passage.
_PASSAGE_FIELDS = (
    "citation_id",
    "jurisdiction",
    "country_pair",
    "title",
    "article",
    "summary",
    "source_url",
    "content_type",
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "a an and are as at be by for from how if in into is it of on or that the to "
    "what when where which who why with you your do does my our their his her i "
    "this these those can could would should will".split()
)


def _content_tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS}


@lru_cache(maxsize=1)
def build_knowledge_corpus() -> list[dict[str, Any]]:
    """Build the unified searchable corpus, keyed uniquely by citation id.

    ``legislation.json`` is the canonical curated knowledge base (residency,
    deadlines and one summary per treaty article), each with a ``source_url``.
    ``treaty_articles.json`` holds the literal convention text; where a treaty id
    is already curated we fold that literal text into the document's BM25 ``text``
    body (better keyword recall) rather than adding a duplicate id.
    """
    by_id: dict[str, dict[str, Any]] = {}

    leg = json.loads((DATA_DIR / "legislation.json").read_text(encoding="utf-8"))
    for e in leg["legislation"]:
        jurisdiction = e.get("jurisdiction", "")
        country_pair = jurisdiction if "-" in jurisdiction else ""
        summary = e.get("summary", "")
        title = e.get("title", "")
        by_id[e["citation_id"]] = {
            "doc_id": e["citation_id"],
            "citation_id": e["citation_id"],
            "jurisdiction": jurisdiction,
            "country_pair": country_pair,
            "title": title,
            "article": e.get("article", ""),
            "summary": summary,
            "source_url": e.get("source_url", ""),
            "content_type": e.get("content_type", "curated_summary"),
            "text": f"{title}. {summary}",
        }

    treaty = json.loads((DATA_DIR / "treaty_articles.json").read_text(encoding="utf-8"))
    for t in treaty["treaty_articles"]:
        cid = t["citation_id"]
        pair = t.get("country_pair", "")
        topic = t.get("topic", "")
        body = t.get("text", "")
        types = ", ".join(t.get("income_types", []))
        literal = f"{topic}. {body}. Income types: {types}."
        if cid in by_id:
            doc = by_id[cid]
            doc["country_pair"] = doc["country_pair"] or pair
            doc["text"] = f"{doc['text']} {literal}"
            continue
        article_no = t.get("article_no", "")
        title = f"{pair} double tax treaty — Article {article_no}: {topic}".strip()
        by_id[cid] = {
            "doc_id": cid,
            "citation_id": cid,
            "jurisdiction": pair,
            "country_pair": pair,
            "title": title,
            "article": f"Art. {article_no}" if article_no else "",
            "summary": body,
            "source_url": t.get("url", ""),
            "content_type": "treaty_article",
            "text": f"{title}. {literal}",
        }

    return list(by_id.values())


@lru_cache(maxsize=1)
def known_knowledge_ids() -> frozenset[str]:
    """The curated allowlist of doc ids the Elastic path is allowed to return."""
    return frozenset(d["citation_id"] for d in build_knowledge_corpus())


def _public_passage(src: dict[str, Any]) -> dict[str, Any]:
    return {k: src.get(k, "") for k in _PASSAGE_FIELDS}


# --------------------------------------------------------------------------- #
# Corpus (offline) lexical search                                             #
# --------------------------------------------------------------------------- #
def corpus_knowledge_search() -> KnowledgeSearch:
    docs = build_knowledge_corpus()

    def search(query: str, k: int = _DEFAULT_K, jurisdiction: str | None = None) -> dict:
        q_tokens = _content_tokens(query)
        pool = docs
        if jurisdiction:
            j = jurisdiction.strip().upper()
            pool = [
                d
                for d in docs
                if j in (d["jurisdiction"].upper(), d["country_pair"].upper())
                or j in d["country_pair"].upper().split("-")
            ]
        scored: list[tuple[float, float, dict]] = []
        for d in pool:
            title_tokens = _content_tokens(d["title"])
            body_tokens = _content_tokens(d["text"])
            # Primary: distinct query terms covered (title counts double); a long
            # passage is not penalised for being thorough.
            covered = len(q_tokens & (title_tokens | body_tokens))
            if covered == 0:
                continue
            title_hits = len(q_tokens & title_tokens)
            score = covered + 0.5 * title_hits
            tiebreak = -len(body_tokens)  # prefer the more focused passage on ties
            scored.append((score, tiebreak, d))
        scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
        results = [_public_passage(d) for _, _, d in scored[:k]]
        return {
            "results": results,
            "meta": {
                "mode": "corpus",
                "retrieval": "lexical",
                "query": query,
                "jurisdiction": jurisdiction or "",
                "k": k,
            },
        }

    return search


# --------------------------------------------------------------------------- #
# Elastic hybrid search                                                       #
# --------------------------------------------------------------------------- #
def _jurisdiction_filter(jurisdiction: str) -> list[dict]:
    j = jurisdiction.strip().upper()
    return [
        {
            "bool": {
                "should": [
                    {"term": {"jurisdiction": j}},
                    {"term": {"country_pair": j}},
                ],
                "minimum_should_match": 1,
            }
        }
    ]


def elastic_knowledge_search(url: str, api_key: str | None) -> KnowledgeSearch:
    from elasticsearch import Elasticsearch

    from taixable_copilot.embeddings import embed_query

    es = Elasticsearch(url, api_key=api_key) if api_key else Elasticsearch(url)
    allow = known_knowledge_ids()
    corpus_fallback = corpus_knowledge_search()

    def _allowed(hits: list[dict]) -> list[dict]:
        out: list[dict] = []
        for h in hits:
            src = h.get("_source", {})
            cid = src.get("citation_id") or h.get("_id")
            if cid in allow:
                out.append(_public_passage(src))
        return out

    def _bm25_query(query: str, jurisdiction: str | None) -> dict:
        match: dict = {
            "bool": {
                "must": [
                    {"multi_match": {"query": query, "fields": ["title^2", "text", "summary"]}}
                ]
            }
        }
        if jurisdiction:
            match["bool"]["filter"] = _jurisdiction_filter(jurisdiction)
        return match

    def _knn_query(vector: list[float], k: int, jurisdiction: str | None) -> dict:
        knn: dict = {
            "field": "embedding",
            "query_vector": vector,
            "k": k,
            "num_candidates": max(25, k * 5),
        }
        if jurisdiction:
            knn["filter"] = {"bool": {"filter": _jurisdiction_filter(jurisdiction)}}
        return knn

    def _python_rrf(
        bm25_hits: list[dict], knn_hits: list[dict], k: int
    ) -> list[dict]:
        scores: dict[str, float] = {}
        first_seen: dict[str, dict] = {}
        for hits in (bm25_hits, knn_hits):
            for rank, h in enumerate(hits, start=1):
                cid = h.get("_source", {}).get("citation_id") or h.get("_id")
                if cid not in allow:
                    continue
                scores[cid] = scores.get(cid, 0.0) + 1.0 / (_RRF_RANK_CONSTANT + rank)
                first_seen.setdefault(cid, h)
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        return [_public_passage(first_seen[cid]["_source"]) for cid, _ in ranked[:k]]

    def search(query: str, k: int = _DEFAULT_K, jurisdiction: str | None = None) -> dict:
        meta = {
            "mode": "elastic",
            "retrieval": "bm25",
            "query": query,
            "jurisdiction": jurisdiction or "",
            "k": k,
        }
        vec = embed_query(query)
        try:
            if vec is not None:
                # Preferred: a single RRF retriever fusing BM25 + semantic kNN.
                try:
                    resp = es.search(
                        index=KNOWLEDGE_INDEX,
                        retriever={
                            "rrf": {
                                "retrievers": [
                                    {"standard": {"query": _bm25_query(query, jurisdiction)}},
                                    {"knn": _knn_query(list(vec), k, jurisdiction)},
                                ],
                                "rank_window_size": max(10, k * 3),
                                "rank_constant": _RRF_RANK_CONSTANT,
                            }
                        },
                        size=k,
                    )
                    meta["retrieval"] = "hybrid_rrf"
                    return {"results": _allowed(resp["hits"]["hits"]), "meta": meta}
                except Exception:  # noqa: BLE001 - RRF unsupported → fuse in Python
                    bm25 = es.search(
                        index=KNOWLEDGE_INDEX, query=_bm25_query(query, jurisdiction), size=k * 3
                    )["hits"]["hits"]
                    knn = es.search(
                        index=KNOWLEDGE_INDEX, knn=_knn_query(list(vec), k * 3, jurisdiction), size=k * 3
                    )["hits"]["hits"]
                    meta["retrieval"] = "hybrid_python"
                    return {"results": _python_rrf(bm25, knn, k), "meta": meta}
            # No embedding (offline embeddings) → keyword search in Elastic.
            resp = es.search(
                index=KNOWLEDGE_INDEX, query=_bm25_query(query, jurisdiction), size=k
            )
            return {"results": _allowed(resp["hits"]["hits"]), "meta": meta}
        except Exception:  # noqa: BLE001 - Elastic unreachable → offline corpus
            out = corpus_fallback(query, k=k, jurisdiction=jurisdiction)
            out["meta"]["mode"] = "corpus_fallback"
            return out

    return search


def build_knowledge_search() -> KnowledgeSearch:
    """Pick the Elastic hybrid backend when ``ELASTIC_URL`` is set, else corpus."""
    url = os.environ.get("ELASTIC_URL")
    if url:
        return elastic_knowledge_search(url, os.environ.get("ELASTIC_API_KEY"))
    return corpus_knowledge_search()


# --------------------------------------------------------------------------- #
# Citation -> source-passage highlighting                                     #
#                                                                             #
# The "verifiable AI" feature: clicking a citation retrieves the *exact*       #
# allowlisted passage by id and asks Elasticsearch to mark the spans that      #
# match the question, so a reviewer can see word-for-word why the engine cited #
# it. Retrieval is by ``citation_id`` (a deterministic term filter) — never a  #
# fresh fuzzy search — so the highlighted passage is always the cited one.     #
# --------------------------------------------------------------------------- #
# Highlight a single passage: ``highlight(citation_id, query) -> envelope``.
KnowledgeHighlight = Callable[..., dict[str, Any]]

_HIGHLIGHT_PRE = "<mark>"
_HIGHLIGHT_POST = "</mark>"
_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]?")


@lru_cache(maxsize=1)
def _corpus_by_id() -> dict[str, dict[str, Any]]:
    return {d["citation_id"]: d for d in build_knowledge_corpus()}


def _not_found(citation_id: str, mode: str, reason: str) -> dict[str, Any]:
    return {
        "found": False,
        "citation_id": citation_id,
        "fragments": [],
        "meta": {"mode": mode, "reason": reason},
    }


def _highlight_terms(text: str, query: str) -> list[str]:
    """Offline highlighter: wrap query terms in the sentences that contain them."""
    q_tokens = _content_tokens(query)
    if not text:
        return []
    fragments: list[str] = []
    for sentence in _SENTENCE_RE.findall(text):
        stripped = sentence.strip()
        if not stripped:
            continue
        s_tokens = _content_tokens(stripped)
        if not (q_tokens & s_tokens):
            continue
        marked = re.sub(
            r"\b(" + "|".join(re.escape(t) for t in sorted(q_tokens & s_tokens)) + r")\b",
            lambda m: f"{_HIGHLIGHT_PRE}{m.group(0)}{_HIGHLIGHT_POST}",
            stripped,
            flags=re.IGNORECASE,
        )
        fragments.append(marked)
        if len(fragments) >= 3:
            break
    return fragments


def corpus_highlight() -> KnowledgeHighlight:
    """Offline citation highlighter over the in-process corpus."""

    def highlight(citation_id: str, query: str = "") -> dict[str, Any]:
        doc = _corpus_by_id().get(citation_id)
        if doc is None:
            return _not_found(citation_id, "corpus", "not_allowlisted")
        body = doc.get("summary") or doc.get("text") or ""
        fragments = _highlight_terms(body, query) if query else []
        if not fragments and body:
            # No query overlap (or no query): show the passage verbatim so the
            # reviewer still sees the cited source text.
            fragments = [body]
        return {
            "found": True,
            "citation_id": citation_id,
            "title": doc.get("title", ""),
            "jurisdiction": doc.get("jurisdiction", "") or doc.get("country_pair", ""),
            "article": doc.get("article", ""),
            "source_url": doc.get("source_url", ""),
            "fragments": fragments,
            "meta": {"mode": "corpus", "retrieval": "lexical-highlight", "query": query},
        }

    return highlight


def elastic_highlight(url: str, api_key: str | None) -> KnowledgeHighlight:
    """Elasticsearch highlighter: fetch the cited doc by id and mark query spans."""
    from elasticsearch import Elasticsearch

    es = Elasticsearch(url, api_key=api_key) if api_key else Elasticsearch(url)
    allow = known_knowledge_ids()
    fallback = corpus_highlight()

    def highlight(citation_id: str, query: str = "") -> dict[str, Any]:
        # Fail closed: only allowlisted citation ids can ever be returned.
        if citation_id not in allow:
            return _not_found(citation_id, "elastic", "not_allowlisted")
        try:
            should = (
                [{"multi_match": {"query": query, "fields": ["title^2", "text", "summary"]}}]
                if query
                else []
            )
            resp = es.search(
                index=KNOWLEDGE_INDEX,
                query={"bool": {"filter": [{"term": {"citation_id": citation_id}}], "should": should}},
                highlight={
                    "pre_tags": [_HIGHLIGHT_PRE],
                    "post_tags": [_HIGHLIGHT_POST],
                    "number_of_fragments": 3,
                    "fragment_size": 240,
                    "fields": {"text": {}, "summary": {}, "title": {}},
                },
                size=1,
            )
            hits = resp["hits"]["hits"]
            if not hits:
                return fallback(citation_id, query)
            hit = hits[0]
            src = hit.get("_source", {})
            hl = hit.get("highlight", {})
            fragments: list[str] = []
            for field in ("summary", "text", "title"):
                fragments.extend(hl.get(field, []))
            if not fragments:
                fragments = [src.get("summary") or src.get("text") or ""]
            return {
                "found": True,
                "citation_id": citation_id,
                "title": src.get("title", ""),
                "jurisdiction": src.get("jurisdiction", "") or src.get("country_pair", ""),
                "article": src.get("article", ""),
                "source_url": src.get("source_url", ""),
                "fragments": [f for f in fragments if f][:3],
                "meta": {
                    "mode": "elastic",
                    "retrieval": "highlight",
                    "query": query,
                    "score": hit.get("_score"),
                },
            }
        except Exception:  # noqa: BLE001 - Elastic unreachable -> offline highlighter
            out = fallback(citation_id, query)
            out["meta"]["mode"] = "corpus_fallback"
            return out

    return highlight


def build_knowledge_highlight() -> KnowledgeHighlight:
    """Pick the Elastic highlighter when ``ELASTIC_URL`` is set, else corpus."""
    url = os.environ.get("ELASTIC_URL")
    if url:
        return elastic_highlight(url, os.environ.get("ELASTIC_API_KEY"))
    return corpus_highlight()
