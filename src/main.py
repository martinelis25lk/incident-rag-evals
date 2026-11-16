import os
import time
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate

from src.retriever import HybridIncidentRetriever

load_dotenv()

LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")

app = FastAPI(
    title="Incident Post-Mortem RAG API",
    description="Hybrid-search RAG microservice (BM25 + pgvector) with structured citations.",
    version="1.0.0",
)

retriever: Optional[HybridIncidentRetriever] = None


class SourceCitation(BaseModel):
    company: str = Field(description="Company affected by the incident")
    date: str = Field(description="Date of the incident (YYYY-MM-DD)")
    section: str = Field(description="Document section used as evidence")
    source_file: str = Field(description="Markdown filename")


class RAGStructuredAnswer(BaseModel):
    answer: str = Field(
        description="Technical answer strictly grounded in the retrieved post-mortem excerpts."
    )
    found_in_context: bool = Field(
        description="True if the context contains enough evidence to answer; False otherwise."
    )
    sources: list[SourceCitation] = Field(
        default_factory=list,
        description="List of sources cited to build the answer.",
    )


class AskRequest(BaseModel):
    question: str = Field(..., min_length=5, examples=["What caused the Cloudflare 502 outage?"])
    company: Optional[str] = Field(
        default=None,
        description="Optional metadata filter by company name (e.g., Cloudflare, GitLab, AWS)",
    )
    top_k: int = Field(default=4, ge=1, le=10)


class AskResponse(RAGStructuredAnswer):
    latency_ms: float
    retrieved_chunks_count: int


SYSTEM_PROMPT = """You are a senior Site Reliability Engineer (SRE) assistant analyzing production incident post-mortems.
Answer the user's question using ONLY the provided context excerpts.

Rules:
1. Never invent facts, dates, metrics, or root causes not explicitly stated in the context.
2. If the context does not contain information to answer the question, set ound_in_context to false, leave sources empty, and state clearly that no matching incident record was found in the knowledge base.
3. Always populate sources with the exact metadata of the excerpts you relied on.
4. Keep the technical explanation concise, objective, and accurate.
"""

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", "Context Excerpts:\n{context}\n\nQuestion: {question}"),
])


@app.on_event("startup")
def startup_event():
    global retriever
    retriever = HybridIncidentRetriever()


@app.get("/health")
def health_check():
    return {"status": "ok", "model": LLM_MODEL}


@app.post("/ask", response_model=AskResponse)
def ask_question(payload: AskRequest):
    if retriever is None:
        raise HTTPException(status_code=503, detail="Retriever not initialized.")

    start_time = time.perf_counter()

    docs = retriever.retrieve(
        query=payload.question,
        top_k=payload.top_k,
        company=payload.company,
    )

    if not docs:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return AskResponse(
            answer="No relevant post-mortem records were found for your query.",
            found_in_context=False,
            sources=[],
            latency_ms=latency_ms,
            retrieved_chunks_count=0,
        )

    formatted_context = "\n\n---\n\n".join(
        f"[Metadata: company={d.metadata.get('company')}, date={d.metadata.get('date')}, "
        f"section={d.metadata.get('section', 'General')}, file={d.metadata.get('source_file')}]\n"
        f"{d.page_content}"
        for d in docs
    )

    llm = ChatGoogleGenerativeAI(model=LLM_MODEL, temperature=0)
    structured_llm = llm.with_structured_output(RAGStructuredAnswer)
    chain = prompt | structured_llm

    result: RAGStructuredAnswer = chain.invoke({
        "context": formatted_context,
        "question": payload.question,
    })

    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

    return AskResponse(
        answer=result.answer,
        found_in_context=result.found_in_context,
        sources=result.sources,
        latency_ms=latency_ms,
        retrieved_chunks_count=len(docs),
    )
