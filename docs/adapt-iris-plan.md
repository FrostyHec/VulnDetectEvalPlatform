# Iris 适配 Dataset Patch 计划书

## 1. 概述
本计划旨在将 **Iris**（一种神经符号漏洞检测工具）适配到 `dataset_patch` 数据集。目标是使 Iris 能够扫描 `dataset_patch` 中的代码仓库（涵盖 Java, Python, Node.js），并尽可能覆盖更多的 CWE 漏洞类型。

鉴于 Iris 原生仅支持 Java 且与现有数据集格式差异较大，本计划采用 **“核心复用 + 适配层重写”** 的策略，在 `src/adapted_tools/iris` 下构建适配版本，以解决构建依赖、多语言支持及路径映射等技术挑战。

## 2. 需求分析

### 2.1 输入与输出
- **输入数据**：
  - 代码仓库：`dataset/dataset_patch/repos/` (包含 Java, Python, Node.js 项目)。
  - 索引文件：`dataset/dataset_patch/index.csv` (包含 commit 信息、漏洞类型)。
  - 映射文件：`dataset/dataset_patch/cwe-match.json` (漏洞类型定义)。
- **预期输出**：
  - 漏洞检测报告（兼容 PrimeVul 评估格式）。
  - 中间产物：CodeQL 数据库、生成的查询语句、LLM 分析日志。

### 2.2 核心需求
1.  **多语言支持**：扩展 Iris 以支持 Python 和 Node.js（目前仅支持 Java）。
2.  **构建自动化**：解决 Java 项目的自动编译问题，尽可能提高构建成功率。
3.  **覆盖率**：不要求 100% 适配所有 Case，但需保证主流 CWE（如 SQL注入、XSS、路径遍历）有较高的测试覆盖率。

## 3. 技术挑战与解决方案 (详细)

### 挑战 1: 漏洞类型映射不一致
**问题描述**：`dataset_patch` 使用中文漏洞类型（如“SQL注入”），而 Iris 依赖具体的 CWE ID（如 CWE-89）。两者并非一一对应。
**解决方案**：
- **建立映射表**：利用 `dataset/dataset_patch/cwe-match.json`，编写映射脚本。
- **策略**：
  - 精确匹配：如“SQL注入” -> CWE-89。
  - 集合匹配：如“命令注入”可能对应 CWE-77, CWE-78 等。Iris 若只支持其中一个，则优先适配该 ID。
  - **Action**：在适配层实现 `VulnTypeMapper` 类，负责将数据集的中文类型转换为 Iris 可识别的 CWE ID 列表。

### 挑战 2: Java 项目构建与 CodeQL 依赖
**问题描述**：Iris 依赖 CodeQL 对 Java 项目进行分析，而 Java CodeQL 数据库的创建必须通过成功的编译（Build）。`dataset_patch` 中的项目缺乏统一的构建说明，且历史版本可能难以构建。
**解决方案**：
- **构建信息自动提取**：开发 `gen_build_info.py` 脚本。
  - **探测逻辑**：扫描项目根目录，识别 `pom.xml` (Maven) 或 `build.gradle` (Gradle)。
  - **版本推断**：尝试从配置文件中解析 JDK 版本（`<java.version>`），默认为 JDK 8（针对老旧 CVE）。
  - **命令生成**：自动生成构建命令（如 `mvn clean package -DskipTests`）。
- **容错构建策略**：
  - 优先尝试生成的构建命令。
  - 若失败，尝试 CodeQL 的 **Auto-build** 模式（不指定 command）。
  - 若仍失败，记录日志并跳过该 Case（接受部分数据丢失）。
- **环境隔离**：使用 SDKMAN 或 Docker 容器来切换不同的 JDK 版本，避免环境冲突。

### 挑战 3: Python 与 Node.js 的多语言扩展
**问题描述**：Iris 原生代码（如 `codeql_queries.py`）硬编码了 `import java`，且缺乏 Python/JS 的 CodeQL 查询模板。
**解决方案**：
- **查询模板参数化**：重构 Iris 的查询生成模块。
  - 将 `QL_SOURCE_PREDICATE` 等常量改为模板，支持传入 `{language}` 和 `{imports}`。
  - 为 Python 引入 `import python`，为 JS 引入 `import javascript`。
