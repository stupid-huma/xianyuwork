# xianyuwork 项目架构说明

这份文档写给：

- 新接手项目的程序员
- 后续维护者
- 需要快速理解项目的 AI
- 准备扩展 API、闲鱼监听、自动发货等功能的人

目标是让读者快速理解：

1. 项目结构。
2. 各脚本职责。
3. 模块之间的调用关系。
4. 订单状态机如何工作。
5. local / API 模式如何接入。
6. 未来修改应该从哪里下手。

---

# 1. 项目整体设计

项目核心是：

```text
文件夹监听 + 订单状态机 + SQLite 持久化 + Telegram 审核
```

当前不是一个 Web 服务，也不是复杂微服务结构。

它主要通过以下方式运行：

```text
run.py
├── run_bot.py
└── run_worker.py
    ├── folder_watcher
    └── edited_watcher
```

整体数据流：

```text
data/incoming/
-> folder_watcher
-> OrderService
-> SQLite + data/orders/ORD_xxx/
-> edited_watcher
-> WatermarkProcessor
-> Telegram Bot
-> OrderService
-> final/
```

---

# 2. 核心原则

项目里最重要的业务原则：

```text
original 只保存买家原图
edited 只保存真正处理完成的图片
preview 只能从 edited 生成
final 默认从 edited 复制
```

这条原则会影响所有代码修改。

不要在 local 模式里把 `original` 自动复制成 `edited`。

不要从 `original` 直接生成 `preview`。

---

# 3. 顶层目录结构

```text
xianyuwork/
├── main.py
├── run.py
├── run_worker.py
├── run_bot.py
├── smoke_test.py
├── requirements.txt
├── config/
│   ├── settings.py
│   └── paths.py
├── app/
│   ├── core/
│   ├── storage/
│   ├── sources/
│   ├── processors/
│   ├── notifiers/
│   ├── bots/
│   └── workers/
├── services/
└── data/
```

---

# 4. 顶层脚本职责

## 4.1 `main.py`

职责：

```text
项目初始化检查
```

通常用于部署后第一次检查。

它应该负责：

- 加载 settings。
- 确保目录存在。
- 初始化数据库。
- 校验运行配置。
- 打印当前模式和路径。

它不应该负责：

- 监听文件。
- 启动 Telegram Bot。
- 处理订单。
- 调用 AI API。

---

## 4.2 `run.py`

职责：

```text
统一启动入口
```

它通过 `subprocess.Popen` 同时启动：

```text
run_bot.py
run_worker.py
```

常用命令：

```bash
python run.py
python run.py --no-bot
python run.py --no-worker
```

调用关系：

```text
run.py
├── subprocess -> run_bot.py
└── subprocess -> run_worker.py
```

注意：

- `run.py` 自己不处理业务。
- 它只是进程启动器。
- 子进程退出时，它会停止其他进程，避免只剩一个进程孤立运行。

---

## 4.3 `run_worker.py`

职责：

```text
启动 worker
```

支持三种模式：

```text
folder：只监听 incoming/
edited：只监听 edited/
both：同时监听 incoming/ 和 edited/
```

当前默认：

```python
mode = "both"
```

所以：

```bash
python run_worker.py
```

等价于：

```bash
python run_worker.py --mode both
```

---

## 4.4 `run_bot.py`

职责：

```text
启动 Telegram Bot
```

负责接收 Telegram 命令，然后调用 `app/bots/commands.py` 或相关 bot 逻辑。

它不应该直接写复杂业务规则。

复杂业务规则应该放在：

```text
app/core/order_service.py
```

---

## 4.5 `smoke_test.py`

职责：

```text
端到端冒烟测试
```

它验证核心流程是否可用：

```text
创建订单
-> 等待 edited
-> 模拟人工放入 edited
-> edited_watcher 生成 preview
-> reject
-> rejected 归档
-> 再次放入 edited
-> 再次生成 preview
-> approve
-> preview_sent
-> buyer_confirmed
-> final_sent
-> completed
```

这个文件非常适合新程序员理解整体状态流。

---

# 5. config 层

## 5.1 `config/settings.py`

职责：

```text
全局配置中心
```

主要配置：

```python
image_processor_mode
api_provider
default_image_prompt
openai_api_key
qwen_api_key
data_dir
incoming_dir
orders_dir
database_path
watermark_text
watermark_opacity
preview_max_size
watch_interval_seconds
```

