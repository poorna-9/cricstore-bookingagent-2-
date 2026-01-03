import os
import json
import logging
from typing import Optional

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import PydanticOutputParser
from django.conf import settings
from ai.models import Queryrecordground
from typing import Optional, Literal

logger = logging.getLogger(__name__)

class NormalBookingFilters(BaseModel):
    sporttype: Optional[str] = Field(default="")
    ground_or_turf: Optional[str] = Field(default="")
    ground_or_turf_name: Optional[str] = Field(default="")
    city: Optional[str] = Field(default="")
    area: Optional[str] = Field(default="")
    address: Optional[str] = Field(default="")
    date: Optional[str] = Field(default="")
    timings: Optional[str] = Field(default="")
    am_pm: Optional[str] = Field(default="")
    shift: Optional[str] = Field(default="")
    hours: Optional[str] = Field(default="")
    price: Optional[str] = Field(default="")
    price_semantic: Optional[str] = Field(default="")
    rating_min: Optional[str] = Field(default="")
    rating_semantic: Optional[str] = Field(default="")
class NormalBookingSchema(BaseModel):
    booking_type: Literal["normal_booking"]
    intent: str
    filters: NormalBookingFilters
    query_text: str

class TournamentBookingFilters(BaseModel):
    sporttype: Optional[str] = Field(default="")
    ground_or_turf: Optional[str] = Field(default="")
    ground_or_turf_name: Optional[str] = Field(default="")
    city: Optional[str] = Field(default="")
    area: Optional[str] = Field(default="")
    address: Optional[str] = Field(default="")
    start_date: Optional[str] = Field(default="")
    end_date: Optional[str] = Field(default="")
    duration_days: Optional[str] = Field(default="")
    shift: Optional[str] = Field(default="")
    am_pm: Optional[str] = Field(default="")
    radius_km: Optional[str] = Field(default="")

class TournamentBookingSchema(BaseModel):
    booking_type: Literal["tournament"]
    intent: str
    filters: TournamentBookingFilters
    query_text: str

normal_parser = PydanticOutputParser(pydantic_object=NormalBookingSchema)

normal_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """
You are a strict JSON generator for a NORMAL sports ground booking system.

RULES:
- Output ONLY valid JSON
- booking_type MUST be "normal_booking"
- Do NOT explain
- Do NOT ask questions
- Missing values → empty string ""

INTENT:
- show, book, cancel, unknown

All extracted info MUST be inside filters.

{format_instructions}
"""
    ),
    ("human", "{query}")
]).partial(format_instructions=normal_parser.get_format_instructions())

normal_llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.2,
    openai_api_key=settings.OPENAI_API_KEY
)

normal_chain = normal_prompt | normal_llm | normal_parser


tournament_parser = PydanticOutputParser(pydantic_object=TournamentBookingSchema)

tournament_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """
You are a strict JSON generator for a TOURNAMENT ground booking system.

RULES:
- Output ONLY valid JSON
- booking_type MUST be "tournament"
- Do NOT explain
- Do NOT ask questions
- Missing values → empty string ""

Tournament bookings are MULTI-DAY.

{format_instructions}
"""
    ),
    ("human", "{query}")
]).partial(format_instructions=tournament_parser.get_format_instructions())

tournament_llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.2,
    openai_api_key=settings.OPENAI_API_KEY
)

tournament_chain = tournament_prompt | tournament_llm | tournament_parser


def interpret_normal_booking(user_query: str):
    try:
        obj = normal_chain.invoke({"query": user_query})
        data = obj.dict()
        Queryrecordground.objects.create(
            userquery=user_query,
            gptresponse=json.dumps(data)
        )
        return data
    except Exception as e:
        logger.error(f"Normal booking error: {e}")
        return {
            "booking_type": "normal_booking",
            "intent": "unknown",
            "filters": NormalBookingFilters().dict(),
            "query_text": user_query
        }

def interpret_tournament_booking(user_query: str):
    try:
        obj = tournament_chain.invoke({"query": user_query})
        data = obj.dict()
        Queryrecordground.objects.create(
            userquery=user_query,
            gptresponse=json.dumps(data)
        )
        return data
    except Exception as e:
        logger.error(f"Tournament booking error: {e}")
        return {
            "booking_type": "tournament",
            "intent": "unknown",
            "filters": TournamentBookingFilters().dict(),
            "query_text": user_query
        }

def interpretgroundquery(user_query: str, booking_type: str):
    if booking_type == "tournament":
        return interpret_tournament_booking(user_query)
    return interpret_normal_booking(user_query)
