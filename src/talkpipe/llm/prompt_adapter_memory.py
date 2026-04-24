import logging
from typing import Optional

from talkpipe.data.text.englishnormalize import summarize

logger = logging.getLogger("talkpipe.llm.prompt_adapters")


class PromptAdapterMemoryMixin:
    def _estimate_tokens(self, messages: list) -> int:
        # Provider-agnostic approximation to stay lightweight and deterministic.
        content_size = sum(len(str(message.get("content", ""))) for message in messages)
        return (content_size // 4) + (6 * len(messages))

    def _needs_compaction(self) -> bool:
        if self._summarization_mode != "rolling":
            return False
        effective_budget = self._get_effective_context_token_trigger()
        if not effective_budget:
            return False
        return self._estimate_tokens(self._request_messages()) > max(1, int(effective_budget))

    def _configure_memory_mode(self, memory_mode: str) -> None:
        mode = (memory_mode or "full").strip().lower()
        valid_modes = {"full", "recent_only", "summary_llm", "summary_deterministic", "summary_truncate"}
        if mode not in valid_modes:
            raise ValueError(
                f"Unknown memory_mode: {memory_mode}. "
                "Expected one of: full, recent_only, summary_llm, summary_deterministic, summary_truncate."
            )
        self._memory_mode = mode
        self._summarization_mode = "off" if mode == "full" else "rolling"
        if mode in {"recent_only", "summary_truncate"}:
            self._summary_strategy = "truncate"
        elif mode == "summary_deterministic":
            self._summary_strategy = "deterministic"
        else:
            self._summary_strategy = "llm"

    def _get_effective_context_token_trigger(self) -> Optional[int]:
        trigger = self._context_token_trigger
        if trigger is None:
            return None
        if isinstance(trigger, (int, float)) and trigger >= 1:
            return int(trigger)
        return None

    def _messages_to_summary_text(self, messages: list) -> str:
        lines = []
        for message in messages:
            role = str(message.get("role", "unknown")).upper()
            content = str(message.get("content", ""))
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def _summarize_deterministic(self, previous_summary: str, archived_messages: list) -> str:
        history_text = self._messages_to_summary_text(archived_messages)
        combined = history_text if not previous_summary else f"{previous_summary}\n{history_text}"
        if not combined.strip():
            return ""
        lines = [line for line in combined.splitlines() if line.strip()]
        summary = summarize(lines, max_chars=self._summary_max_chars, strategy="deterministic")
        return f"Conversation memory (deterministic fallback):\n{summary}"

    def _summarize_truncate(self, previous_summary: str, archived_messages: list) -> str:
        history_text = self._messages_to_summary_text(archived_messages)
        combined = history_text if not previous_summary else f"{previous_summary}\n{history_text}"
        if not combined.strip():
            return ""
        return combined.strip()[-self._summary_max_chars :]

    def _summarize_history(self, previous_summary: str, archived_messages: list) -> str:
        # Strategy order is intentional: requested strategy first, then deterministic, then truncate.
        if self._summary_strategy == "deterministic":
            return self._summarize_deterministic(previous_summary, archived_messages)
        if self._summary_strategy == "truncate":
            return self._summarize_truncate(previous_summary, archived_messages)

        # Default strategy: llm
        try:
            summary = self._summarize_with_llm(previous_summary, archived_messages)
            if summary and summary.strip():
                return summary.strip()[: self._summary_max_chars]
        except Exception as exc:
            logger.warning(f"LLM summary strategy failed, using deterministic fallback: {exc}")

        deterministic_summary = self._summarize_deterministic(previous_summary, archived_messages)
        if deterministic_summary and deterministic_summary.strip():
            return deterministic_summary.strip()[: self._summary_max_chars]
        return self._summarize_truncate(previous_summary, archived_messages)

    def _compact_context_if_needed(self) -> None:
        if not self._needs_compaction():
            return

        current_estimate = self._estimate_tokens(self._request_messages())
        logger.info(
            "Context compaction triggered for %s (%s): estimated_tokens=%s",
            self._model_name,
            self._source,
            current_estimate,
        )
        keep_count = max(0, self._unsummarized_message_count)
        if len(self._messages) <= keep_count:
            logger.debug(
                "Context compaction skipped: message count (%s) <= keep_recent_turns (%s)",
                len(self._messages),
                keep_count,
            )
            return

        # Compact only the oldest messages; retain the newest unsummarized messages verbatim.
        archived_messages = self._messages[:-keep_count]
        recent_messages = self._messages[-keep_count:] if keep_count > 0 else []
        logger.debug(
            "Compacting context: archived_messages=%s recent_messages_kept=%s strategy=%s",
            len(archived_messages),
            len(recent_messages),
            self._summary_strategy,
        )
        previous_summary = self._summary_message["content"] if self._summary_message else ""
        if self._memory_mode == "recent_only":
            new_summary = ""
            self._summary_message = None
        else:
            new_summary = self._summarize_history(previous_summary, archived_messages)
            self._summary_message = {"role": "system", "content": new_summary} if new_summary else None

        if self._debug_messages:
            self._log_message_payload("archived_messages", archived_messages)
            self._log_message_payload("recent_messages", recent_messages)
            logger.debug(
                "Summary text update for %s (%s): previous_summary=%s new_summary=%s",
                self._model_name,
                self._source,
                self._clip_debug_text(previous_summary),
                self._clip_debug_text(new_summary),
            )
        self._messages = recent_messages
        logger.info(
            "Context compaction complete: summary_created=%s summary_chars=%s remaining_messages=%s",
            bool(self._summary_message),
            len(new_summary) if new_summary else 0,
            len(self._messages),
        )
