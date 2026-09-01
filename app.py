import streamlit as st
import os
import json
import time
import re
import html
import requests
from bs4 import BeautifulSoup

from google import genai
from google.genai import types
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, HRFlowable
from reportlab.lib import colors

# Original scenario definitions[cite: 1]
SCENARIOS = {
    "New Prospect / Blank Canvas": {
        "domain": "", "dba": "", "revenue": "", 
        "headcount": "", "careers_url": "", "bdr_notes": ""
    },
    "Scenario 1: Target Regional Assortment & Allocation Misalignment (Inventory)": {
        "domain": "https://target.com",
        "dba": "Target",
        "revenue": "20000000000", # Adjusted to raw number to demonstrate auto-formatting
        "headcount": "14500",
        "careers_url": "https://corporate.target.com/careers",
        "bdr_notes": "Director of Merchandising mentioned regional store clusters are too broad. Southern stores receive heavy winter apparel allocations meant for Northern stores, causing $1.2M in inter-store transfer freight and severe localized stockouts."
    }
}

# -----------------------------------------------------------------------------
# CORE PIPELINE CLASSES (Unchanged from source)
# -----------------------------------------------------------------------------
def scrape_job_postings_sync(careers_url: str) -> list:
    """Synchronous web scraping to ensure robust compatibility on cloud runtimes[cite: 1]."""
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
    except Exception as e:
        return [{"info": f"Scraper execution note: {e}"}]

class PreDiscoveryPipeline:
    def __init__(self, builtwith_key: str):
        self.builtwith_key = builtwith_key

    def fetch_tech_stack(self, domain: str, bypass_cache: bool = False) -> dict:
        """Retrieves prospect technology stack via BuiltWith API[cite: 1]."""
        if not self.builtwith_key:
            return {"info": "BuiltWith API key omitted. Skipping tech lookup."}
        try:
            url = f"https://api.builtwith.com/v23/api.json?KEY={self.builtwith_key}&LOOKUP={domain}"
            response = requests.get(url, timeout=10)
            res_data = response.json() if response.status_code == 200 else {"error": f"HTTP {response.status_code}"}
            return res_data
        except Exception as e:
            return {"error": str(e)}

    def run_pipeline(self, prospect_data: dict, bypass_cache: bool = False) -> str:
        """Aggregates all quantitative signals and contextual CRM data into a structured payload[cite: 1]."""
        domain = prospect_data["domain"]
        dba = prospect_data["dba"]
        
        jobs = []
        if prospect_data["careers_url"]:
            jobs = scrape_job_postings_sync(prospect_data["careers_url"])

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
                "job_board_signals": jobs
            }
        }
        return json.dumps(payload, indent=2)

class PDFReportGenerator:
    @staticmethod
    def _format_markdown_inline(text: str) -> str:
        """Sanitizes strings and applies basic markdown rendering for PDF conversion[cite: 1]."""
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
        return text

    @staticmethod
    def generate_pdf(briefing_text: str, prospect_name: str, output_filename: str) -> str:
        """Translates markdown text from LLM output into a formatted ReportLab PDF[cite: 1]."""
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

def execute_orchestrator(prospect_data, bypass_cache, api_key, builtwith_key):
    """Executes the core pipeline, integrating web scraping, LLM analysis, and PDF generation synchronously[cite: 1]."""
    pipeline = PreDiscoveryPipeline(builtwith_key)
    raw_data = pipeline.run_pipeline(prospect_data, bypass_cache)
    
    client = genai.Client(api_key=api_key)
    
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
# STREAMLIT UI WITH SESSION STATE PERSISTENCE & FORMATTING
# ==============================================================================
st.set_page_config(page_title="Pre-Discovery Studio", layout="wide")
st.title("Retail ERP Pre-Discovery Studio")

# Initialize persistent session state for last entry[cite: 1]
if "last_entry" not in st.session_state:
    st.session_state.last_entry = {
        "domain": "", "dba": "", "revenue": "", 
        "headcount": "", "careers_url": "", "bdr_notes": ""
    }

