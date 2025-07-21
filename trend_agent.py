# trend_agent.py

from langgraph.graph import StateGraph, START, END
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.messages import AIMessage
from langchain_perplexity import ChatPerplexity
#from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_tavily.tavily_search import TavilySearch
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import List, Dict, Union
import re
load_dotenv()
class TrendSummary(BaseModel):
    heading: str
    summary: str
    engagement: str
# ---------- State Schema ----------
class TrendState(BaseModel):
    query: str | None = None  # Raw user input
    brand: str | None = None
    product: str | None = None
    type: str | None = None
    content: str | None = None
    original: dict | None = None
    reflection: List[TrendSummary] | None = None
    final: dict | None = None

# ---------- Summary Output ----------
from pydantic import BaseModel
from typing import List



class TrendSummaryList(BaseModel):
    summaries: List[TrendSummary]

# ---------- LLM and Parser ----------
llm = ChatPerplexity(model="sonar")
parser = PydanticOutputParser(pydantic_object=TrendSummaryList)

# ---------- Prompt Templates ----------
summ_prompt = PromptTemplate(
    template="""
You are analyzing competitor strategies in the {product} category. Your task is to extract and summarize what each **major competing brand** is doing across social media and marketing channels.

Instructions:
- Focus **only on competitors** (exclude {brand}).
- Mention **brand names explicitly**.
- Group actions and strategies under each brand within one paragraph.
- Cover:
  - Platforms used (e.g., Instagram, TikTok, YouTube)
  - Tactics (e.g., influencer partnerships, AR/VR, livestreams, UGC, storytelling)
  - Regional targeting (e.g., China via Douyin, global vs. local focus)
  - Mention niche players if relevant.

Example:
[
{{
"heading": "Tom Ford",
"summary": "Tom Ford is using Instagram and TikTok to promote its perfumes through influencer collaborations and AR filters. It targets a luxury-driven audience with global reach.",
"engagement": "High influencer engagement on TikTok; innovative AR adoption on Snapchat."
}},
{{
"heading": "Byredo",
"summary": "Byredo focuses on Instagram Reels and minimalistic brand storytelling. Campaigns emphasize Scandinavian craftsmanship and appeal to niche fragrance lovers.",
"engagement": "Moderate, with rising organic shares."
}}
]
TEXT:
{text}

{format_instructions}
""",
    input_variables=["text", "brand", "product"],
    partial_variables={"format_instructions": parser.get_format_instructions()}
)
reflect_prompt = PromptTemplate(
    template="""
You are an expert editor improving strategic marketing summaries.

Given this original summary, improve it for:
- Clarity and conciseness
- Logical structure
- Impactful phrasing
- Flow and transitions between brand tactics

Avoid repetition, overly general statements, or redundant phrasing. Do not add new information.

Output only the improved version (no labels).

Original Summary:
{summary}
""",
    input_variables=["summary"]
)
#----------Preporcess-------------
def preprocess(state: TrendState):
    prompt = f"""
Extract the brand, product category, and type of product from the following user query. Return a JSON like:
{{"brand": "...", "product": "...", "type": "..."}}.

Query: "{state.query}"
"""
    output = llm.invoke([("human", prompt)])
    match = re.search(r'{.*}', output.content, re.DOTALL)
    parsed = eval(match.group(0)) if match else {}
    return {
        "query": state.query,
        "brand": parsed.get("brand"),
        "product": parsed.get("product"),
        "type": parsed.get("type")
    }

# ---------- Node: Fetch Content ----------
search_tool = TavilySearch()

def fetch_content(state: TrendState):
    print(f"🔍 Searching for: {state.brand} in {state.product}")
    queries = [
        f"What are recent social media campaigns by competitors of {state.brand} in the {state.product} space?",
        f"What influencer strategies are being used by brands competing with {state.brand} in {state.product}?",
        f"What are {state.brand}'s competitors doing in the {state.product} category on social platforms?"
    ]

    combined_results = []
    for q in queries:
        results = search_tool.run(q)
        combined_results.extend([r["content"] for r in results if "content" in r])

    unique_contents = list(set(combined_results))
    merged_content = "\n\n".join(unique_contents[:6])

    return {"content": merged_content}

# ---------- Node: Summarize ----------
def summarize(state: TrendState):
    print("✍️  Summarizing content...")

    chain = summ_prompt | llm
    output = chain.invoke({
        "text": state.content,
        "brand": state.brand,
        "product": state.product
    })



    try:
        parsed = parser.parse(output.content)
        
        # ✅ Inject default "engagement" if missing
        for item in parsed.summaries:
            if not item.engagement or item.engagement.strip() == "":
                item.engagement = "Not specified"

        return {"original": parsed.model_dump()}

    except Exception as e:
        print(f"❌ Parsing failed: {e}")
        fallback_summary = [{
            "heading": "Fallback",
            "summary": output.content.strip(),
            "engagement": "Not specified"
        }]
        return {"original": {"summaries": fallback_summary}}

# ---------- Node: Reflect ----------
def reflect(state: TrendState):
    print("🔁 Reflecting on summary...")

    improved = []
    for item in state.original["summaries"]:
        chain = reflect_prompt | llm
        output = chain.invoke({"summary": item["summary"]})
        improved.append({
            "heading": item["heading"],
            "summary": output.content.strip(),
            "engagement": item["engagement"]
        })

    return {"reflection": improved}
# ---------- Node: Finalize ----------
"""
def finalize(state: TrendState):
    print("✅ Finalizing...")
    reflected = state.reflection
    clean_summary = reflected.replace("Refined Summary:", "").strip()
    return {"final": {"heading": state.original["heading"], "summary": clean_summary}}
"""
def finalize(state: TrendState):
    print("✅ Finalizing...")
    return {"final": {"summaries": state.reflection}} 

# ---------- LangGraph Setup ----------
graph = StateGraph(TrendState)
graph.add_node("preprocess", preprocess)
  # fetch now uses brand/product/type
graph.add_node("fetch", fetch_content)
graph.add_node("summarize", summarize)
graph.add_node("reflect", reflect)
graph.add_node("finalize", finalize)
graph.add_edge(START, "preprocess")
graph.add_edge("preprocess", "fetch")
graph.add_edge(START, "fetch")
graph.add_edge("fetch", "summarize")
graph.add_edge("summarize", "reflect")
graph.add_edge("reflect", "finalize")
graph.add_edge("finalize", END)

agent = graph.compile()

# ---------- Usage ----------
def run_trend_agent(query: str):
    result = agent.invoke({"query": query})
    return result["final"]

if __name__ == "__main__":
    topic =  "What are Dior’s competitors doing in the perfume space?"
    #print(f"\n=== TREND: {topic} ===")
    trend = run_trend_agent(topic)
    response=[]
    for item in trend["summaries"]:
        response.append({"Heading":item.heading,"summary":item.summary})
        #print(f"\n📌 Heading: {item.heading}\n📝 Summary: {item.summary}")
    print(response)
    #print(f"\n📌 Heading:{trend['heading']}\n📝 Summary: {trend['summary']}")
