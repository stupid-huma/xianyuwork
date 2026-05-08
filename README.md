\# Xianyu Photo Workflow



这是一个面向闲鱼修图订单的半自动工作流项目。



当前版本重点不是全自动操作闲鱼，而是先搭建一条稳定、可扩展、可审核的本地流程：



```text

买家图片

→ data/incoming/

→ 自动建单

→ 保存原图

→ 生成水印预览图

→ Telegram 审核

→ 你确认后发预览给买家

→ 买家确认收货

→ 发送高清无水印版本

```



\---



\## 1. 项目结构



```text

xianyu-photo-workflow/

├── main.py

├── run\_worker.py

├── run\_bot.py

├── smoke\_test.py

├── .env

├── requirements.txt

├── config/

│   ├── \_\_init\_\_.py

│   ├── settings.py

│   └── paths.py

├── app/

│   ├── \_\_init\_\_.py

│   ├── core/

│   │   ├── \_\_init\_\_.py

│   │   ├── enums.py

│   │   ├── models.py

│   │   └── order\_service.py

│   ├── storage/

│   │   ├── \_\_init\_\_.py

│   │   ├── database.py

│   │   └── file\_store.py

│   ├── sources/

│   │   ├── \_\_init\_\_.py

│   │   ├── base.py

│   │   └── folder\_source.py

│   ├── processors/

│   │   ├── \_\_init\_\_.py

│   │   └── watermark\_processor.py

│   ├── notifiers/

│   │   ├── \_\_init\_\_.py

│   │   └── telegram\_notifier.py

│   ├── bots/

│   │   ├── \_\_init\_\_.py

│   │   ├── telegram\_bot.py

│   │   └── commands.py

│   ├── workers/

│   │   ├── \_\_init\_\_.py

│   │   ├── folder\_watcher.py

│   │   └── edited\_watcher.py

│   └── utils/

│       ├── \_\_init\_\_.py

│       ├── id\_generator.py

│       └── image\_utils.py

└── data/

&#x20;   ├── incoming/

&#x20;   ├── orders/

&#x20;   └── database/

```



\---



\## 2. 安装依赖



建议使用虚拟环境。



\### Windows PowerShell



```powershell

python -m venv .venv

.venv\\Scripts\\activate

pip install -r requirements.txt

```



\### macOS / Linux



```bash

python -m venv .venv

source .venv/bin/activate

pip install -r requirements.txt

```



\---



\## 3. 配置 `.env`



先复制或创建 `.env`：



```env

TELEGRAM\_BOT\_TOKEN=

TELEGRAM\_ADMIN\_USER\_ID=



APP\_ENV=dev

ENABLE\_OPENAI\_API=false

OPENAI\_API\_KEY=



DATA\_DIR=data

INCOMING\_DIR=data/incoming

ORDERS\_DIR=data/orders

DATABASE\_PATH=data/database/xianyu\_photo\_workflow.db



WATERMARK\_TEXT=PREVIEW

WATERMARK\_OPACITY=90

PREVIEW\_MAX\_SIZE=1600

SUPPORTED\_IMAGE\_EXTENSIONS=.jpg,.jpeg,.png,.webp

WATCH\_INTERVAL\_SECONDS=2

LOG\_LEVEL=INFO

```



如果你只是本地测试，可以暂时不填 Telegram。



如果你要启用 Telegram 审核，需要填写：



```env

TELEGRAM\_BOT\_TOKEN=你的 BotFather Token

TELEGRAM\_ADMIN\_USER\_ID=你的 Telegram 数字 ID

```



\---



\## 4. 初始化检查



运行：



```bash

python main.py

```



正常情况下会看到：



```text

✅ Xianyu Photo Workflow initialized

```



这个命令会检查：



\* `.env` 是否能读取

\* `data/` 目录是否能创建

\* SQLite 数据库是否能初始化

\* 图片配置是否正常

\* Telegram 配置是否填写



\---



\## 5. 冒烟测试



运行：



```bash

python smoke\_test.py

```



成功后会看到：



```text

✅ Smoke test passed

```



它会自动创建一张测试图片，然后完整跑通：



```text

创建订单

→ 收图

→ 生成水印预览

→ 审核通过

→ 标记预览已发

→ 买家确认

→ 生成最终图

→ 完成订单

```



\---



\## 6. 不接 Telegram 的本地测试流程



\### 第一步：放入图片



把一张图片放到：



```text

data/incoming/

```



例如：



```text

data/incoming/test.jpg

```



\### 第二步：只运行一次 worker



```bash

python run\_worker.py --once --no-telegram

```



它会自动：



```text

发现 data/incoming/test.jpg

→ 创建订单

→ 复制到 data/orders/{order\_id}/original/

→ 复制到 data/orders/{order\_id}/edited/

→ 生成 data/orders/{order\_id}/preview/test\_preview.jpg

→ 把 incoming 原文件移动到 data/incoming/\_consumed/

```



\### 第三步：查看输出



进入：



