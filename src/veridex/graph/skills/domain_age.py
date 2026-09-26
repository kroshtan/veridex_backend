import asyncio
import contextlib
from datetime import UTC, datetime

import whois
from langchain_core.messages import HumanMessage, SystemMessage

from veridex.graph.skills import Skill
from veridex.graph.state import AnalysisState
from veridex.llm import get_llm
from veridex.net import hostname

_WHOIS_TIMEOUT = 15  # seconds passed to asyncio.wait_for

_ANALYZE_SYSTEM = """\
You are an e-commerce trust analyst assessing a domain's registration data for pop-up store signals.

Given WHOIS / registry metadata, look for:
- Domain registered very recently (under 6 months) — strong pop-up store signal
- Short registration period (1-year only) suggesting low long-term commitment
- Registrant country inconsistent with the seller's claimed location or shipping origin
- Privacy-protected or hidden WHOIS (registrant name/org redacted) combined with a new domain
- Bulk or low-cost registrar frequently used by scam or disposable stores
- Domain name pattern suggesting a temporary store (random strings, keyword-stuffed, hyphenated brand knockoffs)

Summarise the findings concisely and factually. Highlight specific concerns.\
"""


def _lookup_whois(domain: str) -> dict[str, str]:
    """
    Perform a synchronous WHOIS lookup and return a flat string dict.

    Intended to be called via :func:`asyncio.to_thread`.

    :param domain: Bare domain name to look up.
    :return: Dict of WHOIS fields as strings; empty on failure.
    """
    try:
        w = whois.whois(domain)
    except Exception:  # noqa: BLE001
        return {}

    def _str(val: object) -> str:
        if val is None:
            return ""
        if isinstance(val, list):
            val = val[0]
        if isinstance(val, datetime):
            return val.strftime("%Y-%m-%d")
        return str(val)

    return {k: _str(v) for k, v in w.items() if _str(v)}


def _domain_age_days(whois_data: dict[str, str]) -> int | None:
    """
    Compute domain age in days from the WHOIS creation date.

    :param whois_data: Flat WHOIS dict as returned by :func:`_lookup_whois`.
    :return: Age in days, or ``None`` if the creation date is unavailable.
    """
    raw = whois_data.get("creation_date", "")
    if not raw:
        return None
    with contextlib.suppress(Exception):
        created = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=UTC)
        return (datetime.now(tz=UTC) - created).days
    return None


class DomainAgeSkill(Skill):
    """Look up WHOIS data for the page domain and flag pop-up store signals."""

    name = "domain_age"
    description = "Checks domain registration age, registrar, and WHOIS metadata for pop-up store signals."
    always_run = True

    async def run(self, state: AnalysisState) -> dict[str, list[str]]:
        """
        Resolve the page domain, fetch WHOIS data, and analyse for pop-up store signals.

        :param state: Current graph state; uses ``url``.
        :return: Skill findings appended to ``skill_results``.
        """
        url = state.get("url", "")
        if not url:
            return {"skill_results": ["[domain_age]\nNo URL provided; domain check skipped."]}

        domain = hostname(url)
        if not domain:
            return {"skill_results": [f"[domain_age]\nCould not parse domain from URL: {url}"]}

        # WHOIS lookup (synchronous network I/O off the event loop)
        try:
            whois_data = await asyncio.wait_for(
                asyncio.to_thread(_lookup_whois, domain),
                timeout=_WHOIS_TIMEOUT,
            )
        except TimeoutError:
            return {"skill_results": [f"[domain_age]\nWHOIS lookup timed out for {domain}."]}

        if not whois_data:
            return {"skill_results": [f"[domain_age]\nNo WHOIS data returned for {domain}."]}

        # Build a human-readable summary of key fields
        age_days = _domain_age_days(whois_data)
        age_str = (
            f"{age_days} days ({age_days // 365}y {(age_days % 365) // 30}m)" if age_days is not None else "unknown"
        )

        interesting_keys = (
            "creation_date",
            "expiration_date",
            "updated_date",
            "registrar",
            "registrant_country",
            "country",
            "org",
            "name",
            "status",
            "dnssec",
            "name_servers",
        )
        whois_summary = "\n".join(f"  {k}: {whois_data[k]}" for k in interesting_keys if k in whois_data)

        # LLM analysis
        prompt = f"Domain: {domain}\nAge: {age_str}\n\nWHOIS data:\n{whois_summary}"
        response = await get_llm().ainvoke([SystemMessage(content=_ANALYZE_SYSTEM), HumanMessage(content=prompt)])

        lines = [
            "[domain_age]",
            f"Domain: {domain}",
            f"Age: {age_str}",
            f"\nWHOIS summary:\n{whois_summary}",
            f"\nAnalysis:\n{response.content}",
        ]
        return {"skill_results": ["\n".join(lines)]}
