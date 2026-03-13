# fiscalDataIntuitiveSearch

An interactive Flask dashboard for exploring U.S. fiscal data from the [Fiscal Data API](https://api.fiscaldata.treasury.gov). Features Plotly-powered visualizations and an embedded AI agent for natural-language queries about federal financial datasets.

## Architecture

```
app/
├── routes/          # Flask blueprints (main UI, API proxy, agent endpoints)
├── services/        # Business logic (Fiscal Data client, agent orchestration)
├── static/          # CSS, JS (Plotly dashboards, agent chat widget)
└── templates/       # Jinja2 HTML templates
```

## Quickstart

```bash
# Clone
git clone https://github.com/<your-username>/fiscalDataIntuitiveSearch.git
cd fiscalDataIntuitiveSearch

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your API keys

# Run
python run.py
```

Open [http://localhost:5000](http://localhost:5000)

## Docker

```bash
docker-compose up --build
```

## Key Dependencies

| Package | Purpose |
|---------|---------|
| Flask | Web framework |
| Plotly | Interactive data visualizations |
| Pandas | Data manipulation |
| Anthropic | AI agent for dataset Q&A |
| Gunicorn | Production WSGI server |

## Fiscal Data API

This app queries endpoints from `https://api.fiscaldata.treasury.gov/services/api/fiscal_service/`. No API key is required. Common datasets include:

- `/v2/accounting/od/debt_to_penny` — Daily national debt
- `/v1/accounting/mts/mts_table_5` — Monthly Treasury Statement
- `/v2/accounting/od/avg_interest_rates` — Average interest rates on Treasury securities
- `/v1/accounting/dts/dts_table_1` — Daily Treasury Statement

## License

MIT
