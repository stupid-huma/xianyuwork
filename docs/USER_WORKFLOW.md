# 闲鱼修图工作流使用说明

这份文档写给第一次接触本项目的人。

目标是让你知道：

1. 这个项目是干什么的。
2. 日常应该怎么使用。
3. local 模式和 API 模式有什么区别。
4. 如何切换 local / API 模式。
5. 未来想添加新的 AI 模型，要新增哪些文件、修改哪些地方。

>**切换处理模式和新增模型在标题5和10**

---
# 1. 项目用途

本项目用于搭建一个“闲鱼修图订单”的半自动处理流程。

它当前不做这些事情：

- 不自动监听闲鱼聊天。
- 不自动向买家发送图片。
- 不自动识别买家是否确认收货。

它当前主要做这些事情：

- 自动从 `data/incoming/` 收集买家原图。
- 自动创建订单。
- 自动保存原图到订单目录。
- 等待人工修图，或者后续调用 API 修图。
- 自动从修好的图生成带水印预览图。
- 通过 Telegram 或命令推进订单状态。
- 在买家确认后准备高清无水印 final 图。

一句话理解：

```text
这个项目负责把“收图 -> 修图 -> 加水印预览 -> 审核 -> 交付高清图”的流程固定下来。
```

---

# 2. 最重要的目录

日常使用最重要的是 `data/` 目录。

```text
data/
├── incoming/
├── orders/
│   └── ORD_xxx/
│       ├── original/
│       ├── edited/
│       ├── preview/
│       ├── final/
│       ├── rejected/
│       └── metadata.json
└── database/
    └── xianyu_photo_workflow.db
```

各目录含义：

| 目录 | 作用 |
| --- | --- |
| `data/incoming/` | 你把买家原图放到这里 |
| `original/` | 系统保存买家原图 |
| `edited/` | 真正修好的成图，人工或 API 放这里 |
| `preview/` | 系统从 edited 生成的带水印预览图 |
| `final/` | 买家确认后准备的高清无水印交付图 |
| `rejected/` | 审核打回时归档旧图 |
| `metadata.json` | 当前订单的元数据备份 |
| `database/` | SQLite 数据库 |

最重要的规则：

```text
original 只放买家原图
edited 只放真正修好的图片
preview 只能从 edited 生成
final 默认从 edited 复制
```

---

# 3. local 模式工作流程

`local` 是默认模式。

local 模式表示：

```text
系统不调用 AI API。
你自己手动修图。
你把修好的图放进 edited/。
系统再生成 preview。
```

完整流程：

```text
1. 买家发来原图
2. 你把原图放入 data/incoming/
3. worker 发现图片
4. 系统创建订单 ORD_xxx
5. 系统把原图复制到 data/orders/ORD_xxx/original/
6. 订单进入 waiting_for_edited
7. 你用 Photoshop、GPT Plus、网页工具或其他方式修图
8. 你把修好的图放入 data/orders/ORD_xxx/edited/
9. edited_watcher 发现 edited 图
10. 系统从 edited 图生成带水印 preview
11. 订单进入 waiting_for_review
12. 你在 Telegram 或命令里审核
13. 审核通过后，你手动把 preview 发给买家
14. 买家确认后，你执行 buyer_confirmed
15. 系统准备 final 高清无水印图
16. 你发送 final 图给买家
17. 完成订单
```

local 模式的关键点：

```text
local 模式不会自动生成 edited。
local 模式不会从 original 直接生成 preview。
preview 必须等 edited 里有成图后才会生成。
```

---

# 4. API 模式工作流程

API 模式表示：

```text
系统调用配置好的图像 AI API 自动修图。
API 输出 edited。
系统再从 edited 生成 preview。
```

完整流程：

```text
1. 买家发来原图
2. 你把原图放入 data/incoming/
3. worker 发现图片
4. 系统创建订单 ORD_xxx
5. 系统保存 original
6. 系统调用 API provider
7. API 把处理好的图输出到 edited/
8. 系统从 edited 生成带水印 preview
9. 订单进入 waiting_for_review
10. 你审核 preview
11. 审核通过后，你手动把 preview 发给买家
12. 买家确认后，系统准备 final 高清图
13. 你发送 final 给买家
14. 完成订单
```

API 模式和 local 模式的区别：

| 模式 | edited 从哪里来 |
| --- | --- |
| local | 你手动修图后放入 `edited/` |
| api | 系统调用 API 自动生成到 `edited/` |

共同点：