```text

data/orders/{order\_id}/

```



你应该能看到：



```text

original/

edited/

preview/

final/

metadata.json

```



\---



\## 7. 启动 Telegram Bot



确保 `.env` 已填写：



```env

TELEGRAM\_BOT\_TOKEN=xxx

TELEGRAM\_ADMIN\_USER\_ID=123456789

```



然后运行：



```bash

python run\_bot.py

```



在 Telegram 里给你的 bot 发送：



```text

/start

/help

/list

```



\---



\## 8. 启动自动监听



\### 只监听 incoming



```bash

python run\_worker.py

```



默认会持续监听：



```text

data/incoming/

```



发现图片后会自动建单、生成水印图，并在 Telegram 配置完整时发送审核通知。



\### 同时监听 incoming 和人工修图回流



```bash

python run\_worker.py --mode both

```



这会同时监听：



```text

data/incoming/

data/orders/{order\_id}/edited/

```



\---



\## 9. 推荐日常使用流程



\### 终端 A：启动 Bot



```bash

python run\_bot.py

```



\### 终端 B：启动 Worker



```bash

python run\_worker.py --mode both

```



\### 日常操作



1\. 买家下单后，你手动或半自动把买家图片放入：



```text

data/incoming/

```



2\. worker 自动创建订单并生成水印预览图。



3\. Telegram 收到审核通知。



4\. 审核通过：



```text

点击 ✅ 审核通过

```



或输入：



```text

/approve ORD\_xxx

```



5\. 你把水印预览图发给买家后，点击或输入：



```text

/preview\_sent ORD\_xxx

```



6\. 买家满意并确认收货后，点击或输入：



```text

/buyer\_confirmed ORD\_xxx

```



7\. 准备并标记发送高清无水印版本：



```text

/final\_sent ORD\_xxx

```



8\. 订单完成：



```text

/complete ORD\_xxx

```



\---



\## 10. 人工重修流程



如果审核不满意：



```text

/reject ORD\_xxx 皮肤细节还需要更自然

```



然后你可以把重新处理好的高清图放到：



```text

data/orders/{order\_id}/edited/

```



如果运行了：



```bash

python run\_worker.py --mode both

```



`edited\_watcher` 会自动发现新高清图，并重新生成水印预览图。



\---



\## 11. 常见命令



| 命令                                          | 作用                     |

| ------------------------------------------- | ---------------------- |

| `python main.py`                            | 初始化检查                  |

| `python smoke\_test.py`                      | 完整冒烟测试                 |

| `python run\_worker.py --once --no-telegram` | 本地单次测试                 |

| `python run\_worker.py`                      | 持续监听 incoming          |

| `python run\_worker.py --mode both`          | 同时监听 incoming 和 edited |

| `python run\_bot.py`                         | 启动 Telegram Bot        |



\---



\## 12. Telegram 命令



| 命令                         | 作用          |

| -------------------------- | ----------- |

| `/help`                    | 查看帮助        |

| `/list`                    | 最近订单        |

| `/status ORD\_xxx`          | 查看订单状态      |

| `/process ORD\_xxx`         | 无 API 测试处理  |

| `/previews ORD\_xxx`        | 重新发送水印预览给你  |

| `/approve ORD\_xxx`         | 审核通过        |

| `/reject ORD\_xxx 原因`       | 打回重做        |

| `/preview\_sent ORD\_xxx`    | 标记水印预览已发给买家 |

| `/buyer\_confirmed ORD\_xxx` | 标记买家确认      |

| `/final\_sent ORD\_xxx`      | 准备并标记高清图已发送 |

| `/complete ORD\_xxx`        | 完成订单        |

| `/cancel ORD\_xxx 原因`       | 取消订单        |



\---



\## 13. 当前版本边界



当前版本已经支持：



\* 本地文件夹收图

\* 自动建单

\* SQLite 保存订单状态

\* metadata.json 备份

\* 水印预览图生成

\* Telegram 审核通知

\* Telegram 命令状态机操作

\* 人工修图回流

\* 无 OpenAI API 的完整测试链路



当前版本暂不包含：



\* 真正自动监听闲鱼聊天

\* 自动向闲鱼买家发送图片

\* 自动调用 OpenAI 图像 API

\* 自动识别买家是否确认收货



这些后续可以作为独立模块接入，不需要推翻当前结构。



\---



\## 14. 后续扩展方向



\### 接入 OpenAI API



可以新增：



```text

app/processors/openai\_image\_processor.py

```



然后在 `OrderService` 中把：



```text

process\_order\_without\_ai()

```



扩展成：



```text

process\_order\_with\_ai()

```



\### 接入闲鱼监听



可以新增：



```text

app/sources/xianyu\_source.py

```



实现：



```python

discover\_images()

mark\_consumed()

mark\_failed()

```



然后 worker 可以不用改大结构。



\### 接入 QQ 通知



可以新增：



```text

app/notifiers/qq\_notifier.py

```



保持和 `telegram\_notifier.py` 类似接口。



