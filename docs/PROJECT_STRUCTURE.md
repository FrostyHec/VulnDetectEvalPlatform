# 项目结构说明

此文档概述本仓库的主要目录与用途，重点关注 `src` 目录以及如何通过统一的 `envs.py` 来引用工程内路径。

---

总体说明

- **根目录**: 包含 `environment.yml`、`dataset/`、`docs/`、`origin_tools/`、`scripts/`、`src/` 等。
- **`origin_tools/`**: 存放原始/参考工具集合，仅作参考。
- **`dataset/`**: 存放数据集（项目中若需引用数据集路径，请通过 `envs.py` 提供的变量访问）。

---

重点 — `src` 目录

`src/` 是最主要的代码目录，包含以下子模块（以文件夹为单位说明）:

- `src/adapted_tools/`：项目中适配或封装的外部工具集合，示例子目录 `primeVul` 用于存放与 PrimeVul 相关适配代码。
- `src/common/`：公共代码与配置。
  - `src/common/config/envs.py`：非常重要的文件，用来集中定义项目中的“全局路径”或“工程内固定位置”。
    - 当前定义了 `ROOT_DIR`：项目根目录（通过相对位置自动计算）。
    - 新增示例变量 `DATASET_DIR`（指向仓库顶层的 `dataset/`），建议新增任何需要全局引用的文件夹路径都在此文件中添加。
- `src/experiments/`：实验相关代码与脚本。
- `src/scripts/`：脚本集合，例如 `dataset_preprocessing` 用于数据预处理相关脚本。
- `src/test/`：测试相关代码。

具体文件与说明（快速索引）

- `src/__init__.py`：包声明
- `src/adapted_tools/__init__.py`、`src/adapted_tools/primeVul/__init__.py`：适配工具包入口
- `src/common/__init__.py`、`src/common/config/__init__.py`：公共模块入口
- `src/common/config/envs.py`：核心的路径定义（见下节）
- `src/scripts/dataset_preprocessing/dataset_patch/__init__.py`：数据补丁预处理脚本入口

---

关于 `envs.py`（必须遵守的约定）

- 统一入口：所有工程内跨模块的“固定”路径应从 `src/common/config/envs.py` 导出并在代码中引用，而不是在各处硬编码相对路径或使用 `..` 的相对导入路径。
- 典型使用：

```python
from common.config.envs import ROOT_DIR, DATASET_DIR
import os

# 指向 dataset 下的某个文件
file_path = os.path.join(DATASET_DIR, 'dataset_patch', '...')

# 或使用 ROOT_DIR + 相对路径
config_path = os.path.join(ROOT_DIR, 'some', 'path', 'config.yaml')
```

- 增加新全局目录：如果项目需要稳定引用仓库中其它顶层目录（比如 `logs/`、`models/` 等），请在 `envs.py` 中新增对应变量，例如：

```python
# 在 envs.py 中
MODELS_DIR = os.path.join(ROOT_DIR, 'models')
```

- 仅存放路径：`envs.py` 的职责是定义路径常量，不要在其中进行大量业务逻辑或导入会引起副作用的模块。

---

维护建议

- 文档：当新增顶层目录或改变目录结构时，同时更新 `docs/PROJECT_STRUCTURE.md` 与 `src/common/config/envs.py`。
- origin_tools：仅作为参考，使用时请先拷贝或封装到 `src/adapted_tools/` 下并在 `envs.py` 中添加路径（如需要）。

---

文件位置

- 本文档：`docs/PROJECT_STRUCTURE.md`
- 核心 env 文件：`src/common/config/envs.py`