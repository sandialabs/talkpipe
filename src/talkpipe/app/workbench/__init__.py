"""Backend services for the ChatterLang workbench IDE features.

Each module exposes a FastAPI ``APIRouter`` (``*_api``) or plain service
logic; ``chatterlang_workbench`` wires the routers into its app. Everything
here builds on the public talkpipe APIs (registry, parser, compiler,
doc extraction, LLM adapters) without modifying them.
"""
