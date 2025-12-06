我需要你写一个提取python代码，将当前数据集转化为类似于primeVul的格式，也就是可以参考在example_ds.jsonl的结构输出（重点是包含如下信息：id（独立生成一个id+concat cve_id），label 0/1表示是否是漏洞，三元组三个字段(project, 漏洞类型（使用本数据集中文的设置），cve_id)，完整的function片段（如果在function外面，则存储完整的文件片段），时间（用commit id就能查到时间））注意，primevul实际上使用了更精准的数据集标注方法（见下面的规则），因此部分case会被drop掉。你最终的输出应该至少包含ds.jsonl，case_summary.csv(记录每一条是否成功/失败，以及使用的哪个规则，)

随后再写一个切分数据集python代码，生成一个index.csv(id（前面ds.jsonl中的id）, 在哪个数据集中：train/val/test三部分），切分方式参考primevul的时间切分方法.

你必须要新开一个适配方案md文档，记录你是如何适配当前数据集到PrimeVul格式数据集的。

（必须测试，你可以写一个test只测试一下前5个能否成功并且正确，必须持续迭代直至成功；注意你不需要删除你写了的test）

数据集jsonl提取需要支持选择是哪个语言（比如只选择java，但必须可以传入多个，比如"java,python"），选择某个漏洞类型（比如只选择sql注入，同样需要可以传入多条类似于语言），以及选择max_samples（比如只选择1000个样本进行转换测试）

PrimeVul的数据集主要是通过如下方法构建出来的，：

具体主要是作了如下事情:
Using filtering to make sure auto labeling assumptions are satisfied
One function in fix
Extract function from CVE Description
Ignoring other hard cases
Train set leakages
Data Duplication: MD5 filter same
Time Leakage: Split dataset by time


=== what PrimeVul did said in their paper ===

```text
B. More Accurate Data Labeling
We propose two new labeling techniques: PRIMEVULONEFUNC and PRIMEVUL-NVDCHECK.
PRIMEVUL-ONEFUNC: We notice that the previous labeling
method has errors particularly when dealing with commits that
modify multiple functions. Therefore, PRIMEVUL-ONEFUNC
regards a function as vulnerable if it’s the only function
changed by a security-related commit.
PRIMEVUL-NVDCHECK: Since human experts have analyzed the CVEs in the NVD database, the vulnerability
description in each CVE entry is a reliable reference to label
vulnerable functions. We develop PRIMEVUL-NVDCHECK as
the following. First, we link security-related commits to their
CVE numbers and the vulnerability description in the NVD
database. We label a function as vulnerable if it satisfies one
of the two following criteria: (1) NVD description explicitly

mentions its name, or (2) NVD description mentions its file
name, and it is the only function changed by the securityrelated commit in that file.
After applying our two labeling techniques, we obtain two
sets of vulnerable functions. Next, we merge the sets and deduplicate the functions again. We normalize the formatting
characters in the functions, and compute their MD5 hashes
to identify and remove duplicates. Subsequently, we label the
post-commit versions of these identified vulnerable functions,
as well as all other unchanged functions within the same
commits, as benign. Only a subset of commits from the merged
database mentioned in Section III-A, meet the criteria for
labeling by our techniques. Commits without any function that
matches these criteria are excluded from our dataset.
Our pipeline results in a collection of 6,968 vulnerable and
228,800 benign functions across 755 projects and 6,827 commits. To assess our labeling accuracy, we conducted a manual
review following the same process used in Section II-B, with
our results presented in Table I. The most accurate prior dataset
SVEN has only 417 vulnerable functions in C/C++, and 386
vulnerable functions in Python. Our PRIMEVUL dataset not
only matches the label accuracy of SVEN but also significantly
expands the collection of vulnerable C/C++ functions by
16.7× compared to SVEN. PRIMEVUL is diverse, containing
140 CWEs (15.6× of SVEN).

As discussed in Section II-C, we need new methods to properly evaluate vulnerability detection models in deployment
settings. This section proposes new evaluation guidelines.
A. Temporal Splits
To minimize the data leakage issue and formulate a realistic
train-evaluate setup for vulnerability detection, we split the
train/validation/test set of PRIMEVUL according to the commit
date of the samples. Concretely, we find the original commit
for each sample and collect the time of that commit, tying
it with the sample. Then, we sort the samples according to
the commit, where the oldest 80% will be the train set, 10%
in the middle will be the validation set, and the most recent
10% will be the test set. We also make sure that the samples
from the same commit will not be split into different sets. This
ensures that the vulnerability detection model is trained using
past data and tested over future data.

2) Paired Functions and Pair-wise Evaluation: As discussed in Section II-D2, evaluating the models on paired
functions—vulnerable and benign versions of code—could
potentially reveal whether a model merely relies on superficial text patterns to make predictions without grasping the
underlying security implications, indicating areas where the
model needs improvement to reduce the false positives and
false negatives.
We collected 5,480 such pairs in PRIMEVUL, significantly
larger than existing paired datasets [12, 20]. Concretely, we
match the vulnerable functions with their patches in PRIMEVUL to construct such pairs. As we show in Table III, the
paired vulnerable functions are fewer than all vulnerable
functions, since not all vulnerable functions have a patch (e.g.,
a patch could delete the vulnerable function), and we only
include those challenging pairs sharing at least 80% of the
string between the vulnerable and benign version.
Accordingly, we also propose a pair-wise evaluation
method. The core idea is to evaluate the model’s predictions on
the entire pair as a single entity, emphasizing the importance
of correctly identifying both the presence and absence of
vulnerabilities in a textually similar context, while recording
the model’s concrete predicting behaviors.
We define four outcomes of the pair-wise prediction:
• Pair-wise Correct Prediction (P-C): The model correctly
predicts the ground-truth labels for both elements of a pair.
• Pair-wise Vulnerable Prediction (P-V): The model incorrectly predicts both elements of the pair as vulnerable.
• Pair-wise Benign Prediction (P-B): The model incorrectly
predicts both elements of the pair as benign.
• Pair-wise Reversed Prediction (P-R): The model incorrectly
and inversely predicts the labels for the pair.
```


----
第二个prompt
好的，现在数据集jsonl和切分的split.csv已经在文件夹中生成，我现在要适配primevul的实验到这个数据集中，你需要
1. 参考现有的程序，正确的撰写数据集加载（放在primevul的common中，primevul实验可以复用）、结果评估（放在common/eval/evaluation中以便复用评估，包括基本的aprf-1(可以用sklearn json来打印结果。以及作者计算的Pair-wise Evaluation等指标)
2、用ignite（你需要下载一下，更新下req文件）撰写训练管线（bert类模型，实现bert类模型用这个数据集训练，eval和test（三个步骤分离，三个数据集加载步骤也模块化，方便后续引入a数据集训练b数据集测试这种）；要求管线每个epoch打印结果，有日志文件输出，best_model，current_model输出，支持中断续训。
【训练的基本信息（lr之类的）应该参数化，开一个config类进行记录，以便训练参数的继承与复写，从而设置多组基准实验【譬如，我在指令中加载某个config对象（dict存）就可以完整加载这个参数以进行训练，我需要基本的训练参数类，同时extend出codet5, codebert, unixcoder三种小模型的训练）
（必须测试，你可以只测试一下第1个epoch能否成功，必须持续迭代直至成功；注意你不需要删除你写了的test）

config可以1, 用dataclasses简化配置
2. 添加一个config_dict，然后包含codet5, codebert, unixcoder三个模型的训练config，然后我可以在指令中指定run哪个config
这三个config有一个默认的输出在output(output/dataset_patch/primevul/default)中，同时我可以在脚本中指定1. 其他文件夹作为路径 2. 单纯传入其他实验名称，比如"exp1“则创建使用exp1文件夹
2. 必须实现我在adapt中的需求，包括传入--continue后中断续训（如果没传入但是文件夹有东西则要报错），传入--load_pretrained加载某个预先训练的参数，同时可以传入其他参数指令覆盖所加载的config中的参数
3.测试用输出应该输出到output/tmp，测试用数据可以存放到src/test

（如果是多点的复杂需求，请针对我的需求详细的分TODO并逐步完成，你可以创建一个TODO文档在docs/TODO.md，记录你划分的todo以及交付需要着重check是否满足需求的点，并且持续迭代直至你完成这些内容；必须进行测试，持续迭代直至代码完全成功；注意你不需要删除你写了的test）