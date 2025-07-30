import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from tools.find_suspected_cve_patches import main as find_patches_main
    from tools.link_cve_to_commit import main as link_cve_main
    from tools.categorize_cve_patches import main as categorize_main
    from tools.generate_cve_commit_csv import main as generate_final_report_main
    from analysis.generate_embeddings import main as generate_embeddings_main
    from analysis.load_embeddings_to_chroma import main as load_embeddings_main
    from analysis.query_rag_system import main as query_rag_main
except ImportError as e:
    print(f"Error: Could not import a required module. Make sure you are running this script from the root 'lkml-patch-analysis' directory.")
    print(f"Import error: {e}")
    sys.exit(1)

"""
This script controls the end-to-end RAG pipeline for LKML CVE analysis.
It allows users to run specific steps or the entire pipeline in sequence.
"""


def run_step(step_name, func, argv=[]):
    """Helper function to run a step and print its status"""
    print("\n" + "="*60)
    print(f"RUNNING STEP: {step_name}")
    print(f"  (command: python {func.__module__.replace('.', '/')} {' '.join(argv)})")
    print("="*60)

    try:
        original_argv = sys.argv
        sys.argv = [f'{func.__module__}.py'] + argv
        func()
        sys.argv = original_argv
        print(f"Step {step_name} completed successfully.")
    except Exception as e:
        print(f"Error in step {step_name}: {e}")
        sys.exit(1)

def main():
        parser = argparse.ArgumentParser(
        description="End-to-end RAG pipeline for LKML CVE analysis.",
        formatter_class=argparse.RawTextHelpFormatter
        )
        parser.add_argument(
        '--step',
        choices=['all', '1', '2', '3', '4', '5', '6', '7', '8'],
        required=True,
        help="""Run a specific step of the pipeline:
        1: Import CVEs & find suspected patches
        2: Create commit database from git log
        3: Link CVEs to commits to create report
        4: Categorize CVEs using an LLM
        5: Generate final CSV report of categories
        6: Generate embeddings for CVE threads
        7: Load embeddings into ChromaDB
        8: Query the RAG system with a --query argument
        all: Run all steps in sequence (1-7)
        """
        )

        parser.add_argument(
             '--query',
             type=str,
             help="Query string for the RAG system"
        )

        args = parser.parse_args()

        steps = {
            '1': ("Import CVEs & Find Patches", find_patches_main, ['--import-cves', '--find-suspected']),
            '2': ("Create Commit Database", link_cve_main, ['--create-db']),
            '3': ("Link CVEs to Commits", link_cve_main, ['--connect-cve', '--limit', '0']),
            '4': ("Categorize CVEs", categorize_main, ['--setup']),
            '5': ("Generate Final CSV Report", generate_final_report_main, []),
            '6': ("Generate Embeddings", generate_embeddings_main, []),
            '7': ("Load to ChromaDB", load_embeddings_main, []),
            '8': ("Query RAG System", query_rag_main, []) # the query will be passed dynamically
        }

        if args.step == 'all':
            for i in range(1, 8):
                step_name, func, argv = steps[str(i)]
                run_step(step_name, func, argv)
            print("\nAll pipeline steps completed successfully!")
        elif args.step == '8':
            if not args.query:
                print("Error: --query argument is required for step 8.")
                sys.exit(1)
            step_name, func, _ = steps['8']
            run_step(step_name, func, [args.query])
        elif args.step in steps:
            step_name, func, argv = steps[args.step]
            run_step(step_name, func, argv)

if __name__ == "__main__":
    main()
