from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from veridex.graph.skills import Skill
from veridex.graph.state import AnalysisState
from veridex.llm import get_llm, get_structured_llm

_MAX_CLAIMS = 20
_MAX_CONTENT_CHARS = 12_000

_EXTRACT_SYSTEM = """\
You are a product claims extractor. Given the text of a product listing, identify every explicit \
quality, performance, or benefit claim made about the product.

Extract only concrete, specific claims — not generic marketing filler like "high quality" or "great value".

Focus on claims that are:
- Quantified: "lasts 30 days", "waterproof to 50m", "reduces wrinkles by 40%"
- Material/origin: "100% merino wool", "made in Germany", "grade 316 stainless steel"
- Certification/compliance: "FDA approved", "CE certified", "ISO 9001", "OEKO-TEX"
- Comparative: "3x faster than competitors", "#1 rated", "hospital-grade"
- Capability: "works in -40°C", "supports 500kg", "holds a charge for 72 hours"

Return up to 20 claims as short, verbatim or near-verbatim phrases from the listing.\
"""

_VERIFY_SYSTEM = """\
You are a product claims veracity analyst. Given a list of claims extracted from a product listing, \
assess the plausibility and integrity of each one.

For each claim consider:
- Physical/scientific plausibility: is this achievable given known limits for the product category?
- Price–quality coherence: does the claim match the apparent price point and product tier?
- Verifiability: is the claim specific and testable, or vague and unverifiable?
- Certification authenticity: if a certification is claimed (FDA, CE, ISO, etc.), is it plausible \
  for this product type? Are such certifications commonly faked or misrepresented in this category?
- Benchmark context: how does the claimed specification compare to known standards or typical products?

Flag:
- IMPLAUSIBLE: physically impossible or wildly inconsistent with the product tier/price
- SUSPICIOUS: possible but extraordinary; commonly used in dropship/scam listings without basis
- UNVERIFIABLE: deliberately vague or unmeasurable (not necessarily false, but not meaningful either)
- PLAUSIBLE: consistent with known products in this category at this price range
- VERIFIED_STANDARD: matches a real, well-known standard or certification

Provide a concise verdict per claim, then a one-paragraph overall integrity summary.\
"""


class _ClaimsOutput(BaseModel):
    claims: list[str] = Field(
        description=f"Up to {_MAX_CLAIMS} specific quality, performance, or benefit claims from the listing.",
        max_length=_MAX_CLAIMS,
    )


class ClaimsVerificationSkill(Skill):
    """Extract explicit product claims from the listing and assess their plausibility."""

    name = "claims_verification"
    description = "Extracts quality and benefit claims from the listing text and verifies their plausibility."
    always_run = True

    async def run(self, state: AnalysisState) -> dict[str, list[str]]:
        """
        Extract and verify product claims from the cleaned page content.

        Step 1 uses structured output to pull up to 20 concrete, specific claims
        from the listing. Step 2 asks the LLM to assess each claim's plausibility,
        price-quality coherence, and certification authenticity.

        :param state: Current graph state; uses ``cleaned_content``.
        :return: Skill findings appended to ``skill_results``.
        """
        content = state["cleaned_content"][:_MAX_CONTENT_CHARS]

        # Step 1 – extract claims
        claims_output: _ClaimsOutput = await get_structured_llm(_ClaimsOutput).ainvoke(
            [SystemMessage(content=_EXTRACT_SYSTEM), HumanMessage(content=content)]
        )
        claims = claims_output.claims

        if not claims:
            return {
                "skill_results": ["[claims_verification]\nNo specific quality or benefit claims found in the listing."]
            }

        # Step 2 – verify plausibility
        claims_block = "\n".join(f"{i}. {c}" for i, c in enumerate(claims, start=1))
        response = await get_llm().ainvoke(
            [
                SystemMessage(content=_VERIFY_SYSTEM),
                HumanMessage(content=f"Product listing excerpt:\n{content[:3_000]}\n\nClaims:\n{claims_block}"),
            ]
        )

        lines = [
            "[claims_verification]",
            f"Claims extracted: {len(claims)}",
            f"\n{response.content}",
        ]
        return {"skill_results": ["\n".join(lines)]}
