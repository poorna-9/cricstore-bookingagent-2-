import json
import logging
from typing import Optional, List, Literal

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import PydanticOutputParser
from django.conf import settings
from ai.models import Queryrecordground

logger = logging.getLogger(__name__)

# =========================================================
# ===================== SCHEMAS ===========================
# =========================================================

class routedecison(BaseModel):
    route: Literal["missing_fields", "full_parse"]
    confidence: float = 1.0


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
    nearme: Optional[bool] = False
    radius_km: Optional[int] = None


class NormalBookingSchema(BaseModel):
    booking_type: Literal["normal_booking"]
    intent: Literal["show", "book", "cancel", "unknown", ""]
    query_text: str
    filters: NormalBookingFilters


class AllowedShifts(BaseModel):
    start_day: List[str] = Field(default_factory=list)
    middle_days: List[str] = Field(default_factory=list)
    end_day: List[str] = Field(default_factory=list)
    constraint_type: str = ""


class TournamentBookingfilters(BaseModel):
    sporttype: str = ""
    ground_or_turf: str = ""
    ground_or_turf_name: str = ""
    city: str = ""
    area: str = ""
    address: str = ""
    start: str = ""
    end: str = ""
    total_days: str = ""
    shifts: AllowedShifts = Field(default_factory=AllowedShifts)
    budget: str = ""
    total_matches: str = ""
    overs_per_match: str = ""
    price_semantic: str = ""
    rating_min: str = ""
    rating_semantic: str = ""
    constraint_type: str = ""
    nearme: Optional[bool] = False
    radius_km: Optional[int] = None


class TournamentBookingSchema(BaseModel):
    booking_type: Literal["tournament_booking"]
    intent: Literal["show", "book", "cancel", "unknown", ""]
    query_text: str
    filters: TournamentBookingfilters


# =========================================================
# ===================== PARSERS ===========================
# =========================================================

normal_parser = PydanticOutputParser(pydantic_object=NormalBookingSchema)
tournament_parser = PydanticOutputParser(pydantic_object=TournamentBookingSchema)
route_parser = PydanticOutputParser(pydantic_object=routedecison)

# =========================================================
# ===================== PROMPTS ===========================
# =========================================================

normal_prompt = ChatPromptTemplate.from_messages([
    ("system", """
You are a STRICT JSON generator for a NORMAL sports ground booking system.
Output ONLY valid JSON. No explanations.
{format_instructions}
"""),
    ("human", "{query}")
]).partial(format_instructions=normal_parser.get_format_instructions())


missing_prompt = ChatPromptTemplate.from_messages([
    ("system", """
Fill ONLY missing fields.
Do NOT guess.
{format_instructions}
"""),
    ("human", "{query}")
]).partial(format_instructions=normal_parser.get_format_instructions())


tournament_prompt = ChatPromptTemplate.from_messages([
    ("system", """
You are a STRICT JSON generator for TOURNAMENT bookings.
Output ONLY valid JSON.
{format_instructions}
"""),
    ("human", "{query}")
]).partial(format_instructions=tournament_parser.get_format_instructions())


tournament_missing_prompt = ChatPromptTemplate.from_messages([
    ("system", """
Fill ONLY missing tournament fields.
Do NOT guess.
{format_instructions}
"""),
    ("human", "{query}")
]).partial(format_instructions=tournament_parser.get_format_instructions())


route_prompt = ChatPromptTemplate.from_messages([
    ("system", """
Decide routing.
Output STRICT JSON.
{format_instructions}
"""),
    ("human", """
Missing fields: {required_fields}
User reply: {query}
""")
]).partial(format_instructions=route_parser.get_format_instructions())

# =========================================================
# ===================== LLM FACTORY =======================
# =========================================================

def get_llm(temperature=0.1):
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set")
    return ChatOpenAI(
        model="gpt-4o-mini",
        temperature=temperature,
        openai_api_key=settings.OPENAI_API_KEY,
    )


def get_normal_chain():
    return normal_prompt | get_llm(0.1) | normal_parser


def get_missing_chain():
    return missing_prompt | get_llm(0.1) | normal_parser


def get_tournament_chain():
    return tournament_prompt | get_llm(0.1) | tournament_parser


def get_tournament_missing_chain():
    return tournament_missing_prompt | get_llm(0.1) | tournament_parser


def get_route_chain():
    return route_prompt | get_llm(0) | route_parser

# =========================================================
# ===================== MAIN LOGIC ========================
# =========================================================

def interpretgroundquery(user_query, booking_type, required_fields):
    try:
        route = "full_parse"

        if required_fields:
            route_decision = get_route_chain().invoke({
                "required_fields": ", ".join(required_fields),
                "query": user_query
            })
            if route_decision.confidence >= 0.7:
                route = route_decision.route

        if booking_type == "normal_booking":
            if route == "missing_fields":
                output = get_missing_chain().invoke({
                    "required_fields": ", ".join(required_fields),
                    "query": user_query
                })
            else:
                output = get_normal_chain().invoke({"query": user_query})

            data = output.dict()
            data["intent"] = (data.get("intent") or "unknown").lower()
            data["booking_type"] = "normal_booking"

            if "near me" in user_query.lower():
                data["filters"]["nearme"] = True

            Queryrecordground.objects.create(
                userquery=user_query,
                gptresponse=json.dumps(data)
            )
            return data

        if booking_type == "tournament_booking":
            if route == "missing_fields":
                output = get_tournament_missing_chain().invoke({
                    "required_fields": ", ".join(required_fields),
                    "query": user_query
                })
            else:
                output = get_tournament_chain().invoke({"query": user_query})

            data = output.dict()
            data["intent"] = (data.get("intent") or "unknown").lower()
            data["booking_type"] = "tournament_booking"

            Queryrecordground.objects.create(
                userquery=user_query,
                gptresponse=json.dumps(data)
            )
            return data

        return {"intent": "show", "query_text": user_query}

    except Exception as e:
        logger.error(f"LangChain error: {e}")
        return {"intent": "show", "query_text": user_query}
