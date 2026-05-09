# Xianyu Photo Workflow

这是一个面向闲鱼修图订单的半自动工作流项目。当前版本先搭建稳定、可审核、可扩展的本地流程，不自动操作闲鱼，也不自动向买家发图。

核心流程：

```text
买家原图
-> data/incoming/
-> folder_watcher 自动建单并保存到 original/
-> local 模式进入 waiting_for_edited
-> 你手动修图或用外部工具处理
-> 把成图放入 data/orders/{order_id}/edited/
-> edited_watcher 生成带水印 preview
-> Telegram / 命令行内部审核
-> review_approved
-> 你手动把水印预览发给买家
-> preview_sent
-> 买家确认后 buyer_confirmed
-> final_sent
-> completed
```

## 1. 项目结构

```text
xianyu-photo-workflow/
├── main.py
├── run_worker.py
├── run_bot.py
├── smoke_test.py
├── requirements.txt
├── config/
│   ├── settings.py
│   └── paths.py
├── app/
│   ├── core/
│   │   ├── enums.py
│   │   ├── models.py
│   │   └── order_service.py
│   ├── storage/
│   │   ├── database.py
│   │   └── file_store.py
│   ├── sources/
│   │   └── folder_source.py
│   ├── processors/
│   │   └── watermark_processor.py
│   ├── notifiers/
│   │   └── telegram_notifier.py
│   ├── bots/
│   │   ├── telegram_bot.py
│   │   └── commands.py
│   └── workers/
│       ├── folder_watcher.py
│       └── edited_watcher.py
└── data/
    ├── incoming/
    ├── orders/
    │   └── {order_id}/
    │       ├── original/
    │       ├── edited/
    │       ├── preview/
    │       ├── final/
    │       ├── rejected/
    │       └── metadata.json
    └── database/
```

## 2. 安装依赖

Windows PowerShell：

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

macOS / Linux：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. 配置 `.env`

创建 `.env`，local 模式建议保留：

```env
APP_ENV=dev
LOG_LEVEL=INFO

TELEGRAM_BOT_TOKEN=
TELEGRAM_ADMIN_USER_ID=

ENABLE_OPENAI_API=false
OPENAI_API_KEY=
IMAGE_PROCESSOR_MODE=local

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

只做本地测试时，Telegram 可以暂时不填。要启用 Telegram 审核时，再填入 BotFather token 和你的 Telegram 数字 ID。

## 4. 初始化检查

```bash
python main.py
```

这个命令会检查配置、目录、SQLite 数据库和图片处理基础配置。

## 5. 冒烟测试

```bash
python smoke_test.py
```

测试会验证新的 local 状态机：

```text
创建订单
-> 收原图
-> waiting_for_edited
-> 模拟人工放入 edited/
-> edited_watcher 生成 preview
-> waiting_for_review
-> 打回重做并把旧文件归档到 rejected/
-> 再次放入 edited/
-> 重新生成 preview
-> review_approved
-> preview_sent
-> buyer_confirmed
-> final_sent
-> completed
```

## 6. 不接 Telegram 的本地流程

第一步，把买家原图放入：

```text
data/incoming/
```

第二步，只处理 incoming 一次：

```bash
python run_worker.py --mode folder --once --no-telegram
```

它会：

```text
发现 incoming 图片
-> 创建订单
-> 复制原图到 data/orders/{order_id}/original/
-> 订单进入 waiting_for_edited
-> 把 incoming 原文件移动到 data/incoming/_consumed/
```

注意：local 模式不会自动生成 edited，也不会直接生成 preview。

第三步，人工修图完成后，把成图放入：

```text
data/orders/{order_id}/edited/
```

第四步，只处理 edited 回流一次：

```bash
python run_worker.py --mode edited --once --no-telegram
```

它会从 edited 成图生成水印 preview，并在全部图片都有 preview 后把订单推进到 `waiting_for_review`。

## 7. 日常使用

终端 A 启动 Telegram Bot：

```bash
python run_bot.py
```

终端 B 同时监听 incoming 和 edited：

```bash
python run_worker.py --mode both
```

`run_worker.py` 默认模式也是 `both`，所以直接运行 `python run_worker.py` 也可以同时监听两边。

日常操作顺序：

1. 把买家原图放入 `data/incoming/`。
2. worker 自动建单并进入 `waiting_for_edited`。
3. 你处理图片，把成图放入对应订单的 `edited/`。
4. edited_watcher 自动生成水印 preview，并通知你审核。
5. 审核通过后订单进入 `review_approved`，这只表示内部审核通过。
6. 你手动把水印预览发给买家，然后执行 `/preview_sent ORD_xxx`。
7. 买家满意或确认收货后，执行 `/buyer_confirmed ORD_xxx`。
8. 发送高清无水印图后，执行 `/final_sent ORD_xxx`。
9. 订单结束后，执行 `/complete ORD_xxx`。

## 8. Telegram 命令

| 命令 | 作用 |
| --- | --- |
| `/help` | 查看帮助 |
| `/list` | 查看最近订单 |
| `/status ORD_xxx` | 查看订单状态与建议操作 |
| `/process ORD_xxx` | 按 `IMAGE_PROCESSOR_MODE` 处理；local 模式只提示 edited 目录 |
| `/previews ORD_xxx` | 重新发送水印预览图给你审核 |
| `/approve ORD_xxx` | 内部审核通过，进入 `review_approved` |
| `/reject ORD_xxx 原因` | 打回重做，进入 `rework_required` |
| `/preview_sent ORD_xxx` | 标记水印预览已发给买家 |
| `/buyer_confirmed ORD_xxx` | 标记买家已确认 |
| `/final_sent ORD_xxx` | 准备并标记高清无水印图已发送 |
| `/complete ORD_xxx` | 完成订单 |
| `/cancel ORD_xxx 原因` | 取消订单 |

## 9. 打回重做

审核不满意时：

```text
/reject ORD_xxx 皮肤细节还需要更自然
```

系统会把旧的 `edited/`、`preview/`、`final/` 文件移动到：

```text
data/orders/{order_id}/rejected/
```

同时清空订单图片上的旧路径。这样即使 `edited_watcher` 重启，也不会把旧成图重新当成新图处理。

然后你重新处理图片，把新的成图放回：

```text
data/orders/{order_id}/edited/
```

`edited_watcher` 会重新生成 preview，并让订单再次进入 `waiting_for_review`。

## 10. 当前边界

当前版本支持：

- 本地文件夹收图
- 自动建单
- SQLite 保存状态
- metadata.json 备份
- 人工成图回流
- 从 edited 生成水印 preview
- Telegram 审核与状态推进
- 打回重做归档
- local 模式完整冒烟测试

当前版本暂不包含：

- 自动监听闲鱼聊天
- 自动向闲鱼买家发送图片
- 自动调用 OpenAI 图像 API
- 自动识别买家是否确认收货

这些能力后续可以作为独立模块接入，不需要推翻当前状态机。

## 11. 后续扩展

接入图像 API 时，把 `IMAGE_PROCESSOR_MODE` 切到 `with_api`，并实现 `OrderService._process_single_image_with_api()` 中的“原图 -> edited 图”逻辑。状态机仍然保持：API 只负责产出 edited，preview 仍然从 edited 生成。
