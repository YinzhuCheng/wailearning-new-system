/**
 * Canonical Markdown + KaTeX + semantic-card demo block for the school SPA.
 *
 * The live demo starts with a lightweight base example and lets the viewer
 * expand the colored-card and image examples on demand.
 */
export const DEMO_MARKDOWN_IMAGE_PATH = '/markdown-demo-card-image.svg'

export const MARKDOWN_BASE_EXAMPLE_MARKDOWN = `**Markdown + LaTeX 标准示例**

以下示例先展示基础 Markdown 与公式渲染。你可以直接写普通正文、列表和数学公式。

1. 普通正文继续使用标准 Markdown。
2. 行内公式可用 \`\\( ... \\)\` 或 \`$...$\`。
3. 独立公式可用 \`$$ ... $$\` 或 \`\\[ ... \\]\`。

行内公式示例：\\( P(A\\mid B)=\\dfrac{P(B\\mid A)P(A)}{P(B)} \\)

独立公式示例：

$$
\\sum_{i=1}^{n} i = \\frac{n(n+1)}{2}
$$
`

export const MARKDOWN_CARD_EXAMPLE_MARKDOWN = `:::example 示例用法
1. 价格、配额、返回示例适合放进卡片。
2. 普通正文继续使用标准 Markdown。
3. 卡片内部依然支持 **粗体**、列表、\`行内代码\`、图片和公式。
:::

:::pricing 价格说明
- 输入：**$5 / M Tokens**
- 输出：**$30 / M Tokens**
- Web Search：**$0.01 / request**
:::

:::note 插图示例
卡片示例适合展示结构化内容，默认不会自动展开到编辑器外部。
:::

:::tip 当前结论
- 先完成最小可视化流程，再补充更复杂的图表。
:::

:::warning 待确认
- 如果图太复杂，先用箱线图说明差异会更稳妥。
:::

:::danger 常见误区
- 不要把样式直接写死在每一段 HTML 里。
- 不要用单独的英文方括号 \`[ ... ]\` 冒充数学公式定界符。
:::
`

export const MARKDOWN_IMAGE_EXAMPLE_MARKDOWN = `![课程卡片与插图示意图](${DEMO_MARKDOWN_IMAGE_PATH})`

export const MARKDOWN_LATEX_EXAMPLE_MARKDOWN = [
  MARKDOWN_BASE_EXAMPLE_MARKDOWN.trimEnd(),
  MARKDOWN_CARD_EXAMPLE_MARKDOWN.trimEnd(),
  MARKDOWN_IMAGE_EXAMPLE_MARKDOWN.trimEnd()
]
  .filter(Boolean)
  .join('\n\n')