其中：

```python
image_processor_mode = "local" | "api"
api_provider = "qwen" | "openai"
```

决定图像处理方式。

---

## 5.2 `config/paths.py`

职责：

```text
统一管理文件路径
```

它应该负责生成：

```text
data/incoming/
data/orders/
data/orders/ORD_xxx/original/
data/orders/ORD_xxx/edited/
data/orders/ORD_xxx/preview/
data/orders/ORD_xxx/final/
data/orders/ORD_xxx/rejected/
```

业务代码不应该到处手写路径字符串。

---

# 6. app/core 层

`app/core` 是业务核心。

## 6.1 `app/core/enums.py`

职责：

```text
定义所有枚举
```

通常包括：

```text
OrderStatus
ImageStatus
OrderEvent
ReviewDecision
```

---

## 6.2 `app/core/models.py`

职责：

```text
定义核心数据结构
```

通常包括：

```text
Order
OrderImage
OrderStateLog
```

---

## 6.3 `app/core/order_service.py`

这是整个项目最重要的文件。

职责：

```text
订单状态机 + 核心业务规则
```

它负责：

```text
create_order()
add_image()
create_order_with_image()
wait_for_edited()
start_processing()
process_order()
generate_preview_for_image()
generate_previews()
approve_review()
reject_review()
mark_preview_sent()
mark_buyer_confirmed()
prepare_final_images()
mark_final_sent()
complete_order()
cancel_order()
mark_failed()
```

任何订单状态变化都应该通过 `OrderService`。

不要直接修改：

```python
order.status = xxx
```

---

# 7. app/storage 层

## 7.1 `app/storage/database.py`

职责：

```text
SQLite 数据持久化
```

负责：

- 保存订单
- 查询订单
- 保存状态日志

---

## 7.2 `app/storage/file_store.py`

职责：

```text
文件复制、移动、稳定性检查
```

常见职责：

```text
copy_original_image()
copy_edited_image()
copy_final_image()
wait_until_file_stable()
```

---

# 8. app/workers 层

## 8.1 `app/workers/folder_watcher.py`

职责：

```text
监听 incoming/，把新图片变成订单
```

流程：

```text
discover_images()
-> wait_until_file_stable()
-> order_service.create_order_with_image()
-> source.mark_consumed()
-> 根据 image_processor_mode 决定下一步
```

local 模式：

```text
order_service.wait_for_edited()
```

API 模式：

```text
order_service.process_order(processor_mode="api")
```

---

## 8.2 `app/workers/edited_watcher.py`

职责：

```text
监听 data/orders/*/edited/
```

流程：

```text
加载候选订单
-> 扫描 edited/
-> 匹配 OrderImage
-> image.mark_edited()
-> order_service.generate_preview_for_image()
-> 如果订单进入 waiting_for_review，通知 Telegram
```

注意：

```text
edited_watcher 不负责调用 AI。
它只处理已经出现在 edited/ 的成图。
```

---

# 9. app/processors 层

## `app/processors/watermark_processor.py`

职责：

```text
从 edited 图生成带水印 preview
```

输入：

```text
edited image path
```

输出：

```text
preview image path
```

---

# 10. services 层

当前通常有：

```text
services/
├── image_api_client.py
├── qwen_client.py
└── openai_client.py
```

## 10.1 `services/image_api_client.py`

职责：

```text
统一 API provider 分发入口
```

核心函数：

```python
process_image_with_provider(
    input_path,
    output_path,
    prompt,
    settings,
)
```

内部根据：

```python
settings.api_provider
```

分发到：

```text
qwen_client
openai_client
```

---

## 10.2 `services/qwen_client.py`

职责：

```text
调用 Qwen / DashScope 图像 API
```

输入：

```text
original path
output edited path
prompt
settings
```

输出：

```text
edited path
```

---

## 10.3 `services/openai_client.py`

职责：

```text
调用 OpenAI 图像 API
```

输入输出约定和 Qwen 一样。

---

# 11. app/notifiers 层

## `app/notifiers/telegram_notifier.py`

职责：

```text
主动发送 Telegram 通知
```

例如：

- 新订单等待处理。
- preview 生成，等待审核。
- 订单状态变化。

---

# 12. app/bots 层

