# 分析方案与方法选择

## 分析方案 JSON

`python -m spss_agent run` 只执行这份方案，不会自行增加检验。

```json
{
  "title": "论文题目",
  "data_file": "data.csv",
  "sheet": null,
  "methods_note": "样本与研究问题的一段话",
  "variables": [
    {"name": "gender", "label": "性别", "values": {"1": "男", "2": "女"}}
  ],
  "scales": [
    {"name": "anxiety", "label": "焦虑", "items": ["anx1", "anx2", "anx3"]}
  ],
  "analyses": []
}
```

`data_file` 可相对项目文件夹。`.sav` 由 SPSS 直接打开；`.xlsx` / `.csv` 会先整理成运行目录里的 `prepared_data.csv`。标签中不要使用英文单引号。

`analyses` 的 `type`：

| type | 必填字段 | SPSS 过程 |
| --- | --- | --- |
| descriptives | vars | DESCRIPTIVES |
| frequencies | vars | FREQUENCIES |
| reliability | scale, items | RELIABILITY /MODEL=ALPHA |
| efa | items | FACTOR，主成分，方差最大旋转；报告含载荷表 |
| harman | items | 同一批题项的未旋转主成分，只解释第一因子方差占比 |
| zscreen | vars | 各变量 ±3 个标准差的人数，默认不删个案 |
| correlation | vars | CORRELATIONS，皮尔逊，双尾 |
| regression | dependent, blocks | REGRESSION，每层一个 ENTER |
| ttest | group, codes, outcomes | T-TEST，codes 为两组取值 |
| anova | factor, outcomes | ONEWAY |
| mediation | x, m, y，可选 controls、structure。m 为一个变量或变量数组。structure 省略或 parallel 为并行；serial 为链式，数组顺序即链条顺序，至少两个、最多三个 | 并行：每个中介一条回归，加上总效应和同时纳入全部中介的回归。链式：后一个中介的方程包含前一个中介。每条特定间接效应做 Sobel |
| moderation | x, w, y，可选 controls。w 为一个变量，或最多三个调节变量的数组 | 均值中心化、各自的二阶交互、±1SD 简单斜率。多个调节变量不估计三者交互 |
| moderated_mediation | x, m, y, w, stage，可选 controls。stage 为 a、b 或 both | 在调节变量的均值和 ±1SD 上估计条件间接效应，并做 Sobel。a 只调节前半路径，b 只调节后半路径，both 为同一调节变量调节两段 |
| spearman | vars | NONPAR CORR，Spearman，双尾 |
| chisq | row, col | CROSSTABS，Pearson 卡方 |
| mannwhitney | group, outcomes，codes 默认 1 和 2 | Mann-Whitney U |
| kruskal | factor, outcomes，codes 为最小和最大分组取值；变量已有 values 时可省略 | Kruskal-Wallis H |
| logistic | dependent, predictors。dependent 为二分类 | LOGISTIC REGRESSION，进入法 |

量表分在语法里用 `MEAN()` 计算，题项有缺失时按有效题项取平均，并在方法部分沿用报告中的这句话。

反向题写在量表的 `reverse` 里，不要求事先改数据。`low` 和 `high` 是该题的最低分和最高分，程序按 `low + high - 原题` 生成 `原题名_r`，信度、因素分析和量表均分都使用这个新变量。

```json
{"name": "anxiety", "label": "焦虑", "items": ["anx1", "anx2", "anx4"], "reverse": [{"item": "anx4", "low": 1, "high": 5}]}
```

三分类及以上要进入回归、相关或控制变量时，给变量加上 `"coding": "dummy"` 和 `"reference"`。参照组不生成变量。方案里仍写原变量名，程序展开成 `原变量名_d取值`。二分类可以继续用原编码，不必设虚拟变量。频数、t 检验的分组和方差分析的因素仍用原变量。

