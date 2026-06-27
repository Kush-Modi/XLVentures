import os
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

class MatchRecommendation(BaseModel):
    job_id: str = Field(description="UUID of the best matching job")
    job_title: str = Field(description="Job title")
    client_name: str = Field(description="Client company name")
    client_id: str = Field(description="UUID of the client")
    confidence: float = Field(description="Match confidence score between 0.0 and 1.0")
    reasoning: str = Field(description="Detailed evaluation including Strengths, Evidence from placements history, Gaps, and a Pitch Angle")

# LLM connection client
llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0.2,
)
