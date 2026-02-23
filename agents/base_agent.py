"""
BaseAgent — abstract base class providing the full Anthropic agentic loop.

Pattern:
  1. Send messages to Claude with tool definitions.
  2. stop_reason == "tool_use"  → execute every tool call in the response,
     accumulate results into one user message, loop.
  3. stop_reason == "end_turn"  → extract final text and return.
  4. MAX_ITERATIONS guard prevents runaway loops.
"""

import json
from abc import ABC, abstractmethod
from typing import Any

import anthropic

from config.settings import settings
from utils.logger import get_logger

MAX_ITERATIONS = 20


class BaseAgent(ABC):
    """
    All sub-agents inherit this class and gain a full tool-calling agentic loop.

    Subclasses must define class attributes:
      model         : str        — Claude model ID
      system_prompt : str        — agent's behavioural instructions
      tools         : list[dict] — Anthropic-format tool definitions

    And implement:
      _handle_tool_call(name, input) → Any  — dispatch tool to concrete handler
    """

    model: str = ""
    system_prompt: str = ""
    tools: list[dict] = []

    def __init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._log = get_logger(self.__class__.__name__)

    @abstractmethod
    def _handle_tool_call(self, tool_name: str, tool_input: dict) -> Any:
        """Execute the named tool and return a JSON-serialisable result."""

    def run(self, user_message: str) -> str:
        """
        Run the agentic loop for the given user message.
        Returns Claude's final text response after all tool calls complete.
        """
        self._log.debug("Starting agentic loop (model=%s)", self.model)
        messages = [{"role": "user", "content": user_message}]

        for iteration in range(MAX_ITERATIONS):
            self._log.debug("Iteration %d — calling Claude", iteration + 1)

            response = self._client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=self.system_prompt,
                tools=self.tools if self.tools else anthropic.NOT_GIVEN,
                messages=messages,
            )

            # Always append the assistant turn before deciding what to do
            messages.append({"role": "assistant", "content": response.content})
            self._log.debug("stop_reason=%s", response.stop_reason)

            # ── Terminal: Claude finished ──────────────────────────────────────
            if response.stop_reason == "end_turn":
                result = self._extract_text(response.content)
                self._log.debug("end_turn after %d iteration(s)", iteration + 1)
                return result

            # ── Tool calls: execute all, then loop ─────────────────────────────
            if response.stop_reason == "tool_use":
                tool_results = []

                for block in response.content:
                    if block.type != "tool_use":
                        continue

                    self._log.info("Tool call → %s(%s)", block.name, block.input)

                    try:
                        result = self._handle_tool_call(block.name, block.input)
                        content = json.dumps(result)
                        is_error = False
                    except Exception as exc:
                        self._log.error("Tool %s raised: %s", block.name, exc)
                        content = json.dumps({"error": str(exc)})
                        is_error = True

                    self._log.debug("Tool %s result: %s", block.name, content[:200])
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": content,
                        "is_error": is_error,
                    })

                # All tool results go into a single user message (API requirement)
                messages.append({"role": "user", "content": tool_results})
                continue

            # ── Unexpected stop reason (max_tokens, etc.) ──────────────────────
            self._log.warning("Unexpected stop_reason=%s", response.stop_reason)
            return self._extract_text(response.content) or f"[{self.__class__.__name__}] stopped: {response.stop_reason}"

        self._log.error("Reached MAX_ITERATIONS (%d)", MAX_ITERATIONS)
        return f"[{self.__class__.__name__}] Max iterations reached."

    @staticmethod
    def _extract_text(content_blocks: list) -> str:
        return "\n".join(
            b.text for b in content_blocks
            if hasattr(b, "type") and b.type == "text"
        ).strip()
