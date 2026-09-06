"""Seeds fake config env vars before collection.

agent/config.py fails loudly at import if these are unset -- correct
for running the agent for real, but tests import the agent package
without live credentials (they mock the Grafana MCPToolset and never
call Gemini). setdefault leaves a real, already-configured environment
untouched.
"""

import os

os.environ.setdefault("GOOGLE_API_KEY", "test-fake-key")
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")
os.environ.setdefault("GRAFANA_URL", "http://localhost:3000")
os.environ.setdefault("GRAFANA_SERVICE_ACCOUNT_TOKEN", "test-fake-token")
