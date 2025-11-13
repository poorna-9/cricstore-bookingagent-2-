import os
import json
import logging
from langchain.prompts import PromptTemplate
from langchain.chat_models import ChatOpenAI
from langchain.output_parsers import JsonOutputParser
prompttemplate = """
You are an assistant that converts user queries for *sports facility bookings* (grounds, turfs, arenas, etc.) into structured filters.
You will extract information about booking, showing, rescheduling, cancellation, or facility information
in a **strict JSON format**. 

These queries can involve different sports (e.g., cricket, football, badminton, tennis, etc.) and may refer to either "grounds" or "turfs".

------------------------------------------------------------
EXAMPLES
------------------------------------------------------------

Example 1:
User: "Book me Narayana Turf, Yousfgouda, Hyderabad for football 5 pm tonight"
Output JSON:
{{
  "intent": "book_turf",
  "ground_or_turf": "turf",
  "ground_name": "narayana turf",
  "city": "hyderabad",
  "area": "yousfgouda",
  "datetime": "<today's date> 17:00",
  "time_text": "5 pm tonight",
  "timings": [],
  "sporttype": "football",
  "radius_km": null,
  "rating_min": null,
  "price": null,
  "price_semantic": "cheaper",
  "AM or PM": "PM"
}}

Example 2:
User: "Show me cricket grounds in Hyderabad within 10 km with rating above 4"
Output JSON:
{{
  "intent": "show_grounds",
  "ground_or_turf": "ground",
  "ground_name": null,
  "city": "hyderabad",
  "area": null,
  "datetime": null,
  "time_text": null,
  "timings": [],
  "sporttype": "cricket",
  "radius_km": 10,
  "rating_min": 4,
  "price": null,
  "price_semantic": "cheaper",
  "AM or PM": ""
}}

Example 3:
User: "Tell me about Turf Phoenix"
Output JSON:
{{
  "intent": "ground_info",
  "ground_or_turf": "turf",
  "ground_name": "turf phoenix",
  "city": null,
  "area": null,
  "datetime": null,
  "time_text": null,
  "timings": [],
  "sporttype": null,
  "radius_km": null,
  "rating_min": null,
  "price": null,
  "price_semantic": null,
  "AM or PM": ""
}}

Example 4:
User: "Is Ground X open today?"
Output JSON:
{{
  "intent": "ground_status",
  "ground_or_turf": "ground",
  "ground_name": "ground x",
  "city": null,
  "area": null,
  "datetime": "<today's date>",
  "time_text": "today",
  "timings": [],
  "sporttype": null,
  "radius_km": null,
  "rating_min": null,
  "price": null,
  "price_semantic": null,
  "AM or PM": ""
}}

Example 5:
User: "What facilities does Football Turf Y have?"
Output JSON:
{{
  "intent": "ground_facilities",
  "ground_or_turf": "turf",
  "ground_name": "football turf y",
  "city": null,
  "area": null,
  "datetime": null,
  "time_text": null,
  "timings": [],
  "sporttype": "football",
  "radius_km": null,
  "rating_min": null,
  "price": null,
  "price_semantic": null,
  "AM or PM": ""
}}

{{
  "AM or PM": "",
  "sporttype": "",
  "intent": "",
  "ground_or_turf": "",
  "ground_name": "",
  "city": "",
  "area": "",
  "datetime": "",
  "time_text": "",
  "timings": [],
  "radius_km": "",
  "rating_min": "",
  "price": "",
  "price_semantic": ""
}}
USER QUERY:
{query}
Return **only valid JSON**, no text, markdown, or explanation.
"""
prompt = PromptTemplate.from_template(prompttemplate)
llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    openai_api_key=os.getenv("OPENAI_API_KEY")
)
parser = JsonOutputParser()
chain = prompt | llm | parser
def interpretgroundquery(user_query: str):
    try:
        result = chain.invoke({"query": user_query})
        parsed = dict(result) if isinstance(result, dict) else json.loads(result)
        required_keys = [
            "AM or PM", "sporttype", "intent", "ground_or_turf", "ground_name",
            "city", "area", "datetime", "time_text", "timings",
            "radius_km", "rating_min", "price", "price_semantic"
        ]
        for key in required_keys:
            parsed.setdefault(key, None)
        if parsed.get("intent"):
            parsed["intent"] = parsed["intent"].strip().lower()
        if parsed.get("ground_or_turf"):
            parsed["ground_or_turf"] = parsed["ground_or_turf"].strip().lower()
        if parsed.get("sporttype"):
            parsed["sporttype"] = parsed["sporttype"].strip().lower()

        return parsed

    except Exception as e:
        logging.exception("Ground/turf query interpretation failed: %s", e)
        return {
            "AM or PM": "",
            "sporttype": "",
            "intent": "",
            "ground_or_turf": "",
            "ground_name": "",
            "city": "",
            "area": "",
            "datetime": "",
            "time_text": "",
            "timings": [],
            "radius_km": "",
            "rating_min": "",
            "price": "",
            "price_semantic": ""
        }

