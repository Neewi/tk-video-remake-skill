# 产品资料库规范

## 1. 目录结构

默认根目录由 `workspace.yaml.product_library` 指定。相对路径以 `workspace.yaml` 所在目录为基准：

```text
product-library/
├── catalog.yaml
├── <sku-a>/
│   ├── product.yaml
│   └── images/ ...
└── <sku-b>/
    ├── product.yaml
    └── images/
        ├── tablet/
        ├── accessories/
        ├── bundle/
        └── screen/
```

产品原图是长期身份资料，不复制进 Skill，也不得被生成图覆盖。

## 2. 默认选择规则

- “复刻视频”默认表示使用自有商品复刻，读取 `catalog.yaml.default_sku`。
- 用户指定 SKU、产品名或别名时覆盖默认值；运行 `scripts/select_product.py --sku <用户原文>` 解析为标准 SKU。
- 用户要求查看或选择商品时，运行 `scripts/select_product.py --list`。只展示 `enabled` 不为 `false` 的商品。
- 未指定商品且没有提出选择要求时，运行 `scripts/select_product.py` 使用默认 SKU。
- 找不到或匹配到多个商品时停下询问，不做包含匹配、相似拼写推断或随机选择。
- 只有用户明确要求保留源片商品时，才不读取默认 SKU，并使用 `SOURCE_FAITHFUL`。
- 确定标准 SKU 后运行 `scripts/validate_product_library.py --sku <标准 SKU>`；验证失败时停下，不生成分镜。
- 一个 run 只允许绑定一个标准 SKU；只读取该 SKU 目录的 `product.yaml` 和图片，不得从其他 SKU 补图或补事实。

`catalog.yaml` 是可选商品索引：

```yaml
default_sku: T10P
products:
  - sku: T10P
    path: ./T10P
    enabled: true
  - sku: TB02
    path: ./TB02
    enabled: true
  - sku: TAB10
    path: ./TAB10
    enabled: true
```

每个 `sku` 必须唯一。`path` 相对于产品资料库根目录，且必须留在该目录内。把暂不允许用户选择的商品设为 `enabled: false`。产品名和别名放在对应 SKU 的 `product.yaml` 中：

```yaml
sku: TB02
product_name: TB02 Tablet Bundle
aliases:
  - TB02
  - TB02套装
  - TB02平板
```

## 3. 产品事实

`product.yaml` 至少包含：

- `sku`
- `product_name`
- `bundle_includes`
- `facts`
- `allowed_claims`
- `forbidden_claims`
- `reference_priority`

建议同时填写 `aliases`，让用户可用自然称呼选择该 SKU。新增 SKU 时以 [`assets/product.example.yaml`](../assets/product.example.yaml) 为字段模板，并建立 `images/tablet`、`images/accessories`、`images/bundle` 与 `images/screen`；不得复制其他 SKU 的事实充当占位内容。

价格、折扣、库存和活动日期易变化。只有有效 `offer` 或用户本轮明确确认时才可进入目标脚本。

## 4. 图片职责

- `tablet/`：定义实物平板颜色、正背面、摄像头、边框、接口和 3/4 外观。
- `accessories/`：定义每种配件的颜色、形状和数量身份。
- `bundle/`：定义已确认的套装组合和空间关系。
- `bundle/package*`：只定义包装盒外观，不证明盒内实物颜色、数量或配置。
- `screen/`：定义可合法展示的界面；缺失时使用批准的中性无文字界面，不伪造第三方 App。

图片与 `product.yaml` 冲突时停下询问。包装与实物看起来冲突时，可以分别用于包装和实物，但必须在脚本、宫格提示和 Symphony 提示词中明确分开锁定。

## 5. 逐对象替换

阶段一必须建立映射：

- 源平板 → 目标平板身份图。
- 源触控笔 → 目标触控笔单品图。
- 源保护套 → 目标保护套单品图。
- 源包装盒 → 目标包装专用图。
- 源片其他配件 → 对应目标配件图。

遵守以下约束：

- 只替换源片实际出现或人工批准新增的商品对象。
- 资料库里存在键盘、鼠标或线材，不代表每条视频都要展示。
- 套装合照不能代替平板正背面身份图。
- 同一视频不混用不同颜色或外观版本。
- 看不见的接口、按钮、摄像头和包装侧面不要发明。

## 6. Symphony 视觉输入

- 提示词必须在有宫格和无宫格两种情况下都能独立成立；宫格只加强构图、景别、人物站位和动作瞬间。
- 产品资料库图片用于生成和检查宫格；实际生成时提供的产品图只锁定商品外观，不承担人物、环境、剧情或时间线定义。
- 提示词不得出现产品图文件名、图片编号、上传建议或上传顺序。
- 把平板、配件、保护套和包装身份直接写成自足的文字约束；人物、环境、动作和摄影机也必须由文字锚点与完整时间线自足定义。
- 宫格编号只可作为时间段的附加定位，删除编号后画面描述仍必须完整可执行。

## 7. 仅选中 T10P 时的特别注意

- 本节只在标准 SKU 为 `T10P` 时适用；其他 SKU 必须完全忽略本节。
- 平板实物为黑色/深灰色，前后顶部居中单摄像头，背面下方左右各一组扬声器孔。
- 触控笔为银灰色，保护套为黑色。
- 包装图只用于包装外观；即使包装侧面勾选 `Pink`，也不得把 T10P 实物改成粉色。
- 源片未出现键盘、鼠标和线材时，不自动加入宫格或视频。
- 未确认处理器、内存、尺寸、续航、操作系统、兼容性、价格、折扣和库存时，不得沿用源片声称。
