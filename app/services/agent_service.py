"""
Agent service — wraps the Anthropic API with a system prompt specialised
for U.S. fiscal data and optional tool-use for live data queries.
"""

import json
import anthropic
from app.services.fiscal_data import FiscalDataClient


SYSTEM_PROMPT = """\
You are a fiscal-data analyst assistant embedded in the fiscalDataIntuitiveSearch
dashboard.  Your job is to help users understand datasets published by the U.S.
Treasury at api.fiscaldata.treasury.gov.

Capabilities:
• Answer plain-language questions about federal debt, interest rates, Treasury
  statements, and other public fiscal datasets.
• When a question requires live data, call the `query_fiscal_data` tool to
  fetch it, then summarise the results in clear language.
• When asked for a visualisation, return a Plotly JSON spec (as a fenced
  ```plotly-json``` block) that the front-end will render.

Guidelines:
• Cite the specific dataset and date range when you reference numbers.
• Keep answers concise — prefer bullet points and short paragraphs.
• If you are unsure, say so rather than guessing.
"""

TOOLS = [
    {
        "name": "query_fiscal_data",
        "description": (
            "Query the Fiscal Data API. Returns JSON records from the "
            "specified endpoint. Use this whenever the user asks a question "
            "that requires recent or specific fiscal data."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "endpoint": {
                    "type": "string",
                    "description": "API endpoint path, e.g. v2/accounting/od/debt_to_penny",
                },
                "fields": {
                    "type": "string",
                    "description": "Comma-separated field names to return.",
                },
                "filter": {
                    "type": "string",
                    "description": "Fiscal Data filter expression, e.g. record_date:gte:2024-01-01",
                },
                "sort": {
                    "type": "string",
                    "description": "Sort expression, e.g. -record_date",
                },
                "page_size": {
                    "type": "integer",
                    "description": "Number of records to return (max 10000).",
                    "default": 100,
                },
            },
            "required": ["endpoint"],
        },
    }
]


class AgentService:
    def __init__(self, app_config: dict):
        self.client = anthropic.Anthropic(api_key=app_config.get("ANTHROPIC_API_KEY", ""))
        self.fiscal = FiscalDataClient(
            app_config.get(
                "FISCAL_DATA_BASE_URL",
                "https://api.fiscaldata.treasury.gov/services/api/fiscal_service",
            )
        )
        self.model = "claude-sonnet-4-20250514"

    # ── Synchronous (non-streaming) ──────────────────────────

    def answer(self, message: str, history: list[dict]) -> dict:
        messages = history + [{"role": "user", "content": message}]

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # Handle tool-use loop (single round for now)
        if response.stop_reason == "tool_use":
            response = self._handle_tool_calls(response, messages)

        text = "".join(
            block.text for block in response.content if block.type == "text"
        )
        return {"reply": text}

    # ── Streaming variant ────────────────────────────────────

    def answer_stream(self, message: str, history: list[dict]):
        messages = history + [{"role": "user", "content": message}]

        with self.client.messages.stream(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                yield json.dumps({"token": text})

    # ── Tool execution ───────────────────────────────────────

    def _handle_tool_calls(self, response, messages):
        tool_results = []

        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name == "query_fiscal_data":
                result = self._run_fiscal_query(block.input)
            else:
                result = {"error": f"Unknown tool: {block.name}"}

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                }
            )

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        return self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

    def _run_fiscal_query(self, tool_input: dict) -> dict:
        endpoint = tool_input.get("endpoint", "")
        params = {}
        if tool_input.get("fields"):
            params["fields"] = tool_input["fields"]
        if tool_input.get("filter"):
            params["filter"] = tool_input["filter"]
        if tool_input.get("sort"):
            params["sort"] = tool_input["sort"]
        params["page[size]"] = str(tool_input.get("page_size", 100))

        data, error = self.fiscal.fetch(endpoint, params)
        if error:
            return {"error": error}
        return data