```text
无论 local 还是 API，preview 都只从 edited 生成。
```

---

# 5. 如何切换 local 和 API 模式

模式配置不放在 `.env`，而是在：

```text
config/settings.py
```

打开这个文件，找到：

```python
image_processor_mode = "local"
api_provider = "qwen"
default_image_prompt = (
    "在保持原始构图、人物特征和色彩关系的基础上，提升清晰度、修复模糊、"
    "优化细节质感，输出自然真实的高清效果图。"
)
```

## 5.1 切换到 local 模式

```python
image_processor_mode = "local"
```

local 模式不需要配置 AI API key。

## 5.2 切换到 Qwen API 模式

```python
image_processor_mode = "api"
api_provider = "qwen"
```

然后在 `.env` 中配置：

```env
QWEN_API_KEY=你的key
```

或者：

```env
DASHSCOPE_API_KEY=你的key
```

## 5.3 切换到 OpenAI API 模式

```python
image_processor_mode = "api"
api_provider = "openai"
```

然后在 `.env` 中配置：

```env
OPENAI_API_KEY=你的key
```

---

# 6. `.env` 应该放什么

`.env` 只放运行环境和密钥。

示例：

```env
APP_ENV=dev
LOG_LEVEL=INFO

TELEGRAM_BOT_TOKEN=
TELEGRAM_ADMIN_USER_ID=

OPENAI_API_KEY=
QWEN_API_KEY=

DATA_DIR=data
INCOMING_DIR=data/incoming
ORDERS_DIR=data/orders
DATABASE_PATH=data/database/xianyu_photo_workflow.db

WATERMARK_TEXT=PREVIEW
WATERMARK_OPACITY=90
PREVIEW_MAX_SIZE=1600
SUPPORTED_IMAGE_EXTENSIONS=.jpg,.jpeg,.png,.webp
WATCH_INTERVAL_SECONDS=2
```

注意：

```text
不要把 .env 提交到 GitHub。
不要把 API key 写进代码。
```

---

# 7. 常用启动命令

## 7.1 初始化检查

```bash
python main.py
```

这个命令会检查：

- 配置是否正确。
- 目录是否存在。
- 数据库是否能初始化。
- API 模式下 key 是否存在。

## 7.2 冒烟测试

```bash
python smoke_test.py
```

它会模拟完整订单流程：

```text
创建订单
-> 等待 edited
-> 模拟人工放入 edited
-> 生成 preview
-> 打回重做
-> 再次放入 edited
-> 再次生成 preview
-> 审核通过
-> 标记预览已发
-> 买家确认
-> 生成 final
-> 完成订单
```

## 7.3 启动完整系统

同时启动 Telegram Bot 和 Worker：

```bash
python run.py
```

## 7.4 只启动 Worker

```bash
python run.py --no-bot
```

## 7.5 只启动 Telegram Bot

```bash
python run.py --no-worker
```

## 7.6 直接启动 Worker

```bash
python run_worker.py
```

`run_worker.py` 默认同时监听：

```text
data/incoming/
data/orders/*/edited/
```

等价于：

```bash
python run_worker.py --mode both
```

## 7.7 Worker 单次扫描

适合调试：

```bash
python run_worker.py --once --no-telegram
```

## 7.8 只扫描 incoming

```bash
python run_worker.py --mode folder --once --no-telegram
```

## 7.9 只扫描 edited

```bash
python run_worker.py --mode edited --once --no-telegram
```

---

# 8. Telegram 命令

| 命令 | 作用 |
| --- | --- |
| `/help` | 查看帮助 |
| `/list` | 查看最近订单 |
| `/status ORD_xxx` | 查看订单状态 |
| `/process ORD_xxx` | 按当前模式处理订单。local 模式只提示你放入 edited |
| `/previews ORD_xxx` | 重新发送水印预览图给你审核 |
| `/approve ORD_xxx` | 内部审核通过 |
| `/reject ORD_xxx 原因` | 打回重做 |
| `/preview_sent ORD_xxx` | 标记已经把水印预览发给买家 |
| `/buyer_confirmed ORD_xxx` | 标记买家已确认 |
| `/final_sent ORD_xxx` | 准备并标记高清无水印图已发送 |
| `/complete ORD_xxx` | 完成订单 |
| `/cancel ORD_xxx 原因` | 取消订单 |

---

# 9. 打回重做流程

如果预览图不满意，执行：

```text
/reject ORD_xxx 皮肤细节还需要更自然
```

