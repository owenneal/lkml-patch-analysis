import argparse
import textwrap
import chromadb
import re
from openai import OpenAI
from sentence_transformers import SentenceTransformer


# Constants for file paths and model names
CHROMA_DB_PATH = "chroma_db"
COLLECTION_NAME = "cve_patch_threads"
EMBEDDING_MODEL = 'all-MiniLM-L6-v2'
LLM_MODEL_NAME = "gemma-4b-it" # Adjust as needed



def retrieve_relevant_docs(collection, embedding_model, query_text: str, n_results=3, cve_id_filter=None) -> list:
    """Embeds the query and retrieves the most relevant document IDs from ChromaDB."""
    query_embedding = embedding_model.encode(query_text).tolist()

    where_filter = None
    if cve_id_filter:
        where_filter = {"cve_id": {"$eq": cve_id_filter}}
        print(f"Filtering results for CVE ID: {cve_id_filter}")


    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        where=where_filter,
        include=["metadatas", "documents", "distances"]
    )
    return results


def generate_llm_response(llm_client, query_text: str, retrieved_results: dict) -> str:
    """Builds a prompt with context and gets a response from the LLM."""
    context = ""
    for i, chunk_id in enumerate(retrieved_results['ids'][0]):
        metadata = retrieved_results['metadatas'][0][i]
        document_content = retrieved_results['documents'][0][i]

        context += f"--- CONTEXT FROM {metadata.get('cve_id', 'N/A')} (Chunk ID: {chunk_id}) ---\n"
        context += f"Vulnerability Category: {metadata.get('category', 'N/A')}\n"
        context += f"Commit URL: {metadata.get('commit_url', 'N/A')}\n\n"
        context += "--- EMAIL AND PATCH DETAILS ---\n"
        context += f"{document_content}\n\n"

    prompt = f"""
        You are a helpful security analyst assistant who can write code.
        Answer the user's question based *only* on the provided context, which includes email discussions and code patches.
        If the user asks for a code example, use the code from the 'EMAIL THREAD AND PATCH DETAILS' section to create a clear and concise example of the fix.
        If the context does not contain enough information to answer the question, say so.
        
        CONTEXT:
        {context}
        USER'S QUESTION:
        {query_text}
        
        ANSWER:
    """
    try:
        completion = llm_client.chat.completions.create(
            model=LLM_MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"Error communicating with LLM: {e}"
    

def main():
    parser = argparse.ArgumentParser(description="Query the CVE RAG system from the command line.")
    parser.add_argument("query", type=str, help="The question you want to ask the RAG system.")
    args = parser.parse_args()

    print("Setting up the RAG system...")
    llm_client = OpenAI(base_url="http://localhost:1234/v1", api_key="not-needed") #no API key needed for local deployment
    embedding_model = SentenceTransformer(EMBEDDING_MODEL)
    chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

    try:
        collection = chroma_client.get_collection(name=COLLECTION_NAME)
    except ValueError:
        print(f"Collection '{COLLECTION_NAME}' not found. Please ensure the ChromaDB is set up correctly.")
        return
    
    print("RAG system setup complete. Processing your query...")

    cve_id_match = re.search(r'(CVE-\d{4}-\d{4,7})', args.query, re.IGNORECASE)
    cve_filter = cve_id_match.group(0).upper() if cve_id_match else None


    retrieved_results = retrieve_relevant_docs(collection, embedding_model, args.query, cve_id_filter=cve_filter)
    llm_response = generate_llm_response(llm_client, args.query, retrieved_results)
    print("LLM Response:")
    print(llm_response)

    print("\n" + "="*80)
    print(f"Question: {args.query}")
    print("="*80)

    print("\n### Retrieved Document Chunks:")
    for i, doc_id in enumerate(retrieved_results['ids'][0]):
        dist = retrieved_results['distances'][0][i]
        metadata = retrieved_results['metadatas'][0][i]
        cosine_similarity = 1 - (dist**2 / 2)
        print(f"- Chunk: {doc_id} (From: {metadata.get('cve_id', 'N/A')}) (Cosine Similarity: {cosine_similarity:.2f})")

    print("\n### Generated Answer:")
    print(textwrap.fill(llm_response, width=100))
    print("\n" + "="*80)


if __name__ == "__main__":
    main()