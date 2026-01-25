import json
import logging
from typing import Any, Optional, List, Literal

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import PydanticOutputParser
from django.conf import settings
from ai.models import Queryrecordground



logger = logging.getLogger(__name__)

class routedecison(BaseModel):
    route: Literal["missing_fields", "full_parse"]
    confidence: float
class NormalBookingFilters(BaseModel):
    sporttype: str = ""
    ground_or_turf: str = ""
    ground_or_turf_name: str = ""
    city: str = ""
    area: str = ""
    address: str = ""
    date: str = ""
    timings: str = ""
    am_pm: str = ""
    shift: str = ""
    hours: str = ""
    price: str = ""
    price_semantic: str = ""
    rating_min: str = ""
    rating_semantic: str = ""
    constraint_type: str = ""  


class NormalBookingSchema(BaseModel):
    booking_type: Literal["normal_booking"]
    intent: Literal["show", "book", "cancel", "unknown"]
    query_text: str
    filters: NormalBookingFilters

normal_parser = PydanticOutputParser(
    pydantic_object=NormalBookingSchema
)

normal_prompt = ChatPromptTemplate.from_messages([
    ("system", """
You are a STRICT JSON generator for a NORMAL sports ground booking system.

CRITICAL RULES:
- Output ONLY valid JSON
- Do NOT explain
- Do NOT ask questions
- Do NOT add extra keys
- booking_type MUST be "normal_booking"
- Missing or unknown values MUST be empty strings ""

INTENT RULES:
- "show" → user wants to search / view grounds
- "book" → user wants to reserve slots
- "cancel" → user wants to cancel booking
- "unknown" → unclear intent

TIME & DATE RULES:
- Extract raw date text exactly (e.g. "tomorrow", "this saturday")
- Extract timing text exactly (e.g. "5 to 7", "evening")
- Detect shifts: morning / afternoon / evening / night
- Detect AM / PM if clearly mentioned
- Detect constraint words:
    - "from", "after", "starting" → constraint_type = "after"
    - "until", "before" → constraint_type = "before"
    - ranges → constraint_type = "between"

PRICE RULES:
- "cheap", "cheapest", "low price" → price_semantic = "cheaper"
- "expensive", "premium" → price_semantic = "expensive"

RATING RULES:
- "top rated", "best" → rating_semantic = "top_rated"
- "low rated" → rating_semantic = "low_rated"

ALL extracted values MUST go inside "filters".

{format_instructions}
"""),
    ("human", "{query}")
]).partial(
    format_instructions=normal_parser.get_format_instructions()
)

normal_llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.1,
    openai_api_key=settings.OPENAI_API_KEY
)

normal_chain = normal_prompt | normal_llm | normal_parser

missing_prompt = ChatPromptTemplate.from_messages([
    ("system", """
You are a STRICT JSON generator.

The system is asking ONLY for the following missing fields:
{required_fields}

Rules:
- Output FULL JSON schema
- Fill ONLY the missing fields listed above
- All other fields MUST be empty ""
- Do NOT infer intent
- Do NOT change booking_type
- Do NOT hallucinate values

{format_instructions}
"""),
    ("human", "{query}")
]).partial(
    format_instructions=normal_parser.get_format_instructions()
)

missing_chain = missing_prompt | normal_llm | normal_parser

from typing import Dict, Any
class TournamentPatch(BaseModel):
    updates: Dict[str, Any]
    
tournament_patch_parser = PydanticOutputParser(
    pydantic_object=TournamentPatch
)

tournament_missing_prompt = ChatPromptTemplate.from_messages([
    ("system", """
You are a STRICT JSON generator.

The system is asking ONLY for the following missing fields.
Each field is given as a DOT PATH.

Missing fields:
{required_fields}

Rules:
- Output JSON with key-value pairs
- Keys MUST exactly match the dot paths above
- Values must come ONLY from user reply
- Do NOT output full schema
- Do NOT infer or hallucinate
- Output ONLY valid JSON

{format_instructions}
"""),
    ("human", "{query}")
]).partial(
    format_instructions=tournament_patch_parser.get_format_instructions()
)
tournament_missing_chain = tournament_missing_prompt | normal_llm | tournament_patch_parser


class RelativeDates(BaseModel): 
    start: Optional[str] = Field(None, description="this | next | upcoming | None")
    end: Optional[str] = Field(None, description="this | next | upcoming | None")
    unit: Optional[str] = Field(None, description="days | weeks | None")
    duration_days: Optional[int] = None

