import os
import logging
from typing import Optional

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from app.strategies.Workflows.copay_agent.prompts import build_system_prompt
from app.strategies.Workflows.copay_agent.tools import (
    calculate_copay,
    find_network_providers,
    list_available_networks,
    list_available_plans,
    search_insurance_coverage,
    search_providers_online,
)

load_dotenv()
logger = logging.getLogger(__name__)

_agent = None
_memory: Optional[MemorySaver] = None


def _get_agent():
    global _agent, _memory
    if _agent is None:
        logger.info("Initializing CopayAgent")
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0.1,
            api_key=os.getenv("GEMINI_API_KEY"),
        )
        _memory = MemorySaver()
        _agent = create_react_agent(
            model=llm,
            tools=[
                list_available_plans,
                list_available_networks,
                search_insurance_coverage,
                find_network_providers,
                search_providers_online,
                calculate_copay,
            ],
            checkpointer=_memory,
            prompt=build_system_prompt(),
        )
        logger.info("CopayAgent initialized successfully")
    return _agent


def _content_to_text(content) -> str:
    """Normalizes an LLM message content to plain text.

    Gemini may return content as a list of blocks instead of a string.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text" and block.get("text"):
                    parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)


def run_copay_agent(user_message: str, session_id: str) -> str:
    agent = _get_agent()
    config = {"configurable": {"thread_id": session_id}}
    try:
        logger.info(f"CopayAgent invoked: session={session_id}")
        result = agent.invoke(
            {"messages": [HumanMessage(content=user_message)]},
            config=config,
        )
        messages = result.get("messages", [])
        if messages:
            reply = _content_to_text(messages[-1].content)
            if reply.strip():
                return reply
        return "No se pudo generar una respuesta. Por favor intente de nuevo."
    except Exception as e:
        logger.error(f"CopayAgent error for session={session_id}: {e}", exc_info=True)
        raise
