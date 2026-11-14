# tgflow

插件化的 Telegram 转发流水线框架。业务规则全部拆成可插拔插件，框架本身零业务。

从生产项目 `tg_sync` 抽出的通用内核——原来 1200 行的 `sync.py` 里焊死了清洗规则、
发送逻辑、去重策略，改一条规则要动主流程。现在规则是插件，框架是框架。

## 架构

```
tgflow/
├── core/                 框架层（零业务，零 Telegram 依赖）
│   ├── plugin.py         Plugin 契约 + Hook 定义
│   ├── context.py        MessageContext —— 贯穿链路的可变状态
│   ├── registry.py       注册表 + 依赖拓扑排序 + 插件自动发现
│   ├── pipeline.py       流水线：按 hook 执行插件链
│   └── entities.py       UTF-16 实体偏移运算（最容易出错的地方）
├── plugins/              内置业务插件（丢一个 .py 进目录即生效）
│   ├── content_filter.py 垃圾消息拦截（验证/发卡/黑产）
│   ├── cleaner.py        源频道尾注清洗 + 品牌 URL 改写
│   ├── pan_link.py       网盘链接识别
│   ├── brand.py          官网链接注入
│   └── notify.py         转发/入库结果通知
└── adapters/             传输层（唯一知道 Telegram 的地方）
    ├── telegram.py       Telethon 实体工厂 + 按钮提取
    ├── sender.py         发送器（Bot inline 键盘 / 匿名管理员正文链接）
    └── promo.py          推广链接规则
```

## 快速开始

```python
import asyncio
from tgflow import build_registry
from tgflow.adapters.telegram import make_context
from tgflow.runtime import Runtime

registry = build_registry("tgflow.plugins")   # 自动发现并注册内置插件
runtime = Runtime(registry)

async def main():
    await runtime.start()
    ctx = await runtime.process(message, source="my_channel", target=target)
    print(ctx.delivered, ctx.text)

asyncio.run(main())
```

## 写一个插件

插件就是实现了 `Plugin` 契约的类，放进 `tgflow/plugins/` 就自动生效：

```python
from tgflow.core import Hook, MessageContext, Plugin

class WordCountPlugin(Plugin):
    name = "word_count"
    priority = 50          # 越小越先执行

    async def on_message(self, ctx: MessageContext) -> None:
        ctx.extras["words"] = len(ctx.text.split())

    async def filter(self, ctx: MessageContext) -> None:
        if len(ctx.text) < 5:
            ctx.drop_with("内容过短")

PLUGIN = WordCountPlugin()   # 模块级导出，框架会自动注册
```

### Hook 生命周期

| Hook | 时机 | 能做什么 |
|------|------|---------|
| `on_message` | 消息刚到 | 观察、提取信息 |
| `filter` | 过滤阶段 | `ctx.drop_with(reason)` 否决 |
| `transform` | 内容改写 | 改 `ctx.text` / `ctx.entities` |
| `before_send` | 发送前最后一刻 | 改最终载荷 |
| `after_send` | 发送成功 | 记账、通知 |
| `on_error` | 发送失败 | 告警、重试 |

### 插件契约要点

- 插件**不 import Telethon**，需要造实体就调 `ctx.make_text_url(offset, length, url)`
- hook 方法可以同步也可以异步，框架都会 await
- `requires = ("other_plugin",)` 声明依赖，框架按拓扑序初始化
- 插件抛异常不会中断链路，错误记在 `ctx.extras["plugin_errors"]`
- 同一 hook 内按 `priority` 升序执行

### UTF-16 偏移（最容易踩的坑）

Telegram 实体偏移是 UTF-16 码元，Python 字符串是码点。直接改文本会让所有链接错位。
**永远用 `tgflow.core` 里的工具函数**：

```python
from tgflow.core import delete_ranges, rewrite_urls, utf16_len

text, entities = delete_ranges(text, entities, [(start, end)])   # 删区间
text, entities = rewrite_urls(text, entities, (("old.com", "new.com"),))
```

## 内置插件

| 插件 | 作用 |
|------|------|
| `content_filter` | 拦截入群验证、发卡广告、博彩黑产 |
| `cleaner` | 剔除源频道引流尾注，改写品牌 URL |
| `pan_link` | 识别夸克/百度/阿里/115/迅雷等网盘链接 |
| `brand` | 末尾注入官网可点击链接 |
| `notify` | 转发/入库结果推送 |

## 自定义插件包

不想改框架源码时，指定自己的包：

```python
registry = build_registry("my_plugins", only=["word_count"])
```

`only` 是模块名白名单，模块需暴露 `PLUGIN`（单个实例）或 `PLUGINS`（列表）。

## 测试

```bash
python3 -m venv .venv && .venv/bin/pip install telethon==1.36.0
.venv/bin/python tests/test_core.py
```

不需要 pytest，assert 风格自检脚本，退出码 0 即通过。

## 安装

```bash
pip install -r requirements.txt
```

依赖：`telethon==1.36.0`（Telegram 客户端）、`flask`（可选 Web 面板）。

## License

MIT