# -----------------------------------------------------------------------------
# Input Formatting Callbacks
# -----------------------------------------------------------------------------
def process_revenue():
    """
    Extracts raw string from the UI state, strips symbols, calculates the raw numeric
    value to prevent type mismatches in backend processing, and pushes the formatted 
    string ($ + commas) back to the UI.
    """
    raw_val = str(st.session_state.get('revenue_display', ''))
    # Isolate digits and decimal point
    cleaned = "".join([c for c in raw_val if c.isdigit() or c == '.'])
    
    if not cleaned:
        st.session_state['revenue_display'] = ''
        st.session_state['revenue_numeric'] = 0.0
        return
        
    try:
        # Save float for downstream calculations
        st.session_state['revenue_numeric'] = float(cleaned)
        # Re-format string for display
        if '.' in cleaned:
            int_part, dec_part = cleaned.split('.', 1)
            st.session_state['revenue_display'] = f"${int(int_part):,}.{dec_part}"
        else:
            st.session_state['revenue_display'] = f"${int(cleaned):,}"
    except ValueError:
        st.session_state['revenue_display'] = raw_val
        st.session_state['revenue_numeric'] = 0.0

def process_headcount():
    """
    Extracts raw string from the UI state, strips symbols, calculates the raw integer,
    and pushes the comma-separated string back to the UI.
    """
    raw_val = str(st.session_state.get('headcount_display', ''))
    # Isolate digits only for headcount
    cleaned = "".join([c for c in raw_val if c.isdigit()])
    
    if not cleaned:
        st.session_state['headcount_display'] = ''
        st.session_state['headcount_numeric'] = 0
        return
        
    try:
        st.session_state['headcount_numeric'] = int(cleaned)
        st.session_state['headcount_display'] = f"{int(cleaned):,}"
    except ValueError:
        st.session_state['headcount_display'] = raw_val
        st.session_state['headcount_numeric'] = 0


# -----------------------------------------------------------------------------
# UI Rendering
# -----------------------------------------------------------------------------
scenario_options = {}
if st.session_state.last_entry.get("dba"):
    scenario_options[f"★ Last Session Entry ({st.session_state.last_entry.get('dba')})"] = st.session_state.last_entry
scenario_options.update(SCENARIOS)

with st.sidebar:
    st.header("1. API Credentials")
    gemini_key = st.text_input("Gemini Key:", type="password")
    builtwith_key = st.text_input("BuiltWith Key:", type="password")
    bypass_cache = st.checkbox("Bypass Cache", value=False)

st.header("2. Target Prospect Context")
selected_scenario = st.selectbox("Preset / Last:", list(scenario_options.keys()))
init_scen = scenario_options[selected_scenario]

# State Sync: Force formatting updates when a new scenario dropdown option is selected
if "current_scenario" not in st.session_state or st.session_state.current_scenario != selected_scenario:
    st.session_state.current_scenario = selected_scenario
    # Seed the display states with raw strings from the dictionary
    st.session_state['revenue_display'] = init_scen.get("revenue", "")
    st.session_state['headcount_display'] = init_scen.get("headcount", "")
    # Programmatically trigger the formatting logic
    process_revenue()
    process_headcount()

col1, col2 = st.columns(2)

with col1:
    domain_input = st.text_input(
        "Domain:", 
        value=init_scen.get("domain", ""), 
        placeholder="https://company.com"
    )
    dba_input = st.text_input("DBA Brand:", value=init_scen.get("dba", ""))
    careers_input = st.text_input(
        "Careers URL:", 
        value=init_scen.get("careers_url", ""), 
        placeholder="https://company.com/careers"
    )

with col2:
    # Text inputs bound directly to session state keys to execute callbacks on blur/enter
    st.text_input(
        "Annual Revenue:", 
        key="revenue_display",
        on_change=process_revenue,
        placeholder="$1,000,000"
    )
    st.text_input(
        "Headcount:", 
        key="headcount_display",
        on_change=process_headcount,
        placeholder="10,000"
    )

bdr_notes_input = st.text_area("BDR Notes:", value=init_scen.get("bdr_notes", ""), height=100)

if st.button("Run Pre-Discovery Pipeline", type="primary"):
    if not gemini_key:
        st.error("Error: Gemini API key is required.")
    else:
        # Construct pipeline payload utilizing the formatted display variables for LLM context[cite: 1]
        prospect_data = {
            "domain": domain_input, 
            "dba": dba_input,
            "revenue": st.session_state.get('revenue_display', ''), 
            "headcount": st.session_state.get('headcount_display', ''),
            "careers_url": careers_input, 
            "bdr_notes": bdr_notes_input
        }
        
        # Save state persistently in session state[cite: 1]
        st.session_state.last_entry = prospect_data
        
        with st.spinner("Executing Pipeline & Synthesizing AI Briefing..."):
            try:
                # Execute synchronous orchestrator[cite: 1]
                pdf_path = execute_orchestrator(prospect_data, bypass_cache, gemini_key, builtwith_key)
                
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