- **获取标准查询**：
  - Iris 缺乏 Py/JS 的 CWE 查询。
  - **Action**：从 [GitHub CodeQL 官方仓库](https://github.com/github/codeql) 提取标准查询（如 `python/ql/src/Security/CWE-089`），并将其适配为 Iris 的 Source/Sink 格式，或者直接使用 CodeQL 的标准 Path-Problem 查询作为替代。
- **跳过编译**：修改 Iris 的构建流程，对于 Python 和 Node.js，直接运行 `codeql database create --language=...`，跳过构建命令检查。

### 挑战 4: 架构适配策略（重写 vs 修改）
**问题描述**：`origin_tools/iris` 的代码结构与 `dataset_patch` 的数据布局差异巨大。直接修改原仓库代码会导致难以维护，且容易破坏原有逻辑；完全重写则工作量大且难以保证算法一致性（Match 原有工具）。
**解决方案**：**“核心复用 + 适配层重写” (Copy & Adapt)**
- **独立适配目录**：在 `src/adapted_tools/iris` 下工作，不直接修改 `origin_tools/iris`。
- **核心代码复制**：将 `origin_tools/iris/iris/src` 下的核心逻辑文件（如 `iris.py`, `codeql_queries.py`, `utils/`）复制到 `src/adapted_tools/iris/core_adapted/`。
- **最小化修改**：
  - 在 `core_adapted` 中进行必要的修改（如移除硬编码路径、增加多语言支持）。
  - 保持核心算法 Loop（LLM 生成 -> CodeQL 验证 -> 结果过滤）不变。
- **适配器模式**：编写 `run_iris_adapter.py` 作为入口，负责：
  1. 读取 `dataset_patch` 索引。
  2. 准备环境（切换 Commit，生成 Build Info）。
  3. 调用 `core_adapted` 中的功能。
  4. 收集结果并格式化。

### 挑战 5: 环境缺失 (CodeQL)
**问题描述**：当前环境未安装 CodeQL CLI，且 Iris 对版本有要求（推荐 v2.23.2）。
**解决方案**：
- **自动化安装脚本**：编写 `scripts/install_codeql.sh`。
  - 自动下载 CodeQL CLI v2.23.2 二进制包。
  - 下载对应的标准查询包（`codeql-java`, `codeql-python`, `codeql-javascript`）。
  - 配置环境变量 `CODEQL_DIR` 和 `PATH`。

## 4. 详细实施计划

### 阶段 1: 基础设施准备
1.  **CodeQL 安装**：编写并运行安装脚本，确保 CodeQL 可用。
2.  **核心代码迁移**：将 Iris 核心代码复制到 `src/adapted_tools/iris/core_adapted/`。
3.  **依赖清理**：检查复制后的代码依赖，确保 `requirements.txt` 满足需求。

### 阶段 2: 数据预处理与映射
1.  **CWE 映射器**：开发 `src/adapted_tools/iris/utils/cwe_mapper.py`，实现中文漏洞类型到 CWE ID 的转换。
2.  **构建信息生成器**：开发 `src/adapted_tools/iris/utils/gen_build_info.py`，针对 Java 项目生成构建配置。

### 阶段 3: Java 核心适配 (Priority 1)
1.  **代码改造**：修改 `core_adapted/iris.py`，使其接受外部传入的项目路径和构建命令，而不是读取固定的 `build_info.csv`。
2.  **适配器入口**：开发 `src/adapted_tools/iris/run_iris.py`。
    - 实现：读取 Index -> Checkout Commit -> 生成 Build Info -> 调用 Iris Core -> 保存结果。
3.  **验证**：选取 5-10 个 Java CWE-89 (SQL注入) 案例进行跑通测试。

### 阶段 4: 多语言扩展 (Priority 2)
1.  **模板重构**：修改 `core_adapted/codeql_queries.py`，抽象语言相关的 Import 和 Predicate。
2.  **查询库集成**：在 `src/adapted_tools/iris/queries/` 下整理 Python 和 Node.js 的 CodeQL 查询文件。
3.  **流程打通**：在 `run_iris.py` 中增加对 Python/Node.js 的分支处理（跳过构建，指定语言参数）。
4.  **验证**：选取 Python 和 Node.js 的各 5 个案例进行测试。

### 阶段 5: 批量运行与评估
1.  **全量扫描**：对 `dataset_patch` 中匹配支持 CWE 的所有项目进行扫描。
2.  **结果转换**：将 Iris 的输出（通常是 JSON 或 CSV）转换为 PrimeVul 的评估格式。
3.  **统计分析**：统计成功率、构建失败率、漏洞检出率。

## 5. 交付物清单
- `docs/adapt-iris-plan.md` (本计划书)
- `src/adapted_tools/iris/core_adapted/` (修改后的 Iris 核心代码)
- `src/adapted_tools/iris/run_iris.py` (主运行脚本)
- `src/adapted_tools/iris/utils/gen_build_info.py` (构建信息提取工具)
- `scripts/install_codeql.sh` (环境安装脚本)