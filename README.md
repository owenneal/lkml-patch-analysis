# LKML Patch Analysis Toolkit

This toolkit analyzes Linux Kernel Mailing List (LKML) patch emails, detects merge indicators, maps patch discussions to git commits, and generates reports for research or engineering review.

---

## Table of Contents

- [Requirements](#requirements)
- [Setup](#setup)
- [Project Structure](#project-structure)
- [Usage](#usage)
- [Script and File Descriptions](#script-and-file-descriptions)
- [Reports](#reports)
- [Troubleshooting](#troubleshooting)

---

## Requirements

- Python 3.8+
- SQLite3
- Git (for commit log extraction)
- [pip](https://pip.pypa.io/en/stable/)
- will probably need neo4j desktop as well if trying to export to neo4j but
we weren't really focusing on that currently

### Python Libraries

Install required libraries with:

```sh
pip install beautifulsoup4 networkx requests tqdm dateutils pyvis
```
or other way if not using pip

---

## Setup

1. **Clone this repository** and enter the directory:

    ```sh
    git clone <repo-url>
    cd lkml-patch-analysis
    ```

2. **Ensure the following files are present:**
    - `lkml-data-2024.db` (LKML emails database)
    - `maintainers.db` (Linux maintainers database)
    - (Optional) `patch_report.txt`, `merge_indicators_report.txt`, etc.

3. **Install dependencies** (see above).

---

## Project Structure

```
lkml-patch-analysis/
│
├── lkml-data-2024.db           # SQLite database of LKML emails
├── maintainers.db              # SQLite database of maintainers
├── patch_report.txt            # Example output report
├── merge_indicators_report.txt # Example merge indicator report
├── unmatched_patch_commits.txt # Commits not matched to patches
├── src/
│   ├── main.py                 # Main entry point
│   ├── data_access.py          # Database access functions
│   ├── email_parser.py         # Email parsing and signal extraction
│   ├── graph_builder.py        # Builds patch/thread graphs
│   ├── case_study.py           # Merge indicator analysis and reporting
│   ├── git_pull_case_study.py  # Git pull/commit mapping analysis
│   └── maintainer_scraper.py   # Maintainer DB builder (optional)
│
├── lib/                        # JS/CSS libraries for HTML reports
│
└── README                      # This file
```

---

## Usage

### 1. **Basic Patch Analysis**

Run the main analysis script:

```sh
python src/main.py --case-study --text-report --sample-size 1000
```

- `--case-study`: Run merge indicator analysis
- `--text-report`: Output a text report (`merge_indicators_report.txt`)
- `--sample-size N`: Number of emails to process (default: 1000)

### 2. **Generate Maintainer Database (if needed)**

```sh
python src/maintainer_scraper.py
```

### 3. **Analyze Git Pull Requests and Patch Mapping**

```sh
python src/git_pull_case_study.py
```

This script attempts to map `[GIT PULL]` emails to patch discussions and git commits.

### 4. **Export to Neo4j (optional)**

If you want to visualize graphs in Neo4j:

```sh
python src/main.py --export-neo4j --sample-size 1000
```

### 5. **Generate Patch Evolution Graphs**

To create and visualize the patch evolution and discussion graphs, use the following commands:

#### **Basic Graph Visualization (HTML, Pyvis)**

```sh
python src/main.py --sample-size 1000
```

- This will generate an interactive HTML file (e.g., `patch_evolution_graph.html`) in the project directory.
- You can open this file in your browser to explore the patch/thread relationships.

#### **Export Graph to Neo4j (optional)**

If you want to export the graph to a Neo4j database for advanced querying and visualization:

```sh
python src/main.py --export-neo4j --sample-size 1000
```

- Make sure Neo4j Desktop or Server is running and the connection details in the script match your setup.

#### **Batch Processing for Large Datasets**

For large-scale graph creation and export (in batches):

```sh
python src/main.py --full-scale --batch-size 5000 --export-neo4j
```

- This will process emails in batches and export each batch to Neo4j.

---

**Note:**  
- The HTML graph files are saved as `patch_evolution_graph.html` (and similar names) in the `lkml-patch-analysis/` directory.
- You do **not** need to run `case_study.py` directly; all relevant analysis is now handled via `main.py` and `git_pull_case_study.py`.

## Script and File Descriptions

- **src/main.py**  
  Purpose:
    The main entry point for the toolkit. Handles command-line arguments, orchestrates the workflow (database analysis, graph building, merge indicator case study, Neo4j export, etc.), and produces reports.

  Key Features:
    - Parses command-line arguments for all major features.
    - Loads emails from the database and builds patch/thread graphs.
    - Runs merge indicator analysis and generates reports. (not really useful now that using the gitpull emails and linux github commit logs for real proof of merge instead of just heuristics)
    - Optionally exports graphs to Neo4j for visualization.

- **src/data_access.py**  
  IMPORTANT: might need to change the global variable for the DATABASE_PATH at the top of the file if necessary

  Purpose:
    Provides all database access functions for reading emails, threads, and git pull requests from the SQLite database.

  Key Features:
    - Fetches patch emails, git pull emails, and thread data.
    - Provides database statistics and coverage analysis.
    - Contains utility functions for exploring and analyzing the database schema and contents.


- **src/email_parser.py**  
  Purpose:
    Parses raw email content (HTML or plain text) and extracts structured information such as metadata, patch details, merge indicators, and maintainer signals.

  Key Features:
    - Parses email subject, author, date, and body.
    - Extracts patch version, series info, and normalized patch signatures.
    - Detects merge indicators (e.g., "Acked-by", "Reviewed-by", "applied", etc.) and checks if they come from known maintainers.
    - Extracts commit hashes and patch references from git pull emails.
    - Provides helper functions for signal extraction and maintainer lookup.

- **src/graph_builder.py**  
  Purpose:
    Builds and manages the patch evolution and thread discussion graphs using NetworkX.

  Key Features:
    - Adds emails as nodes with rich metadata.
    - Connects related emails via patch evolution, thread reply, and discussion edges.
    - Groups emails into patch families and threads.
    - Provides statistics and utilities for graph analysis.

- **src/case_study.py**  (not a reason to use this anymore, first attempt at trying to determine likelihood of a patch being merged, the git pull case study .py is current working method)
  Purpose:
    Implements the merge indicator case study and reporting logic.

  Key Features:
    - Analyzes patch families for merge likelihood using detected signals.
    - Calculates merge probabilities and assigns status labels (e.g., "Very Likely Merged").
    - Generates detailed text and HTML reports with evidence snippets.
    - Provides functions for manual validation and evidence review.


- **src/git_pull_case_study.py**  (used as a standalone script to analyze git pull emails and map them to patch discussions)
  Purpose:
    Analyzes [GIT PULL] emails, extracts referenced patches/commits, and attempts to map them to patch discussions and git commit hashes.

  Key Features:
    - Extracts commit authors and subjects from pull request emails.
    - Organizes and links git pull emails to patch discussions using subject matching.
    - Generates reports mapping pull requests to patch emails and unmatched commits.
    - Optionally fetches commit info from GitHub for unmatched patches.

- **src/maintainer_scraper.py**  (no reason to use this either, was used to make a database of the
lkml official maintainers to use in tandem with the case_study.py heuristic approach)
  (Optional) Scrapes and builds the maintainers database from kernel sources.

- **lib/**  
  JavaScript and CSS libraries for HTML visualization (not needed for text reports).

---

## Reports

- **merge_indicators_report.txt**:  
  Text report of patch families, merge indicators, and evidence.

- **patch_report.txt**:  
  Mapping of git pull emails to patch discussions and commits.

- **unmatched_patch_commits.txt**:  
  Commits that could not be matched to any patch discussion.

---

## Troubleshooting

- **No output or empty reports?**  
  - Check that `lkml-data-2024.db` and `maintainers.db` are present and not empty.
  - Try increasing `--sample-size`.
  - Ensure dependencies are installed.

- **Neo4j export fails?**  
  - Make sure Neo4j is running and credentials are correct.

- **Maintainer DB missing?**  
  - Run `python src/maintainer_scraper.py` to generate it.

---

