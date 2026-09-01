import streamlit as st
import os
import json
import time
import re
import html
import asyncio
import requests
import concurrent.futures
from bs4 import BeautifulSoup

# Ensure Playwright binaries are installed on the Streamlit Cloud container
os.system("playwright install chromium")

from google import genai
from google.genai import types
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, HRFlowable
from reportlab.lib import colors

CACHE_FILE = ".prediscovery_cache.json"

SCENARIOS = {
    "New Prospect / Blank Canvas": {
        "domain": "", "dba": "", "revenue": "", 
        "headcount": "", "careers_url": "", "bdr_notes": ""
    },
    "Scenario 1: Regional Assortment & Allocation Misalignment (Inventory)": {
        "domain": "bigronline.com",
        "dba": "Big R Stores",
        "revenue": "$1.2B",
        "headcount": "12500",
        "careers_url": "https://www.bigronline.com/careers",
        "bdr_notes": "Director of Merchandising mentioned regional store clusters are too broad. Southern stores receive heavy winter apparel allocations meant for Northern stores, causing $1.2M in inter-store transfer freight and severe localized stockouts."
    }
}

def load_cache() -> dict:
    """Loads historical session data and API responses to minimize redundant calls."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"tech_stack": {}, "job_postings": {}, "last_entry": None}

def save_cache(cache_data: dict):
    """Persists session data to the local file system."""
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache_data, f, indent=2)
    except Exception as e:
        print(f"[!] Warning: Failed to write cache file: {e}")

def _fast_path_scrape(careers_url: str) -> list:
    """Lightweight, compute-efficient web scraper using Requests & BeautifulSoup."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }
        resp = requests.get(careers_url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return []
            
        soup = BeautifulSoup(resp.text, 'html.parser')
        keywords = ["clerk", "entry", "legacy", "manual", "coordinator", "analyst", "pricing", "buyer"]
        jobs_data = []
        
        for tag in soup.find_all(['h2', 'h3', 'h4', 'a', 'div', 'span']):
            text = tag.get_text(separator=" ", strip=True)
            if text and len(text) < 120 and any(k in text.lower() for k in keywords):
                jobs_data.append(text)
                
        return list(set(jobs_data)) 
    except Exception:
        return []

async def _async_scrape_job_postings(careers_url: str) -> list:
    """Heavyweight Playwright async scraper (Fallback). Refactored to run natively in event loop."""
    try:
        from playwright.async_api import async_playwright
        jobs_data = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(careers_url, wait_until="networkidle", timeout=20000)
            job_elements = await page.locator('.job-posting-title, .job-title, h3, .position-title').all()
            for job in job_elements:
                title = await job.inner_text()
                if any(k in title.lower() for k in ["clerk", "entry", "legacy", "manual", "coordinator", "analyst", "pricing", "buyer"]):
                    jobs_data.append(title)
            await browser.close()
        return jobs_data
    except Exception as e:
        return [{"info": f"Scraper execution note: {e}"}]

class PreDiscoveryPipeline:
    def __init__(self, builtwith_key: str):
        self.builtwith_key = builtwith_key

    def fetch_tech_stack(self, domain: str, bypass_cache: bool = False) -> dict:
        """Retrieves prospect technology stack via BuiltWith API."""
        cache = load_cache()
        if not bypass_cache and domain in cache.get("tech_stack", {}):
            return cache["tech_stack"][domain]
        if not self.builtwith_key:
            return {"info": "BuiltWith API key omitted. Skipping tech lookup."}
        try:
            url = f"https://api.builtwith.com/v23/api.json?KEY={self.builtwith_key}&LOOKUP={domain}"
            response = requests.get(url, timeout=10)
            res_data = response.json() if response.status_code == 200 else {"error": f"HTTP {response.status_code}"}
            if "error" not in res_data:
                cache.setdefault("tech_stack", {})[domain] = res_data
                save_cache(cache)
            return res_data
        except Exception as e:
            return {"error": str(e)}

    async def scrape_job_postings(self, careers_url: str, bypass_cache: bool = False) -> list:
        """Orchestrates scraping logic, attempting fast path before falling back to Playwright."""
        cache = load_cache()
        if not bypass_cache and careers_url in cache.get("job_postings", {}):
            return cache["job_postings"][careers_url]

        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            jobs = await loop.run_in_executor(pool, _fast_path_scrape, careers_url)
            
        if not jobs:
            jobs = await _async_scrape_job_postings(careers_url)

        if jobs and isinstance(jobs, list) and not isinstance(jobs[0], dict):
            cache.setdefault("job_postings", {})[careers_url] = jobs
            save_cache(cache)
        return jobs

    async def run_pipeline(self, prospect_data: dict, bypass_cache: bool = False) -> str:
        """Aggregates all quantitative signals and contextual CRM data into a structured payload."""
        domain = prospect_data["domain"]
        dba = prospect_data["dba"]
        payload = {
            "firmographics": {
                "legal_name": dba,
                "domain": domain,
                "annual_revenue": prospect_data["revenue"] or "Undisclosed",
                "employee_count": prospect_data["headcount"] or "Undisclosed"
            },
            "bdr_discovery_notes": prospect_data["bdr_notes"] or "No initial BDR call notes provided.",
            "quantitative_signals": {
                "tech_stack": self.fetch_tech_stack(domain, bypass_cache=bypass_cache),
                "job_board_signals": await self.scrape_job_postings(prospect_data["careers_url"], bypass_cache=bypass_cache)
            }
        }
        return json.dumps(payload, indent=2)

class PDFReportGenerator:
    @staticmethod
    def _format_markdown_inline(text: str) -> str:
        """Sanitizes strings and applies basic markdown rendering for PDF conversion."""
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
        return text

    @staticmethod
    def generate_pdf(briefing_text: str, prospect_name: str, output_filename: str) -> str:
        """Translates markdown text from LLM output into a formatted ReportLab PDF."""
        doc = SimpleDocTemplate(output_filename, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=20, leading=24, textColor=colors.HexColor("#1E3A8A"), spaceAfter=6)
        subtitle_style = ParagraphStyle('DocSubTitle', parent=styles['Normal'], fontSize=10, leading=13, textColor=colors.HexColor("#4B5563"), spaceAfter=12)
        heading1_style = ParagraphStyle('SectionHeader1', parent=styles['Heading2'], fontSize=13, leading=16, textColor=colors.HexColor("#1E40AF"), spaceBefore=10, spaceAfter=4)
        heading2_style = ParagraphStyle('SectionHeader2', parent=styles['Heading3'], fontSize=11, leading=14, textColor=colors.HexColor("#1E3A8A"), spaceBefore=8, spaceAfter=3)
        body_style = ParagraphStyle('BodyTextCustom', parent=styles['Normal'], fontSize=9.5, leading=13, textColor=colors.HexColor("#1F2937"), spaceAfter=6)
        
        story = []
        story.append(Paragraph("Executive Pre-Discovery Briefing", title_style))
        story.append(Paragraph(f"<b>Target Account:</b> {html.escape(prospect_name)} | <b>Generated:</b> {time.strftime('%Y-%m-%d')}", subtitle_style))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1E3A8A"), spaceAfter=12))
        
        for line in briefing_text.split('\n'):
            line = line.strip()
            if not line: continue
            try:
                if line.startswith("# "):
                    story.append(Paragraph(PDFReportGenerator._format_markdown_inline(line[2:].strip()), title_style))
                elif line.startswith("## "):
                    story.append(Paragraph(PDFReportGenerator._format_markdown_inline(line[3:].strip()), heading1_style))
                elif line.startswith("### "):
                    story.append(Paragraph(PDFReportGenerator._format_markdown_inline(line[4:].strip()), heading2_style))
                elif line.startswith("* ") or line.startswith("- "):
                    story.append(Paragraph(f"• {PDFReportGenerator._format_markdown_inline(line[2:].strip())}", body_style))
                elif line.startswith("---") or line.startswith("***"):
                    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CBD5E1"), spaceBefore=6, spaceAfter=6))
                else:
                    story.append(Paragraph(PDFReportGenerator._format_markdown_inline(line), body_style))
            except Exception:
                story.append(Paragraph(html.escape(re.sub(r'<[^>]+>', '', line)), body_style))
                
        doc.build(story)
        return output_filename

async def execute_orchestrator(prospect_data, bypass_cache, api_key, builtwith_key):
    """Executes the core pipeline, integrating web scraping, LLM analysis, and PDF generation."""
    pipeline = PreDiscoveryPipeline(builtwith_key)
    raw_data = await pipeline.run_pipeline(prospect_data, bypass_cache)
    
    client = genai.Client(api_key=api_key)
    
    # Updated system instruction for generic Tier-1 ERP mapping
    system_instruction = (
        "You are a Senior Solutions Engineer specializing in Retail Enterprise Architecture. "
        "Analyze the provided CRM context and quantitative signals using the 'Value Triangle' "
        "(Technical Gap -> Operational Friction -> Financial Impact). "
        "Map technical deficits to modern Tier-1 Retail ERP capabilities. "
        "Use an aggregate of functionality from platforms like Oracle, SAP, and Microsoft Dynamics as your baseline, "
        "but strictly use generic terminology (e.g., 'Unified Inventory Management', 'Advanced Merchandising System', "
        "'Dynamic Price Management'). Do not mention specific vendor or platform names in the output."
    )
    
    chat = client.chats.create(
        model='gemini-2.5-flash',
        config=types.GenerateContentConfig(system_instruction=system_instruction, temperature=0.2)
    )
    response = chat.send_message(f"Generate executive briefing from this context:\n{raw_data}")
    
    base_name = prospect_data["dba"].replace(' ', '_') or "Prospect"
    pdf_filename = f"{base_name}_Pre_Discovery_Brief.pdf"
    PDFReportGenerator.generate_pdf(response.text, prospect_data["dba"], pdf_filename)
    return pdf_filename

# ==============================================================================
# STREAMLIT UI
# ==============================================================================
st.set_page_config(page_title="Pre-Discovery Studio", layout="wide")
st.title("Retail ERP Pre-Discovery Studio")

cache = load_cache()
last_entry = cache.get("last_entry")

scenario_options = {}
if last_entry and isinstance(last_entry, dict):
    scenario_options[f"★ Last Session Entry ({last_entry.get('dba', 'Custom Brand')})"] = last_entry
scenario_options.update(SCENARIOS)

with st.sidebar:
    st.header("1. API Credentials")
    gemini_key = st.text_input("Gemini Key:", type="password")
    builtwith_key = st.text_input("BuiltWith Key:", type="password")
    bypass_cache = st.checkbox("Bypass Cache", value=False)

st.header("2. Target Prospect Context")
selected_scenario = st.selectbox("Preset / Last:", list(scenario_options.keys()))
init_scen = scenario_options[selected_scenario]

col1, col2 = st.columns(2)
with col1:
    domain_input = st.text_input("Domain:", value=init_scen.get("domain", ""))
    dba_input = st.text_input("DBA Brand:", value=init_scen.get("dba", ""))
    careers_input = st.text_input("Careers URL:", value=init_scen.get("careers_url", ""))
with col2:
    revenue_input = st.text_input("Annual Revenue:", value=init_scen.get("revenue", ""))
    headcount_input = st.text_input("Headcount:", value=init_scen.get("headcount", ""))

bdr_notes_input = st.text_area("BDR Notes:", value=init_scen.get("bdr_notes", ""), height=100)

if st.button("Run Pre-Discovery Pipeline", type="primary"):
    if not gemini_key:
        st.error("Error: Gemini API key is required.")
    else:
        prospect_data = {
            "domain": domain_input, "dba": dba_input,
            "revenue": revenue_input, "headcount": headcount_input,
            "careers_url": careers_input, "bdr_notes": bdr_notes_input
        }
        
        c_data = load_cache()
        c_data["last_entry"] = prospect_data
        save_cache(c_data)
        
        with st.spinner("Executing Pipeline & Synthesizing AI Briefing..."):
            try:
                pdf_path = asyncio.run(execute_orchestrator(prospect_data, bypass_cache, gemini_key, builtwith_key))
                
                with open(pdf_path, "rb") as pdf_file:
                    st.success("Pipeline Completed Successfully!")
                    st.download_button(
                        label="Download Executive PDF Briefing",
                        data=pdf_file,
                        file_name=pdf_path,
                        mime="application/pdf"
                    )
            except Exception as e:
                st.error(f"Pipeline Failed: {e}")
