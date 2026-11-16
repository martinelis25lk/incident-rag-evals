import json
import os
import time
from pathlib import Path
from dotenv import load_dotenv
from datasets import Dataset
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_huggingface import HuggingFaceEmbeddings
from ragas import evaluate
from ragas.metrics import Faithfulness, AnswerRelevancy, ContextPrecision
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.run_config import RunConfig

from src.retriever import HybridIncidentRetriever

load_dotenv()

LLM_MODEL = os.getenv("LLM_MODEL", "gemini-3.8-flash")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
EVAL_DATASET_PATH = Path("data/eval_dataset.json")
RESULTS_OUTPUT_PATH = Path("eval_results.json")


def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()
    return str(content)


def generate_answer(llm: ChatGoogleGenerativeAI, question: str, contexts: list[str]) -> str:
    joined_context = "\n\n---\n\n".join(contexts)
    prompt = (
        "Answer the technical question using ONLY the provided post-mortem excerpts. "
        "Be concise and accurate.\n\n"
        f"Context:\n{joined_context}\n\nQuestion: {question}"
    )
    response = llm.invoke(prompt)
    return _extract_text(response.content)


def main():
    if not EVAL_DATASET_PATH.exists():
        raise FileNotFoundError(f"Dataset nao encontrado em {EVAL_DATASET_PATH}")

    eval_samples = json.loads(EVAL_DATASET_PATH.read_text(encoding="utf-8-sig"))
    retriever = HybridIncidentRetriever()
    llm = ChatGoogleGenerativeAI(model=LLM_MODEL, temperature=0, max_retries=5)

    records = []
    print(f"Executando pipeline RAG em {len(eval_samples)} perguntas de teste...")

    for i, item in enumerate(eval_samples, start=1):
        question = item["question"]
        ground_truth = item["ground_truth"]

        docs = retriever.retrieve(query=question, top_k=4)
        contexts = [doc.page_content for doc in docs]
        answer = generate_answer(llm, question, contexts)
        print(f"  [{i}/{len(eval_samples)}] Resposta gerada.")

        records.append({
            "user_input": question,
            "response": answer,
            "retrieved_contexts": contexts,
            "reference": ground_truth,
        })
        time.sleep(1)

    dataset = Dataset.from_list(records)

    evaluator_llm = LangchainLLMWrapper(llm)
    evaluator_embeddings = LangchainEmbeddingsWrapper(
        HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    )

    metrics = [
        Faithfulness(llm=evaluator_llm),
        AnswerRelevancy(llm=evaluator_llm, embeddings=evaluator_embeddings),
        ContextPrecision(llm=evaluator_llm),
    ]

    print("Calculando metricas com Ragas...")
    run_config = RunConfig(max_workers=2, max_retries=5, timeout=120)
    result = evaluate(dataset=dataset, metrics=metrics, run_config=run_config)
    df = result.to_pandas()

    summary = {
        "faithfulness": round(float(df["faithfulness"].mean()), 4),
        "answer_relevancy": round(float(df["answer_relevancy"].mean()), 4),
        "context_precision": round(float(df["context_precision"].mean()), 4),
        "samples_count": len(records),
    }

    print("\n=== RESULTADOS RAGAS ===")
    for k, v in summary.items():
        print(f"{k}: {v}")

    RESULTS_OUTPUT_PATH.write_text(
        json.dumps({"summary": summary, "details": df.to_dict(orient="records")}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nRelatorio detalhado salvo em {RESULTS_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
