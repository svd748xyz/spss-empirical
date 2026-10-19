# SPSS 实证分析 Agent

在 Windows 上调用本机已授权的 IBM SPSS Statistics，为社科、教育、心理问卷研究生成可追溯的中文 Word 报告。对话流程由 Cursor Skill `spss-empirical` 约束；统计由 `spss_agent` 交给 SPSS Production Facility 执行。

交付方式：把本仓库地址发给 Agent，由 Agent 完成安装。使用者不需要自己执行命令。

## 给 Agent 的安装步骤

用户给出本仓库的 GitHub 地址并要求安装时，按顺序做完：

1. 确认系统是 Windows。不是 Windows 就停止并说明本包只能在 Windows 上调用 SPSS。
2. 若当前目录还不是本仓库，克隆到用户选择的可写路径。已经在仓库里就不要重复克隆。
3. 在仓库根目录执行 `powershell -ExecutionPolicy Bypass -File .\install.ps1`。
4. 脚本会安装 Python 依赖、检测 SPSS，并把 Skill 写入 Cursor 用户 Skill 目录。把脚本打印的 SPSS 版本和路径告诉用户。
5. 脚本失败时，把终端原文告诉用户，不要改用其他统计软件冒充 SPSS。
   - 找不到 Python 3.11 或更高版本：请用户安装 Python，然后重新把本仓库地址发给 Agent。
   - 找不到 SPSS：请用户安装已授权的 IBM SPSS Statistics。若 `stats.exe` 不在注册表记录的目录，请用户提供完整路径，设置环境变量 `SPSS_STATS_EXE` 后再运行安装脚本。
6. 安装成功后告诉用户：新开一个对话，指定问卷项目文件夹，确认方案后回复「开始」。分析时不要开着 SPSS 窗口。

可直接发给 Agent 的话：

```text
请安装这个 SPSS 实证分析技能：<仓库地址>
```

## 能力边界

可以做描述统计、频数、Cronbach's α、探索性因素（含旋转载荷表）、Harman 单因子、±3SD 筛查、Pearson 相关、分层回归、独立样本 t、单因素方差分析、Sobel 中介、中心化调节和简单斜率。

不能做验证性因子、AMOS、结构方程、多层模型、logistic、卡方、非参数、Spearman，也不能做 Hayes PROCESS 或 Bootstrap 置信区间。中介结果不能写成 PROCESS 输出。

## 项目文件夹

任选一个可读写目录，放入：

- 数据：`.sav`、`.xlsx` 或 `.csv`
- 问卷、参考文献（可选）
- `需求说明.txt`：主题、假设、方法偏好

## 端到端示例

示例数据由固定随机种子生成，不是某次真实调查。

```powershell
cd D:\AIproject\SPSS-Cursor
py examples\make_demo.py
py -m spss_agent scan examples\demo_questionnaire
py -m spss_agent run examples\demo_questionnaire --plan examples\demo_questionnaire\分析方案.json
```

完成后查看：

- `examples\demo_questionnaire\实证分析报告.docx`
- `examples\demo_questionnaire\spss_output\<时间戳>\` 中的 `analysis.sps`、`viewer.txt`、`oms\`、`run_manifest.json`、`数据说明.md`

方案覆盖描述统计、Cronbach's α、相关、分层回归、独立样本 t 检验、单因素方差分析、Sobel 中介和中心化调节（含 ±1SD 简单斜率）。报告不包含未计算的 Bootstrap 置信区间。

## 目录

```text
spss_agent/                 检测、扫描、语法、SPSS 调用、OMS 解析、Word
.cursor/skills/spss-empirical/   Skill 说明与方案字段
examples/demo_questionnaire/     需求说明、分析方案和示例数据
examples/make_demo.py            生成示例 CSV
```

数字只从 OMS XML 读取。语法日志出现 `Error #` 时，命令以非零状态退出，已经导出的表仍会写入报告，缺失的检验留空。
