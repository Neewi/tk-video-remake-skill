# 运行模式与批量交付

## 模式判定

每个 run 只使用一种模式，并由 `run.json.run_mode` 固定：

- `REVIEW_INCREMENTAL`：默认模式。普通“复刻这条视频”“用某型号复刻”以及未明确要求全部直出的请求都属于此模式。
- `DIRECT_BATCH`：只有用户明确要求直接、一次性或批量生成 BASE 与全部 5 个变体的参考图和提示词时使用。

“直接生成一个版本”“先出基础版”不属于六版直出。无法判断是否要承担六次宫格生成时使用默认模式，不询问扩展范围。

创建 run 时分别使用：

```bash
scripts/create_run.py --source <video> --sku <sku> --mode review
scripts/create_run.py --source <video> --sku <sku> --mode batch
```

## REVIEW_INCREMENTAL

阶段一展示 `script-review.md` 后停止。用户每次选择 BASE 或单个 Vxx，阶段二只生成该分支的一张 B1 和一条 Symphony 提示词。完成后允许继续其他分支。

## DIRECT_BATCH

阶段一仍生成完整 `script-review.md`，作为六个分支共享的可追溯执行记录，但不把它设为人工审核停点。若没有真正阻塞的产品事实冲突，立即按固定顺序执行：

```text
BASE → V01 → V02 → V03 → V04 → V05
```

每个分支必须分别：

1. 从磁盘重新读取同一份 `script-review.md`，合成该分支的有效执行稿。
2. 校验事实、动作可实现性与目标时长。起草阶段就把每个分支约束在单段上限内；校验失败时内部压缩或改写该分支并再次校验，不要求用户编辑，不做语速加速。
3. 运行 `manage_delivery_branch.py start`。
4. 生成该分支独立的一张 B1 宫格与一条 Symphony 提示词并完成提示词校验。
5. 运行 `manage_delivery_branch.py complete`。

六个分支不得共用同一张宫格。提示词和宫格一一对应，目录结构继续使用 `02-storyboard/<script-id>/` 与 `03-symphony/<script-id>/`。

## 失败与续跑

批量任务不是全有或全无。某个分支无法完成时：

```bash
scripts/manage_delivery_branch.py fail <run-dir> <script-review.md> <script-id> --reason <简短原因>
```

保留所有已完成文件，在 `run.json` 中记录失败分支和原因，并停止本轮批量执行。不要越过失败分支继续生成后续版本。用户要求继续或重试批量任务时，按 `delivery_plan` 顺序找到第一个状态不是 `complete` 的分支，从该分支继续，不覆盖已完成分支。

每次状态变化都会更新 run 根目录的 `delivery-summary.md`。六个分支全部完成后，展示该汇总，并同时展示六张 B1 与六条提示词的文件入口。

## 允许停止的情况

六版直出只省略阶段一人工审核，不绕过真实阻塞：SKU 无法唯一解析、产品资料库验证失败、源视频不可读、源视频绑定失败或无法安全确定目标商品事实时仍应停止并提出一个最短问题。源视频超过时长上限不属于阻塞，按既定规则自动截取前段。
