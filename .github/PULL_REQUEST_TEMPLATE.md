<!--
For Chinese contributors: 请直接用中文填写。
For English contributors: please fill in English. All fields marked (EN) accept English.
-->

## PR Type

- [ ] fix
- [ ] feat
- [ ] refactor
- [ ] docs
- [ ] chore
- [ ] test

## Background And Problem

请描述当前问题、影响范围与触发场景。
*(EN) Describe the problem, its impact, and what triggers it.*

## Scope Of Change

请按当前 PR 的真实受影响改动面，完整列出变更范围（不得遗漏文件名）：

- 请先执行以下脚本（可复制）并在正文贴出完整输出（禁止只贴命令）：
```bash
BASE=$(git merge-base origin/main HEAD)
echo "CURRENT_HEAD=$(git rev-parse HEAD)"
echo "CURRENT_BASE=$BASE"
echo "FILES_CHANGED=$(git diff --name-only --diff-filter=ACMRDTUXB \"$BASE\" HEAD | wc -l)"
git diff --stat "$BASE" HEAD
git diff --numstat "$BASE" HEAD
git diff --name-only --diff-filter=ACMRDTUXB "$BASE" HEAD
```

请在正文按输出结果顺序原样贴出，不得截断、不得复用旧值；若有追加 commit，需重复重算并覆盖旧数据。
处理已有 PR 的 review 反馈时，修改本模板不会自动更新已打开 PR 的正文；必须同步编辑 PR 描述中的 Scope、文件清单、Head、验证结果和兼容性说明。

请直接粘贴上述命令输出，不得截断。若 PR 在提交周期内有新增 commit，提交说明前必须重算并覆盖旧值（禁止沿用历史头信息）。
请按受影响改动面说明本次影响范围（如 backend/web/api/docs/治理资产等），包含 governance 文件时请同步解释变更动机与影响面。

请在正文中同步写出本 PR 的当前 Head（如 `Current HEAD: <hash>`）。
若本 PR 有新 commit，请确认正文中仅保留该 commit 对应的 Head 并标注：`本段已重算（本次提交）。`

若本 PR 包含 `.github/**`、`AGENTS.md`、`CLAUDE.md`、`.github/instructions/**`、`.claude/skills/**` 等协作与治理文件，请补充“变更原因 + 影响面 + 回滚方式（默认 revert）”。
并补充该类文件的治理资产验证命令与结果（至少包含 `python scripts/check_ai_assets.py` 的结果）。

## EXTRACT_PROMPT Change

若本 PR 修改了 `src/services/image_stock_extractor.py` 的 `EXTRACT_PROMPT`，请在下方贴出本次 PR 最新完整 prompt。

- 变更前：
- 变更后：

## Issue Link

必须填写以下之一：
- `Fixes #<issue_number>`
- `Refs #<issue_number>`
- 无 Issue 时说明原因与验收标准。

## Visual Evidence (if applicable)

若涉及报告格式、报告渲染效果或 Web UI，请在此处附受影响页面截图；前后对比优先。

- 受影响页面需与 PR 内容一致（按改动面选择，不限定特定页面）：
  - 仅 backend-only 或 docs-only PR 可不附 UI 截图，并在此处注明原因。
  - 修改了报告/页面展示时，至少附 1 张桌面端截图，移动端截图按实际可复现情况补充。

截图提交要求（必填）：

- 截图来源（请选择其一并补齐链接）：
  - Playwright 脚本产物（`apps/dsa-web/test-results/**/*.png`）
  - CI Artifact 链接（含截图路径与重放/查看说明）
  - 本地可复现命令（含截图输出路径）
- 复现截图命令（至少给出一种）：
  - `cd apps/dsa-web && npx playwright test ...`（按实际可复现实验脚本填写）
  - 或在有后端/登录凭证情况下运行 `npm run test:smoke` 并说明截图来源。

- 截图链接（或外部可访问证据）：
- 产物路径（示例）：`apps/dsa-web/test-results/**/*.png`
- 复现命令（示例）：
  - `cd apps/dsa-web && npx playwright test e2e/smoke.spec.ts --grep "settings page"`
- 无法截图时需写明原因与可复现替代证据。
  - 若涉及受影响页面，请覆盖对应报告页/列表页/设置页关键状态视图（按实际触达面选择）；
  - 不可用真实历史报告时，请补充可复用的 mock 页（含 mock 数据）或 Actions artifact 链接，并在 PR 评论中给出复现步骤与截图入口。
  - 若采用 mock 页面，需说明复现起始环境（命令 + 产物路径）并确认至少可复现出 1 张桌面端截图。
  - 修改了报告页/AI 建议页/市场结构展示时，至少附 1 张包含新增卡片（如 `MarketStructureCard`）可见区域的桌面截图；如使用 mock 页面，请说明 mock 的触发条件与参数。

