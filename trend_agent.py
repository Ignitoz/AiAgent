from langgraph.graph import StateGraph, START, END
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain_perplexity import ChatPerplexity
from langchain_tavily.tavily_search import TavilySearch
from pydantic import BaseModel
from typing import List
import re
from dotenv import load_dotenv

load_dotenv()

# ---------- Models ----------
class TrendSummary(BaseModel):
    heading: str
    summary: str
    engagement: str

class TrendSummaryList(BaseModel):
    summaries: List[TrendSummary]

class TrendState(BaseModel):
    query: str
    brand: str | None = None
    product: str | None = None
    content: str | None = None
    original: dict | None = None
    reflection: List[TrendSummary] | None = None
    final: dict | None = None

# ---------- LLM + Parser ----------
llm = ChatPerplexity(model="sonar")
parser = PydanticOutputParser(pydantic_object=TrendSummaryList)

# ---------- Prompts ----------
summ_prompt = PromptTemplate(
    template="""
You are analyzing competitor strategies in the {product} category. Your task is to extract and summarize what each major competing brand is doing across social media and marketing.

- Focus only on competitors (exclude {brand}).
- Mention brand names explicitly.
- One paragraph per brand with platforms, tactics, targeting.

TEXT:
{text}

{format_instructions}
""",
    input_variables=["text", "brand", "product"],
    partial_variables={"format_instructions": parser.get_format_instructions()}
)

reflect_prompt = PromptTemplate(
    template="""
Improve the following summary for clarity, conciseness, and impact. Output only the improved version.

Original Summary:
{summary}
""",
    input_variables=["summary"]
)

# ---------- Nodes ----------
search_tool = TavilySearch()

def fetch_content(state: TrendState):
    print(f"🔍 Searching for competitors of {state.brand} in {state.product}")
    query = f"What are {state.brand}'s competitors doing in the {state.product} category on social platforms?"
    results = search_tool.run(query)
    contents = [r["content"] for r in results if "content" in r]
    merged = "\n\n".join(contents[:2])  # trim to 2 chunks for speed
    return {"content": merged}

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
        for item in parsed.summaries:
            if not item.engagement.strip():
                item.engagement = "Not specified"
        return {"original": parsed.model_dump()}
    except Exception as e:
        print(f"❌ Parsing failed: {e}")
        return {"original": {"summaries": [{
            "heading": "Fallback",
            "summary": output.content.strip(),
            "engagement": "Not specified"
        }]}}

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

def finalize(state: TrendState):
    print("✅ Finalizing...")
    return {"final": {"summaries": state.reflection}}

# ---------- Graph ----------
graph = StateGraph(TrendState)
graph.add_node("fetch", fetch_content)
graph.add_node("summarize", summarize)
graph.add_node("reflect", reflect)
graph.add_node("finalize", finalize)

graph.add_edge(START, "fetch")
graph.add_edge("fetch", "summarize")
graph.add_edge("summarize", "reflect")
graph.add_edge("reflect", "finalize")
graph.add_edge("finalize", END)

agent = graph.compile()

# ---------- Run ----------
def run_trend_agent(query: str, brand: str, product: str):
    result = agent.invoke({"query": query, "brand": brand, "product": product})
    return result["final"]

if __name__ == "__main__":
    topic = "What are Dior’s competitors doing in the perfume space?"
    brand = "Dior"
    product = "perfume"

    trend = run_trend_agent(topic)
    response = [{"Heading": item["heading"], "Summary": item["summary"]} for item in trend["summaries"]]
    print(response)
