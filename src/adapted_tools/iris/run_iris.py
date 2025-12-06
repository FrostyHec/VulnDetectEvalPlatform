import os
import sys
import argparse
import pandas as pd
import subprocess
import logging

# Add src to path
# This script is in src/adapted_tools/iris/run_iris.py
# ../../../ -> src/adapted_tools/iris -> src/adapted_tools -> src -> root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from src.adapted_tools.iris.core_adapted.iris import SAPipeline
from src.adapted_tools.iris.config import IrisConfig
from src.adapted_tools.iris.utils.gen_build_info import generate_build_info

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_command(command, cwd=None):
    logger.info(f"Running command: {command}")
    result = subprocess.run(command, shell=True, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"Command failed: {result.stderr}")
        raise Exception(f"Command failed: {result.stderr}")
    return result.stdout

def main():
    parser = argparse.ArgumentParser(description="Run Iris on a project")
    parser.add_argument("--project_name", required=True, help="Name of the project (repo folder name)")
    parser.add_argument("--cve_id", required=True, help="CVE ID")
    parser.add_argument("--query", default="CWE-079", help="CWE Query to run (e.g., CWE-079)")
    parser.add_argument("--repo_path", help="Path to the repository")
    parser.add_argument("--output_dir", default="output/dataset_patch/primevul", help="Output directory")
    parser.add_argument("--codeql_home", default="tools/codeql_home/codeql", help="Path to CodeQL home")
    parser.add_argument("--skip_evaluation", action="store_true", help="Skip evaluation")
    parser.add_argument("--test_run", action="store_true", help="Run in test mode (no LLM calls)")
    parser.add_argument("--model", default="gpt-4", help="LLM model to use")
    
    args = parser.parse_args()

    project_name = args.project_name
    cve_id = args.cve_id
    query = args.query
    
    # Paths
    workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
    
    if args.repo_path:
        repo_path = os.path.abspath(args.repo_path)
    else:
        repo_path = os.path.join(workspace_root, "dataset/dataset_patch/repos", project_name)
        
    output_dir = os.path.abspath(args.output_dir)
    codeql_home = os.path.abspath(args.codeql_home)
    codeql_bin = os.path.join(codeql_home, "codeql")
    
    # DB Path
    # We store DBs in src/adapted_tools/iris/results/dbs/<project_name>/<cve_id>
    db_path = os.path.join(workspace_root, "src/adapted_tools/iris/results/dbs", project_name, cve_id)
    
    logger.info(f"Project: {project_name}")
    logger.info(f"CVE: {cve_id}")
    logger.info(f"Repo Path: {repo_path}")
    logger.info(f"Output Dir: {output_dir}")
    logger.info(f"DB Path: {db_path}")

    # 1. Generate Build Info
    logger.info("Generating build info...")
    try:
        build_info = generate_build_info(repo_path)
        build_cmd = build_info.get("build_command", "") if isinstance(build_info, dict) else str(build_info)
        logger.info(f"Build info: {build_info}")
    except Exception as e:
        logger.warning(f"Failed to generate build info: {e}. Proceeding without explicit build command.")
        build_cmd = ""

    # 2. Create CodeQL Database if not exists or incomplete
    db_java_path = os.path.join(db_path, "db-java")
    if os.path.exists(db_path) and not os.path.exists(db_java_path):
        logger.warning(f"DB path exists but db-java missing, removing: {db_path}")
        import shutil
        shutil.rmtree(db_path)

    if not os.path.exists(db_path):
        logger.info("Creating CodeQL database...")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        cmd_parts = [
            codeql_bin,
            "database",
            "create",
            db_path,
            "--language=java",
            f"--source-root={repo_path}",
            "--overwrite",
        ]
        if build_cmd:
            # Quote the build command so CodeQL parses it as a single argument
            cmd_parts.append(f"--command=\"{build_cmd}\"")

        try:
            run_command(" ".join(cmd_parts))
        except Exception as e:
            logger.error(f"Failed to create CodeQL DB: {e}")
            return

    # 3. Prepare Fix Info
    # Pass empty dataframe for now
    project_fixed_methods = pd.DataFrame(columns=["file", "project_slug", "cve_id"])

    # 4. Run Iris
    logger.info("Running Iris...")
    try:
        pipeline = SAPipeline(
            project_name=project_name,
            query=query,
            project_source_dir=repo_path,
            output_dir=output_dir,
            codeql_db_path=db_path,
            project_fixed_methods=project_fixed_methods,
            cve_id=cve_id,
            cve_fixing_commits=[], 
            llm=args.model, 
            no_logger=False,
            skip_evaluation=args.skip_evaluation,
            test_run=args.test_run
        )
        
        pipeline.run()
        
    except Exception as e:
        logger.error(f"Iris execution failed: {e}")
        import traceback
        traceback.print_exc()

    # Add Maven to PATH
    maven_home = os.path.join(workspace_root, "tools/maven/apache-maven-3.9.6")
    maven_bin = os.path.join(maven_home, "bin")
    if os.path.exists(maven_bin):
        os.environ["PATH"] = maven_bin + os.pathsep + os.environ["PATH"]
        logger.info(f"Added Maven to PATH: {maven_bin}")

if __name__ == "__main__":
    main()
