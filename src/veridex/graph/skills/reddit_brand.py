import asyncio
from functools import cache

import praw
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from veridex.config import settings
from veridex.graph.skills import Skill
from veridex.graph.state import AnalysisState

_MAX_POSTS = 15
_MAX_SNIPPET_CHARS = 300

_EXTRACT_SYSTEM = """\
You are given the text of an e-commerce product page.
Extract the brand or seller name of the product being sold.
Return only the brand name — nothing else.
If you cannot determine it, return the single word: unknown\
"""

_SUMMARIZE_SYSTEM = """\
You are analysing Reddit discussions about a brand to assess its trustworthiness.
Given the post titles and snippets below, provide a concise factual summary covering:
- Overall sentiment (positive / mixed / negative)
- Any scam, fraud, counterfeit, or dropship complaints
- Any notable trust signals (positive reviews, verified presence)

No score — evidence only.\
"""


class _BrandOutput(BaseModel):
    brand: str = Field(description="The brand or seller name, or 'unknown' if it cannot be determined.")


@cache
def _get_extract_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model="gpt-4o-mini", temperature=0, openai_api_key=settings.openai_api_key
    ).with_structured_output(_BrandOutput)


@cache
def _get_summarize_llm() -> ChatOpenAI:
    return ChatOpenAI(model="gpt-4o-mini", temperature=0, openai_api_key=settings.openai_api_key)


def _search_reddit(brand: str) -> list[dict]:
    """
    Search Reddit for posts mentioning the brand and return structured summaries.

    Runs synchronously; call via :func:`asyncio.to_thread` from async code.

    :param brand: Brand or seller name to search for.
    :return: List of dicts with ``title``, ``subreddit``, ``score``, and ``snippet``.
    """
    reddit = praw.Reddit(
        client_id=settings.reddit_client_id,
        client_secret=settings.reddit_client_secret,
        user_agent=settings.reddit_user_agent,
    )
    return [
        {
            "title": submission.title,
            "subreddit": submission.subreddit.display_name,
            "score": submission.score,
            "snippet": submission.selftext[:_MAX_SNIPPET_CHARS] if submission.selftext else "",
        }
        for submission in reddit.subreddit("all").search(brand, limit=_MAX_POSTS, sort="relevance")
    ]


class RedditBrandSkill(Skill):
    """Look up the product brand on Reddit and summarise community sentiment."""

    name = "reddit_brand"
    description = "Searches Reddit for brand reputation signals and scam reports."
    always_run = True

    async def run(self, state: AnalysisState) -> dict[str, list[str]]:
        """
        Extract the brand name from the page, search Reddit, and summarise findings.

        :param state: Current graph state; uses ``cleaned_content``.
        :return: Skill findings appended to ``skill_results``.
        """
        if not settings.reddit_client_id or not settings.reddit_client_secret:
            return {"skill_results": ["[reddit_brand]\nSkill disabled: no Reddit credentials configured."]}

        # Step 1 – extract brand name
        brand_output: _BrandOutput = await _get_extract_llm().ainvoke(
            [
                SystemMessage(content=_EXTRACT_SYSTEM),
                HumanMessage(content=state["cleaned_content"][:8_000]),
            ]
        )
        brand = brand_output.brand.strip()
        if not brand or brand.lower() == "unknown":
            return {"skill_results": ["[reddit_brand]\nCould not determine brand name from page."]}

        # Step 2 – fetch Reddit posts (sync PRAW in a thread)
        posts = await asyncio.to_thread(_search_reddit, brand)
        if not posts:
            return {"skill_results": [f"[reddit_brand]\nNo Reddit posts found for '{brand}'."]}

        # Step 3 – summarise with LLM
        posts_text = "\n\n".join(
            f"r/{p['subreddit']} | score {p['score']}\n{p['title']}\n{p['snippet']}".strip() for p in posts
        )
        response = await _get_summarize_llm().ainvoke(
            [
                SystemMessage(content=_SUMMARIZE_SYSTEM),
                HumanMessage(content=f"Brand: {brand}\n\nReddit posts:\n{posts_text}"),
            ]
        )

        return {"skill_results": [f"[reddit_brand]\nBrand: {brand}\n{response.content}"]}
