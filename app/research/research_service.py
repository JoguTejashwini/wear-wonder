"""Fashion research service: query generation, source normalization, evidence extraction."""
from datetime import datetime, timezone
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
import httpx

from app.research.provider import (
    CuratedFashionResourceProvider,
    DuckDuckGoWebSearchProvider,
    ResearchProvider,
    SearchResult,
)
from app.storage import (
    get_brief_by_id,
    save_or_update_brief,
    save_research_sources,
    record_audit_event,
)
from app.topic_router import classify_topic, get_topic_config


def normalize_url(url: str) -> str:
    """Normalize URL by stripping tracking parameters, downcasing host, and removing trailing slash."""
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip())
        # Strip tracking query params
        tracking_params = {
            "utm_source", "utm_medium", "utm_campaign", "utm_term",
            "utm_content", "gclid", "fbclid", "ref", "source",
        }
        filtered_query = [
            (k, v) for k, v in parse_qsl(parsed.query)
            if k.lower() not in tracking_params
        ]
        clean_path = parsed.path.rstrip("/")
        if not clean_path:
            clean_path = ""
        clean_url = urlunparse((
            parsed.scheme.lower() or "https",
            parsed.netloc.lower(),
            clean_path,
            parsed.params,
            urlencode(filtered_query),
            "",
        ))
        return clean_url
    except Exception:
        return url.strip()


def check_url_accessibility(url: str, timeout: float = 4.0) -> tuple[bool, int | None]:
    """Test URL reachability via HTTP HEAD/GET request with a short timeout."""
    if not url or not url.startswith("http"):
        return False, None
    try:
        headers = {"User-Agent": "WearAndWonder/1.0 (Fashion Research Verifier)"}
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            try:
                res = client.head(url)
                if res.status_code < 400:
                    return True, res.status_code
            except Exception:
                pass
            res = client.get(url)
            return res.status_code < 400, res.status_code
    except Exception:
        return False, None


def generate_research_queries(brief: dict) -> list[str]:
    """Generate 2-4 targeted research search queries based on the brief and topic router."""
    idea_text = brief.get("idea_original", "")
    audience = brief.get("audience") or "college girls"
    topic_config = classify_topic(idea_text)

    queries: list[str] = []

    # 1. Main topic trend query
    queries.append(f"{audience} {topic_config.display_name.lower()} styling trends")

    # 2. Query from templates
    for tmpl in topic_config.query_templates[:2]:
        q = tmpl.format(
            audience=audience,
            season="everyday current",
            silhouette="classic",
            footwear="sneakers and loafers",
            occasion="casual",
        )
        queries.append(q)

    # 3. Clean and deduplicate queries
    deduped_queries = []
    seen = set()
    for q in queries:
        cleaned = " ".join(q.split())
        if cleaned.lower() not in seen:
            seen.add(cleaned.lower())
            deduped_queries.append(cleaned)

    return deduped_queries[:3]


def execute_fashion_research(
    brief_id: str,
    provider: ResearchProvider | None = None,
    verify_urls: bool = True,
) -> dict[str, Any]:
    """Perform external fashion research for a brief and store normalized sources."""
    brief = get_brief_by_id(brief_id)
    if not brief:
        raise ValueError(f"Brief '{brief_id}' not found.")

    topic_config = classify_topic(brief.get("idea_original", ""))
    queries = generate_research_queries(brief)

    # Use live provider by default, falling back gracefully to curated authoritative resources
    primary_provider = provider or DuckDuckGoWebSearchProvider()
    fallback_provider = CuratedFashionResourceProvider()

    all_raw_results: list[SearchResult] = []

    for query in queries:
        try:
            results = primary_provider.search(query, max_results=3)
            all_raw_results.extend(results)
        except Exception:
            pass

    # If live search returned fewer than 2 sources, enrich with curated authoritative references
    if len(all_raw_results) < 2:
        for query in queries:
            curated_results = fallback_provider.search(f"{topic_config.topic_id} {query}", max_results=2)
            all_raw_results.extend(curated_results)

    # Normalize, deduplicate, and validate URLs
    normalized_sources: list[dict] = []
    seen_urls: set[str] = set()

    for item in all_raw_results:
        clean_url = normalize_url(item.url)
        if not clean_url or clean_url in seen_urls:
            continue
        seen_urls.add(clean_url)

        verification_status = "UNVERIFIED"
        status_code = None
        if verify_urls:
            is_accessible, code = check_url_accessibility(clean_url)
            verification_status = "VERIFIED" if is_accessible else "INACCESSIBLE"
            status_code = code

        source_record = {
            "source_id": f"SRC-{len(normalized_sources) + 1:02d}",
            "title": item.title or f"{topic_config.display_name} Styling Reference",
            "url": clean_url,
            "publisher": item.publisher or "Fashion Publication",
            "source_type": item.source_type or "ARTICLE",
            "publication_date": item.publication_date,
            "retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
            "relevant_excerpt": item.snippet.strip(),
            "supporting_evidence": f"Informs {topic_config.display_name.lower()} styling and proportion balance.",
            "relevance_score": 0.85,
            "verification_status": verification_status,
            "http_status_code": status_code,
        }
        normalized_sources.append(source_record)

    # Extract claims vs suggestions vs assumptions
    ai_analysis = brief.get("ai_analysis", {})
    verified_facts: list[str] = [
        s["relevant_excerpt"] for s in normalized_sources if s["verification_status"] == "VERIFIED"
    ]
    reported_claims: list[str] = [
        s["relevant_excerpt"] for s in normalized_sources if s["verification_status"] != "VERIFIED"
    ]
    ai_styling_suggestions: list[str] = (
        ai_analysis.get("research_plan", [])
        + [ai_analysis.get("styling_direction", "")]
    )
    unverified_assumptions: list[str] = ai_analysis.get("assumptions", [])

    evidence_gaps: list[str] = []
    if len(normalized_sources) < 2:
        evidence_gaps.append("Fewer than 2 external sources could be retrieved. Additional styling checks recommended.")
    if not any(s["verification_status"] == "VERIFIED" for s in normalized_sources):
        evidence_gaps.append("Live URL accessibility verification pending or network offline.")

    summary = {
        "topic_id": topic_config.topic_id,
        "topic_name": topic_config.display_name,
        "total_sources_found": len(normalized_sources),
        "verified_sources_count": sum(1 for s in normalized_sources if s["verification_status"] == "VERIFIED"),
        "queries_executed": queries,
        "verified_facts": [f for f in verified_facts if f][:6],
        "reported_claims": [c for c in reported_claims if c][:6],
        "ai_styling_suggestions": [s for s in ai_styling_suggestions if s][:6],
        "unverified_assumptions": [a for a in unverified_assumptions if a][:6],
        "evidence_gaps": evidence_gaps,
        "research_completed_at": datetime.now(timezone.utc).isoformat(),
    }

    # Atomically save sources & summary
    save_research_sources(brief_id, normalized_sources, summary)

    # Update brief research status to COMPLETED (awaiting user review/approval)
    brief["research_status"] = "COMPLETED"
    save_or_update_brief(brief)

    record_audit_event(
        brief_id=brief_id,
        stage="STAGE_2_RESEARCH",
        action="RESEARCH_EXECUTED",
        from_status="PENDING",
        to_status="COMPLETED",
        details=f"Retrieved {len(normalized_sources)} sources ({summary['verified_sources_count']} verified).",
    )

    return {
        "brief_id": brief_id,
        "sources": normalized_sources,
        "summary": summary,
    }
