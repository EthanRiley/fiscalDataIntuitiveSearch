"""
Agent service — wraps the Anthropic API with a system prompt specialised
for U.S. fiscal data and optional tool-use for live data queries.
"""

import json
from datetime import date
import anthropic
from app.services.fiscal_data import FiscalDataClient
from app.services.metadata_service import search
from app.services import token_logger

KEYWORD_PROMPT = """\
Extract the minimum number of keywords needed to identify the relevant U.S. Treasury \
financial dataset for the question below. Be as concise as possible — if one or two \
keywords are sufficient, use only those. Only add more keywords if the question is \
ambiguous or covers multiple distinct topics.

You must respond with a raw JSON array of lowercase strings and nothing else.
Do not use markdown. Do not use code fences. Do not explain.
Your entire response must be parseable by JSON.loads().

Example input: How much has the national debt grown in the last 5 years?
Example output: ["national debt"]

Example input: Compare interest rates and deficit spending since 2020.
Example output: ["interest rates", "deficit", "spending"]

Question: {question}
Output:"""

CHART_SPEC_PROMPT = """\
You are a fiscal-data analyst. The user has asked a question about U.S. Treasury data.
Below is a filtered list of the most relevant API endpoints and their fields.

Today's date is {today}. Use this to calculate exact start dates for any time range the user mentions.

Your job is to respond with ONLY a valid JSON object — no markdown, no explanation — with these keys:
  blurb     : string  — a clear, concise plain-language answer to the user's question (2-4 sentences)
  endpoint  : string  — the API endpoint path to query (e.g. v2/accounting/od/debt_to_penny)
  x_column  : string  — the field name to use as the x axis
  y_column  : string  — the field name to use as the y axis
  filters   : string  — a Fiscal Data filter expression covering EXACTLY the time range the user asked for,
                        in the format record_date:gte:YYYY-MM-DD. Calculate the start date yourself from
                        today's date. If the user mentions no time range, return an empty string.
  sort      : string  — sort expression for time-series data (e.g. record_date)

IMPORTANT: The filter is the only thing controlling how much data is returned. Be precise.

METADATA:
{metadata}

USER QUESTION:
{question}
"""


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

    # ── Keyword extraction ───────────────────────────────────

    def extract_keywords(self, question: str, session_id: str) -> list[str]:
        """
        Use Haiku to pull search keywords from the user's question.
        Returns a list of lowercase keyword strings.
        """
        keyword_prompt = KEYWORD_PROMPT.format(question=question)
        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=128,
            messages=[{"role": "user", "content": keyword_prompt}],
        )
        text = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()
        token_logger.record_stage(
            session_id=session_id,
            stage="keyword_extraction",
            model="claude-haiku-4-5-20251001",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            prompt=keyword_prompt,
            response=text,
        )
        try:
            keywords = json.loads(text)
            return keywords if isinstance(keywords, list) else []
        except json.JSONDecodeError:
            return []

    # ── Chart spec (Option A — structured JSON response) ────────

    def build_chart_spec(self, question: str) -> tuple[dict, str]:
        """
        Two-stage pipeline:
          1. Extract keywords from the question (Haiku, cheap).
          2. Filter metadata down to the most relevant endpoints.
          3. Ask Sonnet to pick the best endpoint/columns and write a blurb.

        Returns (spec_dict, session_id).
        On failure spec_dict contains {"error": "..."}.
        """
        session_id = token_logger.start_session(question)
        keywords = self.extract_keywords(question, session_id)
        relevant_metadata = search(keywords) if keywords else []

        token_logger.record_search(
            session_id=session_id,
            keywords=keywords,
            matched_endpoints=[d["endpoint"] for d in relevant_metadata],
        )

        if not relevant_metadata:
            return {"error": "Could not find any relevant datasets for that question."}, session_id

        prompt = CHART_SPEC_PROMPT.format(
            today=date.today().isoformat(),
            metadata=json.dumps(relevant_metadata, indent=2),
            question=question,
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()
        token_logger.record_stage(
            session_id=session_id,
            stage="chart_spec",
            model=self.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            prompt=prompt,
            response=text,
        )

        try:
            return json.loads(text), session_id
        except json.JSONDecodeError:
            return {"error": f"Agent returned invalid JSON: {text}"}, session_id

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
        response_text = "".join(
            block.text for block in response.content if block.type == "text"
        )
        token_logger.record(
            model=self.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            prompt=json.dumps(messages),
            response=response_text,
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

        followup = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        followup_text = "".join(
            block.text for block in followup.content if block.type == "text"
        )
        token_logger.record(
            model=self.model,
            input_tokens=followup.usage.input_tokens,
            output_tokens=followup.usage.output_tokens,
            prompt=json.dumps(messages),
            response=followup_text,
        )
        return followup

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