```json
{"name": "grade", "label": "年级", "values": {"1": "大一", "2": "大二", "3": "大三"}, "coding": "dummy", "reference": "1"}
```

## 选择逻辑

1. 多个题项合成一个分数，且用户要信度：`reliability`。用户明确要求维度探索时再加 `efa`。用户要求共同方法偏差时再加 `harman`，并写明题项是否与 `efa` 相同。α 不能代替因素分析。用户要求检查极端值时加 `zscreen`，没有要求删除就不删。
2. 两个连续变量的线性关系：`correlation`。用户明确要求等级相关时用 `spearman`。
3. 一个连续因变量、一组预测变量：`regression`。因变量是二分类时用 `logistic`。用户给出先后进入顺序时，`blocks` 写成多层，后一层必须包含前一层变量。
4. 两组且适合比较均值：`ttest`。三组及以上的单因素：`anova`。用户要求非参数时，两组用 `mannwhitney`，三组及以上用 `kruskal`。两个分类变量用 `chisq`。重复测量不做。
5. 用户明确要中介：`mediation`。报告 a、b、c、c′ 和 Sobel。多个中介且没有先后顺序时，把 `m` 写成数组，做并行中介。中介有先后顺序时，`structure` 写 `serial`，`m` 按原因到结果排列。每条特定间接效应单独检验，不把它们加总后再检验。不要声称做了 Bootstrap 或安装了 PROCESS。
6. 用户明确要调节：`moderation`。一个调节变量写字符串；两到三个调节变量写成数组，只做各自的二阶交互。交互项不显著时，讨论不把简单斜率说成调节成立。调节发生在中介路径上时用 `moderated_mediation`，并写明 `stage`。
7. 描述统计默认包含人口学和进入模型的连续变量。问卷写明反向题时写 `reverse`。三分类及以上进入回归或控制变量时写 `coding` 为 `dummy` 并指定参照组。有序或非正态的连续变量要求等级相关时用 `spearman`。两个分类变量的关联用 `chisq`。用户要求非参数比较时，两组用 `mannwhitney`，三组及以上用 `kruskal`。二分类因变量用 `logistic`。
8. 调用 SPSS 前会检查方案。缺字段、分层回归没有包含上一层、数据里没有对应列，或要求结构方程、Bootstrap、三者交互时，直接说明，不启动 SPSS。

同一方案可以包含上表的子集。不要为了“完整”添加用户没要、数据也支撑不了的模型。

## 调用方式

检测顺序：方案里的 `spss_exe`、环境变量 `SPSS_STATS_EXE`、注册表 `HKLM\SOFTWARE\IBM\SPSS Statistics\*\Setup\Directory`。

执行使用 SPSS Production Facility：

```text
stats.exe analysis.spj -production silent
```

作业把语法输出为 UTF-8 文本，并按块把 OMS XML 写到 `oms/`。正文数字只从这些 XML 的 `number` 属性读取。

运行前若 `stats.exe` 已打开，命令会失败。先关闭 SPSS。

## 统计写法

报告由程序生成，版式按中文期刊三线表，不按英文 APA 省略前导零。均值和标准差保留两位，并写成 `164.98±16.82`。r、β、R²、α、B 保留三位并保留前导零。表内 t、F 保留三位。P 保留三位，小于 0.001 写作 `<0.001`。构成比保留两位。相关表在系数上加星号，表注为 `* p<0.05，** p<0.01，*** p<0.001`。回归表不在系数上加星号，拟合指标写在表下。

## 追踪

每次运行目录：

- `analysis_plan.json`：实际执行的方案
- `analysis.sps` / `analysis.spj`：语法和生产作业
- `viewer.txt`：SPSS 查看器文本，含授权首行和 `Error #`
- `oms/*.xml`：原始表
- `prepared_data.csv` 与 `数据说明.md`：Excel/CSV 的整理结果
- `实证分析报告.docx`：该次报告副本

项目根目录的 `实证分析报告.docx` 是最近一次成功写出的副本。
