import time
from typing import Any, AsyncIterator
from ..llm import LLMClient, LLMError, assemble_messages, get_llm_client
from ..safety import MODEL_INJECTION_GUARD
# from ..market_data import (
#     benchmark_ticker,
#     get_history_returns,
#     get_quote,
#     Quote,
# )

class Time:
    name = "time"
    async def run(
        self,
        *,
        query:str,
        user_context:dict[str,Any],
        classification:dict[str,Any],
        llm:LLMClient | None=None
    ) -> AsyncIterator[dict[str,Any]]:
    # IMPL
        try:
            # time = time.get_clock_info()
            time1 = time.time()
            structured = time1
        except Exception as exc:
            yield {
                "type": "structured",
                "payload": {
                    "agent": self.name,
                    "error": "compute_failed",
                    "message": str(exc),

                },
            }

       