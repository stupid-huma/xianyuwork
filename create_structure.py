import os

structure = {
    ".": ["main.py", "run_worker.py", "run_bot.py", ".env", "requirements.txt"],
    "config": ["settings.py", "paths.py"],
    "app/core": ["enums.py", "models.py", "order_service.py"],
    "app/storage": ["database.py", "file_store.py"],
    "app/sources": ["base.py", "folder_source.py"],
    "app/processors": ["watermark_processor.py"],
    "app/notifiers": ["telegram_notifier.py"],
    "app/bots": ["telegram_bot.py", "commands.py"],
    "app/workers": ["folder_watcher.py", "edited_watcher.py"],
    "app/utils": ["id_generator.py", "image_utils.py"],
    "data": ["incoming", "orders", "database"],
}

for folder, files in structure.items():
    os.makedirs(folder, exist_ok=True)
    for f in files:
        path = os.path.join(folder, f)
        if "." in f:  # 文件
            open(path, 'a').close()
        else:         # 子目录
            os.makedirs(path, exist_ok=True)

print("✅ 项目结构已生成")