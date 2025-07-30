import pickle
import numpy as np
import os

EMBEDDINGS_FILE = "cve_embeddings.pkl"

def verify_embeddings_file():
    """
    Loads the embeddings .pkl file and prints statistics to verify its integrity.
    """
    print(f"--- Verifying Embeddings File: {EMBEDDINGS_FILE} ---")

    if not os.path.exists(EMBEDDINGS_FILE):
        print(f"\n[ERROR] File not found: '{EMBEDDINGS_FILE}'")
        print("Please run the generate-embeddings.py script first.")
        return

    try:
        with open(EMBEDDINGS_FILE, 'rb') as f:
            embeddings_data = pickle.load(f)
    except Exception as e:
        print(f"\n[ERROR] Failed to load or read the pickle file: {e}")
        return

    print("\n[SUCCESS] File loaded successfully.")

    print(f"\nType of loaded data: {type(embeddings_data)}")

    if not isinstance(embeddings_data, dict):
        print("[ERROR] Data is not a dictionary as expected.")
        return

    
    num_embeddings = len(embeddings_data)
    print(f"Number of CVEs with embeddings: {num_embeddings}")

    if num_embeddings == 0:
        print("[WARNING] The embeddings file is empty.")
        return

    
    print("\n--- Inspecting a sample item ---")
    
    first_cve_id = next(iter(embeddings_data))
    first_vector = embeddings_data[first_cve_id]

    print(f"Sample CVE ID: {first_cve_id}")
    print(f"  - Vector Type: {type(first_vector)}")
    
    if isinstance(first_vector, np.ndarray):
        print(f"  - Vector Shape (Dimensions): {first_vector.shape}")
        print(f"  - Vector Data Type: {first_vector.dtype}")
        print(f"  - Sample Vector Values: {first_vector[:5]}...") 
    else:
        print("[ERROR] The vector is not a NumPy array as expected.")

if __name__ == "__main__":
    verify_embeddings_file()