from functools import cache

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, SecretStr

from veridex.config import settings


@cache
def get_llm() -> BaseChatModel:
    """
    Return the shared chat model used by every node and skill.

    The model is created lazily so the app can be imported (e.g. in tests)
    without an API key configured.

    :return: A deterministic (temperature 0) chat model.
    """
    return ChatOpenAI(model=settings.llm_model, temperature=0, api_key=SecretStr(settings.openai_api_key))


def get_structured_llm[T: BaseModel](schema: type[T]) -> Runnable:
    """
    Return the shared chat model bound to a structured output schema.

    :param schema: Pydantic model the LLM response is parsed into.
    :return: A runnable whose ``ainvoke`` returns an instance of ``schema``.
    """
    return get_llm().with_structured_output(schema)
