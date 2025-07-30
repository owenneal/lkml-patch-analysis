import chromadb
import pickle
import pandas as pd
import argparse
import os

EMBEDDINGS_FILE = "cve_embeddings.pkl"
COMMIT_REPORT_CSV = "final_cve_analysis_report_20250722_cleaned.csv"
CHROMA_DB_PATH = "chroma_db"


def load_source_data(embeddings_path, csv_path):
    """Loads embeddings and metadata from the correct files"""
    print(f"Loading embeddings from {embeddings_path}")
    if not os.path.exists(embeddings_path):
        print(f"Error: Embeddings file not found at '{embeddings_path}'")
        return None, None

    with open(embeddings_path, "rb") as f:
        embeddings_dict = pickle.load(f)
    print(f"Loaded {len(embeddings_dict)} embeddings")

    print(f"Loading metadata from {csv_path}")
    if not os.path.exists(csv_path):
        print(f"Error: CSV file not found at '{csv_path}'")
        return None, None

    metadata_df = pd.read_csv(csv_path).set_index('CVE_ID')
    return embeddings_dict, metadata_df


def prepare_chroma_data(chunk_list, metadata_df):
    """Formats the loaded data into lists for ChromaDB"""
    ids =[]
    embeddings = []
    metadatas = []
    documents = []

    for chunk in chunk_list:
        cve_id = chunk['cve_id']
        ids.append(chunk['chunk_id'])
        embeddings.append(chunk['vector'].tolist())
        documents.append(chunk['document'])
        metadata = {}
        if cve_id in metadata_df.index:
            metadata = {
                "cve_id": cve_id,
                "category": metadata_df.loc[cve_id, 'Vulnerability_Category'],
                "commit_url": metadata_df.loc[cve_id, 'Merged_Commit_URL']
            }
        metadatas.append(metadata)
    return ids, embeddings, metadatas, documents


def query_collection(collection, embeddings_dict, query_cve_id, n_results=5):
    """Queries the collection to find similar CVES"""
    print(f"\n--- Running a test query for {query_cve_id} ---")

    if query_cve_id not in embeddings_dict:
        print(f"Error: CVE ID '{query_cve_id}' not found in embeddings")
        return
    
    results = collection.query(
        query_embeddings=[embeddings_dict[query_cve_id].tolist()],
        n_results=n_results
    )

    print("Most similar CVEs:")
    for i, cve_id in enumerate(results['ids'][0]):
        distance = results['distances'][0][i]
        metadata = results['metadatas'][0][i]
        print(f"{i+1}. {cve_id} (Distance: {distance}), Category: {metadata.get('category', 'N/A')}, Commit URL: {metadata.get('commit_url', 'N/A')}")


def main():
    parser = argparse.ArgumentParser(description="Load embeddings and metadata into ChromaDB")
    parser.add_argument("--query", type=str, help="CVE ID to query for similar CVEs", default=None)
    args = parser.parse_args()

    chunk_list, metadata_df = load_source_data(EMBEDDINGS_FILE, COMMIT_REPORT_CSV)
    if not chunk_list or metadata_df is None:
        return
    
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    collection_name = "cve_patch_threads"
    collection = client.get_or_create_collection(name=collection_name)
    print(f"ChromaDB collection '{collection_name}' is ready.")

    ids, embeddings, metadatas, documents = prepare_chroma_data(chunk_list, metadata_df)

    print(f"Adding/updating {len(ids)} embeddings in ChromaDB")
    if ids:
        collection.upsert(ids=ids, embeddings=embeddings, metadatas=metadatas, documents=documents)
    print("Done loading data.")

    if args.query:
        query_collection(collection, chunk_list, args.query)

if __name__ == "__main__":
    main()