## 12.1 `app/bots/telegram_bot.py`

职责：

```text
Telegram Bot 主体
```

负责注册 handler、接收消息、验证用户身份等。

---

## 12.2 `app/bots/commands.py`

职责：

```text
处理 Telegram 命令
```

命令最终应该调用：

```text
OrderService
```

例如：

```text
/approve ORD_xxx
-> order_service.approve_review(order_id)
```

---

# 13. local 模式调用链

用户把图放入：

```text
data/incoming/
```

调用链：

```text
run_worker.py
-> folder_watcher
-> create_order_with_image
-> original/
-> wait_for_edited
```

然后用户人工修图，把图放入：

```text
data/orders/ORD_xxx/edited/
```

调用链：

```text
edited_watcher
-> generate_preview_for_image
-> preview/
-> waiting_for_review
-> Telegram 通知
```

---

# 14. API 模式调用链

调用链：

```text
folder_watcher
-> process_order(api)
-> image_api_client
-> qwen/openai provider
-> edited/
-> generate_preview()
-> preview/
-> waiting_for_review
```

API provider 只负责：

```text
original -> edited
```

preview 仍然由本地 watermark_processor 生成。

---

# 15. 打回重做流程

Telegram 执行：

```text
/reject ORD_xxx 原因
```

调用链：

```text
commands.py
-> order_service.reject_review()
-> rejected/
-> 清空 edited/preview/final
-> rework_required
```

然后 edited_watcher 再次监听新的 edited 图。

---

# 16. 新增 AI provider 的开发步骤

假设新增 provider：

```text
fooai
```

## 16.1 新增文件

新增：

```text
services/fooai_client.py
```

统一接口：

```python
from pathlib import Path
from config.settings import Settings


def process_image(
    input_path: Path,
    output_path: Path,
    prompt: str,
    settings: Settings,
) -> Path:
    return output_path
```

## 16.2 修改 `services/image_api_client.py`

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

## 16.3 修改 `config/settings.py`

加入：

```python
api_provider: Literal["qwen", "openai", "fooai"] = "qwen"
```

以及：

```python
fooai_api_key: str = Field(default="", alias="FOOAI_API_KEY")
```

## 16.4 修改配置校验

```python
if self.api_provider == "fooai" and not self.fooai_api_key:
    raise ValueError(...)
```

---

# 17. 未来添加闲鱼监听建议

推荐新增：

```text
app/sources/xianyu_source.py
app/workers/xianyu_watcher.py
```

职责：

```text
xianyu_source：只负责读取闲鱼消息
xianyu_watcher：把闲鱼消息转换成订单动作
order_service：仍然只负责状态机
```

不要让 OrderService 直接依赖闲鱼平台。

---

# 18. 修改代码时的注意事项

## 不要绕过 OrderService

错误：

```python
order.status = OrderStatus.COMPLETED
repository.save_order(order)
```

正确：

```python
order_service.complete_order(order_id)
```

## 不要从 original 生成 preview

错误：

```text
original -> preview
```

正确：

```text
original -> edited -> preview
```

## 不要在 local 模式自动生成 edited

local 模式的意义是：

```text
人工或外部工具生成 edited
```

## API provider 只能输出 edited

正确职责：

```text
API provider: original -> edited
WatermarkProcessor: edited -> preview
```

---

# 19. 推荐阅读顺序

新程序员或 AI 接手项目时，建议按这个顺序看：

```text
1. docs/USER_WORKFLOW.md
2. docs/DEVELOPER_ARCHITECTURE.md
3. README.md
4. smoke_test.py
5. app/core/order_service.py
6. app/workers/folder_watcher.py
7. app/workers/edited_watcher.py
8. services/image_api_client.py
9. app/bots/commands.py
```

最重要的三个文件：

```text
app/core/order_service.py
app/workers/folder_watcher.py
app/workers/edited_watcher.py
```

---

# 20. 一句话总结

这个项目的核心不是“修图 API”，而是：

```text
用稳定的状态机，把闲鱼修图订单从收图、处理、审核、预览、确认到最终交付完整串起来。
```

AI API 只是其中一个可替换的 edited 生成器。

只要遵守：

```text
original -> edited -> preview -> final
```

这个主链路，后续扩展 Qwen、OpenAI、其他模型、闲鱼监听、自动发货，都不会推翻现有结构。
