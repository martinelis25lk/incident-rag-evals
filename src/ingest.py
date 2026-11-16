import os
from pathlib import Path
import frontmatter
from dotenv import load_dotenv
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_postgres import PGVector

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
COLLECTION_NAME = "incident_postmortems"
DATA_DIR = Path("data/raw")


def load_and_chunk_documents(data_dir: Path):
    headers_to_split_on = [
        ("#", "title"),
        ("##", "section"),
    ]
    markdown_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on,
        strip_headers=False,
    )
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
    )

    all_chunks = []
    md_files = sorted(data_dir.glob("*.md"))

    if not md_files:
        raise FileNotFoundError(f"Nenhum arquivo .md encontrado em {data_dir.resolve()}")

    for file_path in md_files:
        post = frontmatter.load(file_path)
        base_metadata = dict(post.metadata)
        base_metadata["source_file"] = file_path.name

        # 1. Quebra estrutural por cabeçalhos Markdown
        header_splits = markdown_splitter.split_text(post.content)

        # 2. Subdivide apenas se alguma seção ultrapassar 800 caracteres
        final_splits = text_splitter.split_documents(header_splits)

        for doc in final_splits:
            doc.metadata.update(base_metadata)
            all_chunks.append(doc)

    return all_chunks


def main():
    print(f"Carregando documentos de {DATA_DIR}...")
    chunks = load_and_chunk_documents(DATA_DIR)
    print(f"Total de chunks gerados: {len(chunks)}")

    print(f"Inicializando modelo de embeddings ({EMBEDDING_MODEL})...")
    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )

    print("Conectando ao PGVector e ingerindo documentos...")
    vector_store = PGVector(
        embeddings=embeddings,
        collection_name=COLLECTION_NAME,
        connection=DATABASE_URL,
        use_jsonb=True,
        pre_delete_collection=True,  # Limpa a coleção para evitar duplicatas ao re-executar
    )

    vector_store.add_documents(chunks)
    print("Ingestao concluida com sucesso!")


if __name__ == "__main__":
    main()
