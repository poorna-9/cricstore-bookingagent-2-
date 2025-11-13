import os,json,logging
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser 
from ai.models import Queryrecordground

logger=logging.getLogger(__name__)
prompt_template = """
You are an assistant that converts user search queries for CricStore *grounds* into structured filters.

Example Inputs:
- "grounds with lights in Hyderabad"
- "available grounds tomorrow near Chennai"
- "turf grounds in Bangalore"

Expected JSON format:
{
  "index": "grounds",
  "filters": {
    "groundname": "",
    "available_date": "",
    "location": "",
    "sporttype": "",
    "address": "",
    "price": ""
  },
  "query_text": ""
}

User query: {query}
Return only valid JSON.
"""
prompt = PromptTemplate.from_template(prompt_template)

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, openai_api_key=os.getenv("OPENAI_API_KEY"))
parser = JsonOutputParser()

chain = prompt | llm | parser

def interpret_ground_query(user_query: str):
    try:
        result = chain.invoke({"query": user_query})
        parsed = dict(result) if isinstance(result, dict) else json.loads(result)
        parsed["index"] = "grounds"

        f = parsed.get("filters", {})
        parsed["filters"] = {
            "price": f.get("price"),
            "sporttype": f.get("sporttype"),
            "name": f.get("groundname"),
            "location": f.get("location"),
            "available_date": f.get("available_date"),
            "address": f.get("address"),
        }
        parsed["query_text"] = parsed.get("query_text") or user_query
        Queryrecordground.objects.create(userquery=user_query, gptresponse=parsed)
        return parsed
    except Exception as e:
        logging.exception("Ground query interpretation failed: %s", e)
        return {"index": "grounds", "filters": {}, "query_text": user_query}
