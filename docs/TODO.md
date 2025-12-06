# Iris Adaptation TODO List

## 1. Configuration & Infrastructure
- [ ] **Config System**: Implement `src/adapted_tools/iris/config.py` using `dataclass`.
    - [ ] Support Model Type, Key Type, API Source, API Keys (list).
    - [ ] Implement key rotation logic.
    - [ ] Create `config_template.py`.
    - [ ] Add `config.py` to `.gitignore`.
- [ ] **Directory Setup**: Create `src/adapted_tools/iris` and subdirectories (`core_adapted`, `utils`, `logs`, `results`).
- [ ] **CodeQL Setup**: Ensure CodeQL CLI is available (or create install script `scripts/install_codeql.sh` and run it).

## 2. Java Build Information Extraction
- [ ] **Build Info Script**: Implement `src/adapted_tools/iris/utils/gen_build_info.py`.
    - [ ] Detect `pom.xml` (Maven) and `build.gradle` (Gradle).
    - [ ] Heuristic for JDK version (default 8, parse XML/Gradle if possible).
    - [ ] Generate build commands (e.g., `mvn clean package -DskipTests`).
    - [ ] Test on a few dataset repos.

## 3. Core Iris Adaptation
- [ ] **Copy Core**: Copy `origin_tools/iris/iris/src` to `src/adapted_tools/iris/core_adapted`.
- [ ] **Refactor Iris**: Modify `core_adapted/iris.py` to:
    - [ ] Accept `project_path`, `build_command`, `jdk_version` as arguments (decouple from `build_info.csv`).
    - [ ] Use the new Config system for LLM calls.
    - [ ] Mock LLM response for testing purposes.

## 4. Runner & Workflow
- [ ] **Runner Script**: Implement `src/adapted_tools/iris/run_iris.py`.
    - [ ] **Filtering**: Implement filters for:
        - [ ] Language (Java only for now).
        - [ ] Vulnerability Type (Chinese mapping).
        - [ ] Specific CVE.
        - [ ] Top K (Index order).
    - [ ] **Workflow Loop**:
        - [ ] Read `index.csv`.
        - [ ] Checkout `last_vuln_commit`.
        - [ ] Generate Build Info.
        - [ ] Run Iris Core.
        - [ ] Collect results.
- [ ] **Evaluation**:
    - [ ] Implement "Hit" logic: Check if detected lines overlap with modified functions in the patch.

## 5. Testing & Verification
- [ ] **Mock Test**: Create a test case with mocked LLM to verify the pipeline flow (Build -> Analyze -> Report).
- [ ] **Real Project Test**: Run on 5 Java projects from `dataset_patch`.
    - [ ] Verify "Not Detected" path works (pipeline completes without error).
    - [ ] Verify "Detected" path (if lucky, or mock a detection).

## 6. Documentation
- [ ] **Implementation Doc**: Create `docs/iris_implementation.md` recording details.