class DateConstraints(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    relative: RelativeDates

class ScheduleWindow(BaseModel):
    start: dict = Field(default_factory=lambda: {"day_name": None})
    end: dict = Field(default_factory=lambda: {"day_name": None})

class AllowedShifts(BaseModel):
    start_day: Optional[List[str]] = None
    middle_days: Optional[List[str]] = None
    end_day: Optional[List[str]] = None

class MatchFormat(BaseModel):
    overs_per_match: Optional[int] = None

class TournamentDetails(BaseModel):
    total_matches: Optional[int] = None
    match_format: MatchFormat

class QueryScope(BaseModel):
    ground_or_turf_name: Optional[str] = None
    radius_km: Optional[int] = 10
    near_user: Optional[bool] = None

class Preferences(BaseModel):
    city: Optional[str] = None
    area: Optional[str] = None

class Budget(BaseModel):
    total_budget: Optional[int] = None

class TournamentContext(BaseModel):
    type: Literal["tournament"]
    intent: Literal["show", "find", "search", "recommend", "book", "unknown"]
    query_scope: QueryScope
    preferences: Preferences
    date_constraints: DateConstraints
    schedule_window: ScheduleWindow
    allowed_shifts: AllowedShifts
    budget: Budget
    tournament_details: TournamentDetails
    query_text: str  # raw user query

tournament_parser = PydanticOutputParser(pydantic_object=TournamentContext)

tournament_prompt = ChatPromptTemplate.from_messages([
    ("system", """
You are a STRICT JSON generator for a TOURNAMENT cricket ground booking system.

CRITICAL RULES:
- Output ONLY valid JSON
- Do NOT explain
- Do NOT add extra keys
- type MUST be "tournament"
- Missing or unknown values MUST be empty strings "" or null

INTENT RULES:
- "show", "find", "search", "recommend" → user wants to view/find grounds
- "book" → user wants to reserve slots,blocks for tournament
- "unknown" → unclear intent

QUERY SCOPE:
- Extract ground_or_turf_name if mentioned
- Extract radius_km if mentioned
- near_user is true if query indicates proximity to user

PREFERENCES:
- city and area of the user preference

DATE CONSTRAINTS:
- Keep raw text if possible, or relative values (this, next, upcoming)
- start_date, end_date, relative.start, relative.end, relative.unit, relative.duration_days

SCHEDULE WINDOW:
- Extract start.day_name and end.day_name if mentioned

ALLOWED SHIFTS:
- Extract start_day, middle_days, end_day

BUDGET:
- Extract total_budget

TOURNAMENT DETAILS:
- total_matches
- match_format.overs_per_match

ALL extracted values MUST be inside corresponding keys.

{format_instructions}
"""),
    ("human", "{query}")
]).partial(
    format_instructions=tournament_parser.get_format_instructions()
)

tournament_llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.1,
    openai_api_key=settings.OPENAI_API_KEY
   )
tournament_chain = tournament_prompt | tournament_llm | tournament_parser

route_parser = PydanticOutputParser(pydantic_object=routedecison)
route_prompt = ChatPromptTemplate.from_messages([
    ("system", """
You decide whether the user reply is:
1) answering missing required fields
2) changing intent or giving a new request

Rules:
- If reply only contains values for missing fields → missing_fields
- If reply introduces booking intent, ground name, or new action → full_parse

Output STRICT JSON only.
"""),
    ("human", """
Missing fields: {required_fields}
User reply: {query}
""")
]).partial(
    format_instructions=route_parser.get_format_instructions()
)
route_llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0
)
route_chain = route_prompt | route_llm | route_parser


def interpretgroundquery(user_query, booking_type, required_fields):
    route = "full_parse"
    if required_fields:
        route_decision = route_chain.invoke({
            "required_fields": ", ".join(required_fields),
            "query": user_query
        })
        if route_decision.confidence >= 0.7:
            route = route_decision.route
    try:
        if booking_type == "normal_booking":
            if route == "missing_fields":
                output = missing_chain.invoke({
                    "required_fields": ", ".join(required_fields),
                    "query": user_query
                })
                data = output.dict()
            else:
                output = normal_chain.invoke({"query": user_query})
                data = output.dict()
            data["booking_type"] = booking_type
            data["intent"] = (data.get("intent") or "unknown").lower()
            user_lower = user_query.lower()
            if not data["filters"]["ground_or_turf"]:
                if "ground" in user_lower:
                    data["filters"]["ground_or_turf"] = "ground"
                elif "turf" in user_lower:
                    data["filters"]["ground_or_turf"] = "turf"

            Queryrecordground.objects.create(
                userquery=user_query,
                gptresponse=json.dumps(data)
            )
            return data
        elif booking_type == "tournament":
            if route == "missing_fields":
                patch = tournament_missing_chain.invoke({
                    "required_fields": ", ".join(required_fields),
                    "query": user_query
                })
                return {
                    "type": "patch",
                    "updates": patch.updates
                }
            else:
                output = tournament_chain.invoke({"query": user_query})
                data = output.dict()
                data["type"] = "tournament"
                data["intent"] = (data.get("intent") or "unknown").lower()

                Queryrecordground.objects.create(
                    userquery=user_query,
                    gptresponse=json.dumps(data)
                )
                return data
        else:
            return {
                "intent": "unknown",
                "query_text": user_query
            }
    except Exception as e:
        logger.error(f"LangChain error: {e}")
        return {
            "intent": "unknown",
            "query_text": user_query
        }
