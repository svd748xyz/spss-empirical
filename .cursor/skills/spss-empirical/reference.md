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
| mediation | x, m, y，可选 controls | 三条回归 + Sobel |
| moderation | x, w, y，可选 controls | 均值中心化、分层交互、±1SD 简单斜率 |

量表分在语法里用 `MEAN()` 计算，题项有缺失时按有效题项取平均，并在方法部分沿用报告中的这句话。

## 选择逻辑

1. 多个题项合成一个分数，且用户要信度：`reliability`。用户明确要求维度探索时再加 `efa`。用户要求共同方法偏差时再加 `harman`，并写明题项是否与 `efa` 相同。α 不能代替因素分析。用户要求检查极端值时加 `zscreen`，没有要求删除就不删。
2. 两个连续变量的线性关系：`correlation`。用户要求 Spearman 时停止并说明本版本只跑 Pearson。
3. 一个连续因变量、一组预测变量：`regression`。用户给出先后进入顺序时，`blocks` 写成多层，后一层必须包含前一层变量。
4. 两组：`ttest`。三组及以上的单因素：`anova`。重复测量、非参数、卡方：不做。
5. 用户明确要中介：`mediation`。报告 a、b、c、c′ 和 Sobel。不要声称做了 Bootstrap 或安装了 PROCESS。
6. 用户明确要调节：`moderation`。交互项不显著时，讨论不把简单斜率说成调节成立。
7. 描述统计默认包含人口学和进入模型的连续变量。

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

报告由程序生成：均值和标准差保留两位；r、β、R²、α 保留三位并省略前导零；t、F 保留两位；p 小于 .001 写作 `<.001`。相关、回归和 t 检验表用星号，表注为 `* p < .05，** p < .01，*** p < .001`。

## 追踪

每次运行目录：

- `analysis_plan.json`：实际执行的方案
- `analysis.sps` / `analysis.spj`：语法和生产作业
- `viewer.txt`：SPSS 查看器文本，含授权首行和 `Error #`
- `oms/*.xml`：原始表
- `prepared_data.csv` 与 `数据说明.md`：Excel/CSV 的整理结果
- `实证分析报告.docx`：该次报告副本

项目根目录的 `实证分析报告.docx` 是最近一次成功写出的副本。
