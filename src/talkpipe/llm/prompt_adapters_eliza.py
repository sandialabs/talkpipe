import re
from typing import Optional, Union

from pydantic import BaseModel

from .content import UserTurn, user_turn_text
from .prompt_adapter_base import AbstractLLMPromptAdapter, logger


class ElizaPromptAdapter(AbstractLLMPromptAdapter):
    """Deterministic, local ELIZA-like prompt adapter.

    This adapter does not call an external LLM provider. It implements the same
    prompt-adapter contract as cloud/local providers so it can be used with
    ``LLMPrompt`` and guided-generation segments.
    """

    _STOPWORDS = {
        "the", "and", "that", "this", "with", "from", "about", "would", "could", "should",
        "your", "you", "have", "what", "when", "where", "which", "there", "their", "them",
        "they", "into", "while", "just", "been", "being", "were", "will", "then", "than",
    }

    _FEELING_TEMPLATES = (
        "Feelings usually carry useful data; what seems to be driving that today?",
        "That feeling sounds important; when did it become most noticeable?",
        "If that feeling had a headline, what would it be?",
    )

    _BECAUSE_TEMPLATES = (
        "Is that the main reason, or just the first explanation that arrived?",
        "That reason makes sense; what evidence supports it most strongly?",
        "If we tested that reason, what result would surprise you?",
    )

    _SORRY_TEMPLATES = (
        "No apology needed; we can work with what is true right now.",
        "You do not need to apologize here; what part feels unresolved?",
        "Thanks for saying that. What would make this conversation more useful for you?",
    )

    _GREETING_TEMPLATES = (
        "Hello. What has been taking up the most space in your mind lately?",
        "Good to meet you. What would you like to untangle first?",
        "Hi there. What question keeps returning for you?",
    )

    _QUESTION_TEMPLATES = (
        "That is a strong question. What answer are you hoping not to hear?",
        "Useful question. Which answer would change your next decision?",
        "Good question. What assumptions are you carrying into it?",
    )

    _DEFAULT_TEMPLATES = (
        "Say a little more, and include one concrete detail if you can.",
        "Give me one specific example so we can work with something tangible.",
        "Keep going. What part feels most important right now?",
        "If you had to summarize this in one sentence, what would it be?",
        "What happened just before this became a concern?",
    )

    def __init__(
        self,
        model: str,
        system_prompt: Optional[str] = "You are a helpful assistant.",
        multi_turn: bool = True,
        temperature: float = None,
        output_format: BaseModel = None,
        role_map: str = None,
        memory_mode: str = "full",
        unsummarized_message_count: int = 6,
        context_token_trigger: Optional[Union[int, float]] = None,
        memory_size: int = 512,
        debug_messages: bool = False,
    ):
        super().__init__(
            model,
            "eliza",
            system_prompt,
            multi_turn,
            temperature,
            output_format,
            role_map,
            memory_mode,
            unsummarized_message_count,
            context_token_trigger,
            memory_size,
            debug_messages,
        )
        self._facts: list[str] = []
        self._turn_count = 0
        self._identity_introduced = False
        self._name_query_count = 0

    def execute(self, prompt: str) -> str:
        logger.debug(f"Adding user message to chat history: {prompt}")
        self._messages.append({"role": "user", "content": prompt})
        self._compact_context_if_needed()
        self._capture_facts(prompt)
        self._turn_count += 1

        request_params = {
            "model": self._model_name,
            "messages": self._request_messages(),
            "output_format": self._output_format,
        }
        self._log_message_payload("messages", request_params["messages"])
        response = self._messages_create(**request_params)

        response_text = str(response["text"])
        self._record_assistant_response(response_text)

        if self._output_format:
            result = response["structured"]
        else:
            result = response_text

        logger.debug(f"Returning response: {result}")
        return result

    def execute_turn(self, user_turn: UserTurn) -> str:
        prompt = user_turn_text(user_turn)
        if not prompt.strip():
            prompt = "(shared an image without text)"
        return self.execute(prompt)

    def _messages_create(self, model: str, messages: list, output_format=None) -> dict:
        latest_user_text = ""
        for message in reversed(messages):
            if str(message.get("role", "")).lower() == "user":
                latest_user_text = str(message.get("content", ""))
                break

        text_reply = self._build_response_text(latest_user_text)
        structured = None
        if output_format is not None:
            structured = self._build_structured_response(latest_user_text)

        return {
            "model": model,
            "text": text_reply,
            "structured": structured,
        }

    def _build_response_text(self, prompt: str) -> str:
        lower = prompt.lower().strip()

        if self._is_bot_name_query(lower):
            self._name_query_count += 1
            if self._name_query_count >= 2:
                self._identity_introduced = True
                return f"I am {self._model_name}. You asked again, and consistency matters."
            return f"My name is {self._model_name}."

        if "first name" in lower or "my name" in lower and "what" in lower:
            known_name = self._find_fact("your name is")
            if known_name:
                response = f"Earlier you said your name is {known_name}. Is that still how you introduce yourself?"
                return self._with_identity_if_needed(response)

        if lower.startswith("i feel"):
            base = self._choose_template(self._FEELING_TEMPLATES, lower, "feel")
        elif "because" in lower:
            base = self._choose_template(self._BECAUSE_TEMPLATES, lower, "because")
        elif "sorry" in lower:
            base = self._choose_template(self._SORRY_TEMPLATES, lower, "sorry")
        elif "hello" in lower or "hi" in lower:
            base = self._choose_template(self._GREETING_TEMPLATES, lower, "greet")
        elif "?" in lower:
            base = self._choose_template(self._QUESTION_TEMPLATES, lower, "question")
        else:
            base = self._choose_template(self._DEFAULT_TEMPLATES, lower, "default")

        response = self._with_identity_if_needed(base)
        memory_line = self._occasional_memory_line()
        if memory_line:
            response = f"{response} {memory_line}"
        return response

    def _with_identity_if_needed(self, base: str) -> str:
        if self._identity_introduced:
            return base
        self._identity_introduced = True
        return f"I am {self._model_name}. {base}"

    def _is_bot_name_query(self, prompt_lower: str) -> bool:
        return bool(
            re.search(r"\b(what('?s| is) your name|who are you|your name\?)\b", prompt_lower)
        )

    def _choose_template(self, templates: tuple[str, ...], prompt_lower: str, branch: str) -> str:
        if len(templates) == 1:
            return templates[0]
        salt = sum(ord(char) for char in (prompt_lower + branch))
        index = (salt + self._turn_count) % len(templates)
        return templates[index]

    def _capture_facts(self, prompt: str) -> None:
        for pattern in (
            r"\bmy name is\s+([A-Za-z][A-Za-z\-']+)\b",
            r"\bi am from\s+([A-Za-z][A-Za-z\-\s']+)\b",
            r"\bi work as\s+([A-Za-z][A-Za-z\-\s']+)\b",
            r"\bi like\s+([A-Za-z][A-Za-z\-\s']+)\b",
            r"\bi love\s+([A-Za-z][A-Za-z\-\s']+)\b",
        ):
            match = re.search(pattern, prompt, flags=re.IGNORECASE)
            if not match:
                continue
            value = match.group(1).strip(" .,!?:;\"'")
            if pattern.startswith(r"\bmy name"):
                fact = f"your name is {value}"
            elif pattern.startswith(r"\bi am from"):
                fact = f"you are from {value}"
            elif pattern.startswith(r"\bi work as"):
                fact = f"you work as {value}"
            else:
                fact = f"you enjoy {value}"
            self._remember_fact(fact)

    def _remember_fact(self, fact: str) -> None:
        normalized = fact.lower()
        if any(existing.lower() == normalized for existing in self._facts):
            return
        self._facts.append(fact)
        if len(self._facts) > 5:
            self._facts = self._facts[-5:]

    def _find_fact(self, prefix: str) -> Optional[str]:
        prefix_lower = prefix.lower().strip()
        for fact in reversed(self._facts):
            if fact.lower().startswith(prefix_lower):
                return fact[len(prefix):].strip()
        return None

    def _occasional_memory_line(self) -> str:
        if not self._multi_turn or not self._facts:
            return ""
        if self._turn_count % 3 != 0:
            return ""
        fact_index = (self._turn_count // 3 - 1) % len(self._facts)
        return f"You mentioned earlier that {self._facts[fact_index]}."

    def _build_structured_response(self, prompt: str):
        fields = set(self._output_format.model_fields)
        if fields == {"score", "explanation"}:
            score = self._heuristic_score(prompt)
            payload = {
                "score": score,
                "explanation": (
                    f"{self._model_name} assigned {score}/10 using clarity, specificity, and emotional signal as generic heuristics."
                ),
            }
            return self._output_format.model_validate(payload)

        if fields == {"answer", "explanation"}:
            answer = self._heuristic_binary_answer(prompt)
            payload = {
                "answer": answer,
                "explanation": (
                    f"{self._model_name} inferred {'yes' if answer else 'no'} from lexical cues and explicit negation."
                ),
            }
            return self._output_format.model_validate(payload)

        if fields == {"terms"}:
            payload = {"terms": self._extract_terms(prompt)}
            return self._output_format.model_validate(payload)

        payload = {}
        for field_name, field_info in self._output_format.model_fields.items():
            annotation = field_info.annotation
            if annotation is int:
                payload[field_name] = self._heuristic_score(prompt)
            elif annotation is bool:
                payload[field_name] = self._heuristic_binary_answer(prompt)
            elif annotation is list[str]:
                payload[field_name] = self._extract_terms(prompt)
            else:
                payload[field_name] = self._build_response_text(prompt)
        return self._output_format.model_validate(payload)

    def _heuristic_score(self, prompt: str) -> int:
        text = prompt.lower()
        score = 5
        for word in ("clear", "specific", "relevant", "focused", "strong"):
            if word in text:
                score += 1
        for word in ("unclear", "vague", "irrelevant", "confused", "weak"):
            if word in text:
                score -= 1
        if len(text) > 220:
            score += 1
        if len(text) < 40:
            score -= 1
        return max(0, min(10, score))

    def _heuristic_binary_answer(self, prompt: str) -> bool:
        text = prompt.lower()
        if re.search(r"\b(no|not|never|cannot|can't|false|incorrect|wrong)\b", text):
            return False
        if re.search(r"\b(yes|true|can|will|correct|right)\b", text):
            return True
        return self._heuristic_score(prompt) >= 5

    def _extract_terms(self, prompt: str) -> list[str]:
        words = re.findall(r"[A-Za-z][A-Za-z\-']{2,}", prompt.lower())
        terms = []
        for word in words:
            if word in self._STOPWORDS:
                continue
            if word not in terms:
                terms.append(word)
            if len(terms) >= 8:
                break
        return terms

    def complete_text_without_context(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> str:
        del temperature, max_tokens
        response = self._messages_create(
            model=model or self._model_name,
            messages=[{"role": "user", "content": prompt}],
            output_format=None,
        )
        return str(response["text"]).strip()

    def is_available(self) -> bool:
        return True
