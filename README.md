# LKML Patch Analysis Toolkit

This project provides an end-to-end pipeline to analyze Linux Kernel Mailing List (LKML) data, link CVEs to commits, and build a Retrieval-Augmented Generation (RAG) system to query vulnerability information using a local Large Language Model (LLM).


## Table of Contents

- [Requirements](#requirements)
- [Setup](#setup)
- [End-to-End Pipeline Workflow](#end-to-end-pipeline-workflow)
- [Troubleshooting](#troubleshooting)


## Requirements
- Python 3.8+
- SQLite3
- Git (for commit log extraction)

### Python Libraries
Install required libraries with:

```sh
pip install beautifulsoup4 networkx requests tqdm dateutils pyvis OpenAI pandas sentence-transformers torch chromadb
```

### Local LLM Server
This project requires a local LLM server that is compatible with the OpenAI API format. [LM Studio](https://lmstudio.ai/) is a recommended option.
- Download and install LM Studio.
- Download a model (e.g., `gemma-2-9b-it-gguf`) is the recommended model for this project.
- Start the server and ensure it is running on `http://localhost:1234/v1`.


## Setup

0. **Create a main project directory that will house two different repositories.**
    - For example:

1. **Clone this repository** and enter the directory:
    - Create a directory for this project and clone the repository.
    ```sh
    git clone <repo-url>
    cd lkml-patch-analysis
    ```

2. **Prepare Data Files:**
    - Before running the pipeline, you must place the following data files in the project's root directory.
    - `lkml-data-2024.db` (LKML emails database for 2024)
    - `gitlog_2024.txt`: A text file containing the Linux git commit log for 2024.
    - There may be a better way of getting the git log, but I had cloned the linux kernel repository and ran the following command to get the git log:
    ```sh
    git log --since="2024-01-01" --until="2024-12-31" --pretty=format:"<commit_begin>%n%H%n%an%n%ae%n%ad%n%B<commit_end>" > gitlog_2024.txt
    ```

3.  **Download CVE Data:**
    The pipeline requires a local copy of the official CVE records. Clone the `cvelistV5` repository into the same parent directory as `lkml-patch-analysis`.
    ```sh
    # From the directory containing 'lkml-patch-analysis/'
    git clone https://github.com/CVEProject/cvelistV5.git
    ```
    Your directory structure should look like this:
    ```
    your-workspace/
    ├── lkml-patch-analysis/
    └── cvelistV5/

4. **Install dependencies** (see above).

## End-to-End Pipeline Workflow

The `src/main.py` script orchestrates the entire pipeline. You can run all steps at once or execute them individually.

### Run the Full Pipeline
To run all data processing and setup steps from start to finish, execute:
```sh
python src/main.py --step all
```

### Run Individual Steps
You can also run each step manually. This is useful for debugging or re-running a specific part of the process.

**Step 1: Import CVEs & Find Patches**
Creates the `suspected_cve_patches.db` and populates it by finding LKML emails that appear to be patches for Linux kernel CVEs.
```sh
python src/main.py --step 1
```

**Step 2: Create Commit Database**
Parses `gitlog_2024.txt` to create the `commits.db` SQLite database, containing commit hashes, messages, and diffs.
```sh
python src/main.py --step 2
```

**Step 3: Link CVEs to Commits**
Matches suspected CVE patches to commits in `commits.db` and generates `cve_commit_report.csv`.
```sh
python src/main.py --step 3
```

**Step 4: Categorize CVEs with LLM**
Adds a `category` column to the database. **Requires the local LLM server to be running.**
```sh
python src/main.py --step 4
```

**Step 5: Generate Final CSV Report**
Cleans and consolidates the categorized data into a final report, `final_cve_analysis_report_YYYYMMDD.csv`.
```sh
python src/main.py --step 5
```

**Step 6: Generate Embeddings**
Creates vector embeddings for each CVE thread's full text content and saves them to `cve_embeddings.pkl`.
```sh
python src/main.py --step 6
```

**Step 7: Load Embeddings into ChromaDB**
Loads the embeddings and metadata into a local ChromaDB vector store located at `chroma_db/`.
```sh
python src/main.py --step 7
```

## Querying the RAG System

- Once the pipeline has been run successfully, you can ask questions about the CVE data.
- Currently, it looks like including a CVE ID in the query is required to get a response.
- Due to the nature of the data, the system is designed to answer questions about specific CVEs and their related patches. Maybe a better model will be able to answer more general questions or having a much larger dataset would help with that.

- So make sure to include a CVE ID in your query.
- CVE IDs can be found in the `final_cve_analysis_report_YYYYMMDD.csv` file generated in Step 5.

### Via Command Line
Use `step 8` in `main.py` with a `--query` argument.
```sh
python src/main.py --step 8 --query "Can you show me the code fix for CVE-2024-38575 a NULL Pointer Dereference issue in the Linux Kernel?"
```


# Other useful scripts not directly part of the main pipeline or RAG system

## **Generate a Report of Categorized CVEs**

After categorizing the CVEs, you can generate a clean CSV report.

```sh
python -m src.tools.generate_cve_category_csv
```

This will create a file like `cve_categories_YYYYMMDD.csv` in the `src` directory.

## **Visualize a Specific CVE Patch Thread**

To visualize the email discussion graph for a single CVE, use the `cve_patch_graph_tool.py` script.

1.  First, list all available CVEs to find one to investigate:
    ```sh
    python -m .src.tools.cve_patch_graph_tool --list-cves
    ```

2.  Then, generate the graph for a specific CVE ID:
    ```sh
    python -m src.tools.cve_patch_graph_tool CVE-2024-26687 --graph
    ```
- This will create an interactive HTML file (e.g., `patch_evolution_graph_CVE_2024_26687.html`) showing the relationships between the emails in that thread. You can open this file in a web browser to explore the patch discussion visually.


**Note:**  
- The HTML graph files are saved as `patch_evolution_graph.html` (and similar names) in the `lkml-patch-analysis/` directory.
- As the project is set up in modules for those scripts (all but main really) they are run with this as an example: python -m src.tools.cve_patch_graph_tool CVE-2024-26687 --graph
- You may see an error about `maintainers.db` not being found. This is unimportant and does not effect the main system. It was an old line of thinking that ended up not being reliable. I have left it in for now, but it can be removed if desired, the related code is in the email_parser.py and mainainer_scraper.py which is not used in the main pipeline.


## Troubleshooting

- **No output or empty reports?**  
  - Check that `lkml-data-2024.db`, CVEs, and gitlog are present and not empty.
  - Try increasing `--sample-size`.
  - Ensure dependencies are installed.

- **Neo4j export fails?**  
  - Make sure Neo4j is running and credentials are correct.
  - Did not end up being used in the main pipeline, but if you want to use it, make sure to have Neo4j installed and running. It's kind of a pain to set up, so I didn't include it in the main pipeline also it isn't really useful for the RAG system as we use the chroma vector database instead.

- **Maintainer DB missing?**  
  - Run `python -m src.tools.maintainer_scraper` to generate it.
  - This is not used in the main pipeline, but it can be useful for other analyses.


