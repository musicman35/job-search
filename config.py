"""Companies, ATS endpoints, filter keywords, user profile, schema."""

# Each company has one or more sources. Workday JSON endpoint pattern:
#   https://{host}/wday/cxs/{tenant}/{site}/jobs
COMPANIES = [
    {
        "name": "LexisNexis",
        "tier": 1,
        "sources": [
            {
                "type": "workday",
                "host": "relx.wd3.myworkdayjobs.com",
                "tenant": "relx",
                "site": "RELX",
            },
        ],
    },
    {
        "name": "AIG",
        "tier": 1,
        "sources": [
            {
                "type": "workday",
                "host": "aig.wd1.myworkdayjobs.com",
                "tenant": "aig",
                "site": "aig",
            },
            {
                "type": "workday",
                "host": "aig.wd1.myworkdayjobs.com",
                "tenant": "aig",
                "site": "early_careers",
            },
        ],
    },
    {
        "name": "Home Depot",
        "tier": 1,
        "sources": [
            {
                "type": "workday",
                "host": "homedepot.wd5.myworkdayjobs.com",
                "tenant": "homedepot",
                "site": "CareerDepot",
            },
        ],
    },
    {
        "name": "Cox",
        "tier": 2,
        "sources": [
            {
                "type": "workday",
                "host": "cox.wd1.myworkdayjobs.com",
                "tenant": "cox",
                "site": "Cox_External_Career_Site_1",
            },
        ],
    },
    {
        "name": "Truist",
        "tier": 2,
        "sources": [
            {
                "type": "workday",
                "host": "truist.wd1.myworkdayjobs.com",
                "tenant": "truist",
                "site": "Careers",
            },
        ],
    },
    {
        "name": "State Farm",
        "tier": 3,
        "sources": [
            # State Farm's public-facing listing is Phenom-powered; iCIMS is
            # only the apply backend. Phenom returns clean JSON with multi-
            # location and full description inline, so no detail fetch needed.
            {
                "type": "phenom",
                "host": "jobs.statefarm.com",
                "client_code": "statefarm",
            },
        ],
    },
    {
        "name": "Dick's Sporting Goods",
        "tier": 3,
        "sources": [
            {
                "type": "workday",
                "host": "dickssportinggoods.wd1.myworkdayjobs.com",
                "tenant": "dickssportinggoods",
                "site": "DSG",
            },
        ],
    },
    {
        "name": "Bank of America",
        "tier": 3,
        "sources": [
            {
                "type": "workday",
                "host": "ghr.wd1.myworkdayjobs.com",
                "tenant": "ghr",
                "site": "Lateral-US",
            },
            # NOTE: BoA's campus careers (ADP, GTAP, etc.) live on
            # bankcampuscareers.tal.net (WCN/Lumesse), whose /vx/api/jobs
            # is SSO-locked (Shibboleth, no_local_login). No anonymous
            # public API. Monitor manually at:
            #   https://careers.bankofamerica.com/en-us/programs/early-career-programs
            # Rotational programs there post in annual batches.
        ],
    },
]

# Category A: individual contributor DS/ML/AI roles.
IC_KEYWORDS = [
    "data scientist",
    "machine learning",
    "ml engineer",
    "ai engineer",
    "applied scientist",
    "genai",
    "mlops",
]

IC_EXCLUDES = ["intern", "principal", "staff", "director", "vp"]

# Category B: rotational / development programs. No exclude list (per spec).
ROTATIONAL_KEYWORDS = [
    "rotational",
    "rotation program",
    "development program",
    "leadership development",
    "early career",
    "graduate program",
    "associate program",
    "analytics rotation",
    "data rotation",
    "technology development",
    "emerging leader",
    "accelerator program",
]

# Location filter: any of these substrings in a posting's location string passes.
LOCATION_KEYWORDS = ["atlanta", "remote", "online", "georgia", ", ga"]

# Controlled vocabulary for the LLM's `track` field (rotational only).
TRACK_VOCAB = [
    "Data Science",
    "Analytics",
    "Software Engineering",
    "Data Engineering",
    "Product Management",
    "Finance",
    "Sales",
    "Operations",
    "General Management",
    "Mixed Technical",
    "Mixed Business",
    "Unclear",
]

# Tracks that qualify a rotational program for the "top picks" email bucket.
TECHNICAL_TRACKS = {
    "Data Science",
    "Analytics",
    "Software Engineering",
    "Data Engineering",
    "Mixed Technical",
}

# Dropped verbatim into the cached Claude system prompt.
USER_PROFILE = """MS Analytics from Georgia State University, Data Science concentration, May 2026 grad. Prior career in civil engineering (Town of Estes Park, CO). Core technical: RAG evaluation frameworks (built CLEAR with Truist), multi-agent orchestration with LangChain/LangGraph, GenAI systems, LLM-as-judge, OpenTelemetry monitoring, Snowflake time series forecasting. Multi-agent music recommendation system with Qdrant + Cohere reranking, 0.92 Precision@5. AWS Cloud Practitioner + AI Practitioner certified. Python primary. Located in Atlanta, GA. Looking for DS/ML/AI roles or rotational programs that include a data/analytics/tech track.

For rotational programs specifically, score fit based on whether the program includes meaningful data, analytics, ML, or engineering exposure, not just business/sales rotations."""

# CSV schema, canonical column order.
CSV_COLUMNS = [
    "job_id",
    "company",
    "tier",
    "category",
    "track",
    "title",
    "location",
    "remote_type",
    "url",
    "posted_date",
    "first_seen",
    "last_seen",
    "status",
    "fit_score",
    "key_reqs",
    "notes",
]

CSV_PATH = "data/jobs.csv"

LLM_MODEL = "claude-haiku-4-5-20251001"

# Statuses that auto-flip to "closed" when a posting disappears from a fetch.
ACTIVE_STATUSES = {"new", "open"}

# User-set statuses that must never be auto-overwritten.
MANUAL_STATUSES = {"applied", "interviewing", "rejected"}
