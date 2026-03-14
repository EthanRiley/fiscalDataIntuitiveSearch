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

RANK_PROMPT = """\
You are a fiscal-data routing assistant. Given a user question and a list of candidate \
API endpoints, return ONLY the endpoints genuinely needed to answer the question.

Rules:
- Return the minimum number of endpoints required — if one endpoint clearly answers the question, return only that one.
- Return at most 5 endpoints.
- Do not pad the list. Only include endpoints that are directly relevant.

You must respond with a raw JSON array of endpoint path strings and nothing else.
Do not use markdown. Do not use code fences. Do not explain.
Your entire response must be parseable by JSON.loads().

Example — clear single-dataset question:
  Question: "How much has the national debt changed in the last 5 years?"
  Output: ["v2/accounting/od/debt_to_penny"]

Example — multi-dataset question:
  Question: "Compare interest rates and deficit spending since 2020."
  Output: ["v2/accounting/od/avg_interest_rates", "v1/accounting/mts/mts_table_5"]

User question: {question}

Candidate endpoints:
{endpoints}

Output:"""

CHART_SPECS_PROMPT = """\
You are a fiscal-data chart planner. The user has asked a question about U.S. Treasury data.
Below is a filtered list of the most relevant API endpoints and their fields.

Today's date is {today}. Use this to calculate exact start dates for any time range the user mentions.

Your job is to respond with ONLY a valid JSON array — no markdown, no explanation.
Each element represents one chart and must have these keys:

  title       : string  — short descriptive chart title
  endpoint    : string  — API endpoint path (e.g. v2/accounting/od/debt_to_penny)
  x_column    : string  — field name for the x axis (usually a date field)
  y_column    : string  — field name for the y axis
  viz_filters : string  — Fiscal Data filter covering EXACTLY the user's time range,
                          format record_date:gte:YYYY-MM-DD calculated from today.
                          Empty string if no time range specified.
  viz_sort    : string  — sort for the fetch (e.g. record_date for ascending)
  periodicity : string  — the natural time grouping for this question's scope.
                          Must be one of: decade, year, month, week, day.
                          Choose the periodicity that matches the question's time range:
                          - decade: 20+ years
                          - year: 2-20 years
                          - month: 1 month to 2 years
                          - week: 1 week to 3 months
                          - day: less than 1 week or asking for daily granularity

The visualization data will be filtered to one record per period using `periodicity`,
and that filtered data will be passed to an analyst agent to write the summary blurb.
Generate as many charts as genuinely needed — usually 1, sometimes 2-3 for comparative questions.

METADATA:
{metadata}

USER QUESTION:
{question}
"""

ANALYSIS_PROMPT = """\
You are a fiscal-data analyst. Answer the user's question based solely on the real data summaries below.
Write 2-4 clear, concise sentences. Cite specific numbers and date ranges. Do not guess or extrapolate.

USER QUESTION:
{question}

DATA SUMMARIES:
{summaries}

Answer:"""


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

    def rank_endpoints(self, question: str, candidates: list[dict], session_id: str) -> list[dict]:
        """
        Use Haiku to pick the 5 most relevant endpoints from the candidate list.
        Returns a filtered subset of the candidates dicts (preserving full field info).
        Falls back to the full candidate list if ranking fails.
        """
        endpoint_lines = "\n".join(
            f"- {d['endpoint']}: {d['title']}" for d in candidates
        )
        rank_prompt = RANK_PROMPT.format(question=question, endpoints=endpoint_lines)

        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            messages=[{"role": "user", "content": rank_prompt}],
        )
        text = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()
        token_logger.record_stage(
            session_id=session_id,
            stage="endpoint_ranking",
            model="claude-haiku-4-5-20251001",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            prompt=rank_prompt,
            response=text,
        )

        try:
            ranked_paths = json.loads(text)
            if not isinstance(ranked_paths, list):
                return candidates
            path_set = set(ranked_paths)
            ranked = [d for d in candidates if d["endpoint"] in path_set]
            return ranked if ranked else candidates
        except json.JSONDecodeError:
            return candidates

    # ── Chart specs ──────────────────────────────────────────

    def build_chart_specs(self, question: str) -> tuple[list, str]:
        """
        Full pipeline:
          1. Haiku: extract keywords
          2. Local: filter metadata via search()
          3. Haiku: rank to minimum needed endpoints
          4. Sonnet: produce list of chart specs (viz + analysis params per chart)

        Returns (specs_list, session_id).
        On error specs_list is [{"error": "..."}].
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
            return [{"error": "Could not find any relevant datasets for that question."}], session_id

        ranked_metadata = self.rank_endpoints(question, relevant_metadata, session_id)

        prompt = CHART_SPECS_PROMPT.format(
            today=date.today().isoformat(),
            metadata=json.dumps(ranked_metadata, indent=2),
            question=question,
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()
        token_logger.record_stage(
            session_id=session_id,
            stage="chart_specs",
            model=self.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            prompt=prompt,
            response=text,
        )

        try:
            specs = json.loads(text)
            if isinstance(specs, list):
                return specs, session_id
            return [{"error": f"Agent returned unexpected structure: {text}"}], session_id
        except json.JSONDecodeError:
            return [{"error": f"Agent returned invalid JSON: {text}"}], session_id

    # ── Analysis blurb ───────────────────────────────────────

    def build_analysis(self, question: str, summaries: list[dict], session_id: str) -> str:
        """
        Sonnet analyst: receives compact data summaries and writes a blurb.
        Each summary is {"title": ..., "records": [...]}.
        Returns the blurb string.
        """
        summary_text = ""
        for s in summaries:
            summary_text += f"\n{s['title']}:\n"
            for row in s["records"]:
                summary_text += "  " + ", ".join(f"{k}: {v}" for k, v in row.items()) + "\n"

        prompt = ANALYSIS_PROMPT.format(question=question, summaries=summary_text.strip())

        response = self.client.messages.create(
            model=self.model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()
        token_logger.record_stage(
            session_id=session_id,
            stage="analysis",
            model=self.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            prompt=prompt,
            response=text,
        )
        return text

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