## Verification Commands And Results

请填写你实际执行过的命令和关键结果（不要只写“已测试”）。

- ai-governance：pass / fail（链接）
- backend-gate：pass / fail（链接）
- docker-build：pass / fail（链接）
- web-gate：pass / fail（链接）
- check-ai-assets：pass / fail（命令：`python scripts/check_ai_assets.py`，建议附输出/日志）

- Head/CI 结果（建议粘贴一行）：`当前 Head CI：ai-governance:..., backend-gate:..., docker-build:..., web-gate:...`

## Compatibility And Risk

请说明兼容性影响、潜在风险（如无请写 `None`）。

  - 是否触及运行时配置、路由或迁移语义：是 / 否
  - 是否触及 provider/model/base URL 相关语义：是 / 否
  - 若是，必须逐条说明（建议按“文件 | 命中文本 | false-positive 依据 | 运行时影响 | 回滚与验证”逐条提交）：
    - 命中来源（文件与关键词/扫描项）
    - 是否为 false positive（是 / 否）
    - 旧行为是否有静默清理或迁移语义影响（有 / 无）
    - 回滚方案与验证依据
    - 建议按以下格式逐项填写并完整列出 1 行/文件（不满足请直接写 `N/A`）：
      - ```
        | 文件 | 命中文本 | false-positive 依据 | 运行时影响 | 回滚与验证 |
        | --- | --- | --- | --- | --- |
        | api/v1/endpoints/analysis.py | provider/model/base_url | False-positive（文档说明） | 无 | 回归原有配置链路 |
        | docs/... | model_used | False-positive（展示字段） | 无 | revert 即可恢复 |
        ```
    - 常见 false-positive 命中样例（仅作参考，可直接替换）：
      - `.github/PULL_REQUEST_TEMPLATE.md`（PR 模板或说明文案）
      - `docs/architecture/api_spec.json`（文档级 API 示例地址）
      - `docs/full-guide*.md`（配置说明与展示文档）
      - `.env` / `.env.example` 若不在本 PR diff 中，请明确写出扫描命中来自其他文本线索，并附 `git diff --name-only <base> HEAD -- .env .env.example` 为空的核验依据
      - `api_spec`、测试 mock、历史展示字段的快照/元数据定义
    - 若同一语句出现在模板、文档、测试、mock 或展示字段中，请在表中明确写明 `false-positive`，并说明为何不触发运行时迁移或 provider/model/base URL 加载链路。
  - 请确认命中源是否属于以下非运行时改动：仅模板文本、注释、测试、文档、单测 mock；若是 false positive 请在下方逐条列明“文件-命中文本-判定依据”。
    - 常见非运行时命中示例：`api_spec.json` 中服务器 URL 示例、文档中的配置说明、PR/治理模板描述、测试 mock/fixture、报告展示字段说明。
  - 若存在运行时影响或兼容风险，请同步列出“旧配置迁移路径（含回退步骤）”与验证依据（例如回归测试、CI 结果或本地复现命令）。
  - 若仅为展示字段（如历史快照元数据）改动，请在此明确写明：历史展示字段不影响运行时调用路径、持久化清理与迁移。

## Rollback Plan

请写一条可执行的回滚方案（必填）。

- 默认可回退方案：`revert this PR`，并说明是否需要外部配置回填。

## Checklist

- [ ] 本 PR 有明确动机和业务价值 / This PR has a clear motivation and value
- [ ] 已提供可复现的验证命令与结果 / Reproducible verification commands and results are included
- [ ] 已评估兼容性与风险 / Compatibility and risk have been assessed
- [ ] 若触及 provider/model/base URL 或运行时配置迁移扫描项，已逐条说明命中来源、是否 false positive、静默清理/回退路径与验证依据
- [ ] 已提供回滚方案 / A rollback plan is provided
- [ ] 若修改报告格式或 Web UI 界面，已在 PR 正文/评论附受影响页面截图，不提交一次性截图文件到仓库 / If report formatting or Web UI changed, attach screenshots in PR body/comments and do not commit one-off screenshots in the repo
- [ ] 若涉及用户可见变更，已同步更新相关文档与 `docs/CHANGELOG.md`；`README.md` 仅用于首页级信息变化，细节优先写入 `docs/*.md` / If user-visible changes are included, relevant docs and `docs/CHANGELOG.md` are updated
