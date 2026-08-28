"""
Provider-agnostic LLM wrapper.

Why this exists (obstacle #1 in the README): the task spec allows
OpenAI / Anthropic / Gemini, and a judge may only have one key handy.
This module picks whichever key is present at runtime via LangChain's
chat model interfaces, so the rest of the codebase never imports a
specific provider SDK directly.
"""
from langchain_core.messages import SystemMessage, HumanMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings


def get_chat_model(temperature: float = 0.0):
    """
    Returns a LangChain chat model bound to whichever provider has a
    key configured. temperature=0.0 by default — deterministic,
    evidence-grounded output matters more than creativity for a
    finance-control agent (hallucination mitigation #2).
    """
    provider = settings.active_provider()

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=settings.OPENAI_MODEL,
            api_key=settings.OPENAI_API_KEY,
            temperature=temperature,
        )
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=settings.ANTHROPIC_MODEL,
            api_key=settings.ANTHROPIC_API_KEY,
            temperature=temperature,
        )
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
            temperature=temperature,
        )

    raise RuntimeError(
        "No LLM API key found. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, "
        "or GEMINI_API_KEY in your .env file."
    )


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def call_with_retry(chat_model, messages):
    """
    Retries on transient API errors (rate limits, timeouts) with
    exponential backoff — obstacle #3 (latency/flakiness) in the README.
    """
    return chat_model.invoke(messages)


def build_messages(system_prompt: str, user_prompt: str):
    return [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