系统会：

1. 把旧的 `edited/`、`preview/`、`final/` 文件移动到 `rejected/`。
2. 清空订单图片上的旧路径。
3. 订单进入 `rework_required`。
4. 等你重新把修好的图放入 `edited/`。
5. `edited_watcher` 再次生成 preview。
6. 订单重新进入 `waiting_for_review`。

这样可以避免旧图被反复处理。

---

# 10. 未来如何添加新的 AI 模型

假设你要新增一个 provider，名字叫：

```text
fooai
```

目标是让项目支持：

```python
api_provider = "fooai"
```

需要做下面几步。

## 10.1 新增 provider 客户端文件

新增文件：

```text
services/fooai_client.py
```

这个文件至少要提供一个统一函数：

```python
from pathlib import Path

from config.settings import Settings


def process_image(
    input_path: Path,
    output_path: Path,
    prompt: str,
    settings: Settings,
) -> Path:
    """
    调用 FooAI 图像模型。

    参数：
    - input_path: 原图路径，来自 original/
    - output_path: 期望输出路径，通常在 edited/
    - prompt: 修图提示词
    - settings: 全局配置

    返回：
    - 处理完成后的 edited 图片路径
    """
    # 1. 读取 input_path
    # 2. 调用 FooAI API
    # 3. 保存结果到 output_path
    # 4. 返回 output_path

    return output_path
```

统一约定：

```text
输入是 original 图片。
输出必须写入 edited。
返回值必须是最终 edited 图片路径。
```

## 10.2 修改 API 分发文件

修改：

```text
services/image_api_client.py
```

找到：

```python
def process_image_with_provider(...):
    provider = settings.api_provider
```

加入：

```python
if provider == "fooai":
    from services.fooai_client import process_image

    return process_image(
        input_path=input_path,
        output_path=output_path,
        prompt=prompt,
        settings=settings,
    )
```

这样 `order_service.process_order()` 就能通过统一入口调用新模型。

## 10.3 修改 settings.py

修改：

```text
config/settings.py
```

把 provider 类型加入可选值：

```python
api_provider: Literal["qwen", "openai", "fooai"] = "qwen"
```

增加 FooAI 需要的配置，例如：

```python
fooai_endpoint: str = "https://example.com/api"
fooai_model: str = "foo-image-model"
```

如果 FooAI 需要 key，建议放 `.env`：

```python
fooai_api_key: str = Field(default="", alias="FOOAI_API_KEY")
```

然后 `.env` 添加：

```env
FOOAI_API_KEY=
```

## 10.4 修改运行时校验

在 `config/settings.py` 的：

```python
validate_runtime_config()
```

里增加：

```python
if self.api_provider == "fooai" and not self.fooai_api_key:
    raise ValueError("FOOAI_API_KEY is required when api_provider='fooai'")
```

## 10.5 修改 README 或文档

在文档里说明：

```python
image_processor_mode = "api"
api_provider = "fooai"
```

以及 `.env` 需要：

```env
FOOAI_API_KEY=
```

## 10.6 测试新模型

先运行：

```bash
python main.py
```

再把 `settings.py` 改成：

```python
image_processor_mode = "api"
api_provider = "fooai"
```

放一张测试图到：

```text
data/incoming/
```

执行：

```bash
python run_worker.py --once --no-telegram
```

检查是否生成：

```text
data/orders/ORD_xxx/edited/
data/orders/ORD_xxx/preview/
```

如果这两个目录都有正确图片，说明 provider 接入成功。

---

# 11. 常见问题

## 11.1 为什么 local 模式没有生成 edited？

这是正常的。

local 模式下，edited 必须由你手动放入：

```text
data/orders/ORD_xxx/edited/
```

## 11.2 为什么没有生成 preview？

先检查：

```text
data/orders/ORD_xxx/edited/
```

里面是否有图片。

没有 edited，就不会生成 preview。

## 11.3 为什么 API 模式报缺少 key？

检查 `.env` 是否有对应 key。

Qwen：

```env
QWEN_API_KEY=
```

OpenAI：

```env
OPENAI_API_KEY=
```

还要检查：

```python
api_provider = "qwen"
```

是否和你配置的 key 对应。

## 11.4 能不能自动给闲鱼买家发图？

当前版本不做。

未来可以新增独立模块，例如：

```text
app/sources/xianyu_source.py
app/delivery/xianyu_sender.py
```

但不要把它直接写进订单状态机核心里，最好保持模块独立。
