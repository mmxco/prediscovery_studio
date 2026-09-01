# Retail ERP Pre-Discovery Studio

**TL;DR**
A Streamlit-based web application that automates presales research by synthesizing prospect firmographics, tech stacks, and job posting signals into generic executive briefing PDFs using AI.

## Business Problem
* Manual presales research is inefficient and scales poorly across multiple target accounts.
* This application automates the aggregation of firmographics, BuiltWith tech data, and scraped job postings[cite: 9].
* It uses AI to map identified operational friction to modern Retail ERP solutions[cite: 9].
* The pipeline standardizes presales deliverables by generating an Executive Briefing as a downloadable PDF[cite: 9].

## Data Guardrails
* The AI prompt baseline utilizes an aggregate of functionality from Tier-1 platforms like Oracle, SAP, and Microsoft Dynamics[cite: 6].
* Technical deficits are mapped strictly to generic terminology, such as 'Unified Inventory Management' or 'Dynamic Price Management'[cite: 6].
* The system is explicitly instructed to never mention specific vendor or platform names in the generated output[cite: 6].

## Solution Architecture
* **Frontend Application:** Built on Streamlit (`1.42.0`)[cite: 8], utilizing `st.session_state` to persistently store user inputs and scenario data across interactions[cite: 6].
* **Data Ingestion:** Executes synchronous HTML parsing via `requests` and `beautifulsoup4` to isolate job posting keywords[cite: 6, 8]. Domain technology stacks are retrieved via the BuiltWith API[cite: 6].
* **AI Orchestration:** Implements dynamic routing logic to process context through either Google Gemini (`gemini-2.5-flash`) or OpenAI (`gpt-4o`) based on user selection[cite: 6].
* **Document Generation:** Sanitizes LLM markdown output and renders a structured PDF document using the `reportlab` library[cite: 6, 8].

## Execution Instructions
* **System Dependencies:** Cloud deployment requires a Debian-based container to install OS-level libraries defined in `packages.txt`, including `libnss3`, `libgtk-3-0`, and `libx11-xcb1`[cite: 7].
* **Python Environment:** The environment requires the packages specified in `requirements.txt`, which include `google-genai`, `openai`, `beautifulsoup4`, and `reportlab`[cite: 8].
* **Authentication & Execution:** To run the pre-discovery pipeline, users must input a valid Gemini or OpenAI API key into the sidebar interface[cite: 6]. A BuiltWith API key is optional but required for full tech stack analysis[cite: 6].
