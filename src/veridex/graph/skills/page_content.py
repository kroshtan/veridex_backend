from langchain_core.messages import HumanMessage, SystemMessage

from veridex.graph.skills import Skill
from veridex.graph.state import AnalysisState
from veridex.llm import get_llm

_MAX_CHARS = 40_000

_SYSTEM = """\
You are a product page analyst. Examine the page content for signals about the \
seller's legitimacy. Look for:
- Known brand presence vs. generic / white-label branding
- Dropshipping patterns: AliExpress-style copy, vague or long shipping times, \
  no warehouse address
- Scam signals: fake urgency ("Only 3 left!"), unrealistic discounts, \
  missing contact info, no return policy
- Trust signals: clear return/refund policy, verifiable reviews, professional copy

Provide a concise, factual summary of your findings — no score yet, just evidence.\
"""


class PageContentSkill(Skill):
    """Baseline skill: LLM analysis of the cleaned page text."""

    name = "page_content"
    description = "Analyses page text for legitimacy and scam signals."
    always_run = True

    async def run(self, state: AnalysisState) -> dict[str, list[str]]:
        """
        Analyse cleaned page content with an LLM.

        :param state: Current graph state; uses ``cleaned_content``.
        :return: Skill findings appended to ``skill_results``.
        """
        content = state["cleaned_content"][:_MAX_CHARS]
        response = await get_llm().ainvoke([SystemMessage(content=_SYSTEM), HumanMessage(content=content)])
        return {"skill_results": [f"[page_content]\n{response.content}"]}
