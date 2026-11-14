# 插件开发 SDK

面向写 tgflow 插件的人。读完这页就能独立产出插件。

## 1. 插件是什么

一个插件 = 一个实现了 `Plugin` 契约的类。框架只认契约，不认具体实现。

```python
from tgflow.core import MessageContext, Plugin

class MyPlugin(Plugin):
    name = "my_plugin"      # 唯一 ID，缺省用类名
    priority = 100          # 同 hook 内升序执行
    requires = ()           # 依赖的插件名元组

    async def setup(self, ctx) -> None:
        """框架启动时调用一次。可以在这里开连接、读配置。"""

    async def teardown(self) -> None:
        """框架停止时调用一次。释放资源。"""

    async def on_message(self, ctx) -> None: ...
    async def filter(self, ctx) -> None: ...
    async def transform(self, ctx) -> None: ...
    async def before_send(self, ctx) -> None: ...
    async def after_send(self, ctx) -> None: ...
    async def on_error(self, ctx) -> None: ...
```

只需要覆写关心的 hook，其余继承基类的空实现。

## 2. MessageContext

插件拿到的上下文对象，可读全部状态、写自己负责的部分。

| 字段 | 类型 | 说明 |
|------|------|------|
| `message` | Any | 原始消息对象（Telethon Message） |
| `source` | str | 源频道标识 |
| `target` | Any | 目标实体 |
| `route` | dict | 路由配置 |
| `account` | dict | 账号配置 |
| `text` | str | **即将发送的正文**（可改） |
| `entities` | list | **正文实体**（可改） |
| `drop` | bool | 是否否决 |
| `drop_reason` | str | 否决原因 |
| `delivered` | bool | 是否发送成功 |
| `error` | str | 失败原因 |
| `extras` | dict | 插件间共享的草稿本 |

`extras` 是插件间传数据的唯一通道：

```python
# 生产者
ctx.extras["pan_urls"] = urls

# 消费者
urls = ctx.extras.get("pan_urls", [])
```

框架预置的 `extras` 键：

| 键 | 由谁写入 | 内容 |
|----|----------|------|
| `make_text_url` | 适配层 | 造 TextUrl 实体的工厂函数 |
| `buttons` | 运行时 | `[[(label, url), ...], ...]` 按钮行 |
| `notifier` | 运行时 | 通知发送器 |
| `importer` | 运行时 | 资源入库器 |
| `plugin_errors` | 框架 | 插件异常列表 |

## 3. 生命周期与顺序

```
消息到达
  → on_message（按 priority 升序）
  → filter      → 有插件 drop 则中止
  → transform   → 有插件 drop 则中止
  → before_send
  → 发送
  → after_send  或  on_error
```

`priority` 小的先跑。内置插件的优先级参考：

| priority | 插件 | 为什么 |
|----------|------|--------|
| 5 | `pan_link` | 最先提取链接，后续插件要用 |
| 10 | `content_filter` | 先拦垃圾，省掉后续开销 |
| 20 | `cleaner` | 清洗正文 |
| 80 | `brand` | 靠近发送才注入品牌链接 |
| 90 | `notify` | 发送后才通知 |

## 4. 依赖声明

```python
class ImportPlugin(Plugin):
    name = "importer"
    requires = ("cleaner", "pan_link")
```

框架按拓扑序初始化（`setup` 顺序满足依赖），停止时逆序 `teardown`。
循环依赖、缺失依赖都会在启动时**直接抛异常**——宁可启动失败也不要半初始化。

## 5. UTF-16 实体运算

Telegram 的实体 offset/length 是 **UTF-16 码元**，Python str 是 **码点**。
emoji 一个字 = 2 码元 = 1 码点。直接切片改文本会导致所有链接错位。

**规则：永远不要手工切文本，用框架工具函数。**

```python
from tgflow.core import (
    delete_ranges,      # 删区间
    rewrite_urls,       # 替换 URL
    span_to_py,         # UTF-16 span → Python span
    utf16_len,          # 长度（UTF-16 码元）
    drop_out_of_range,  # 清理越界实体
)
```

删除示例（从右往左删，偏移才不会乱）：

```python
ranges = [(m.start(), m.end()) for m in footer_re.finditer(text)]
text, entities = delete_ranges(text, entities, ranges)
```

替换示例：

```python
text, entities = rewrite_urls(text, entities, (("pinglian.lol", "vault.aaaaaaaa.host"),))
```

追加一个可点击链接：

```python
offset = utf16_len(text)
text += "\n官网"
entities = list(entities) + [ctx.make_text_url(offset, utf16_len("官网"), "https://example.com")]
```

`ctx.make_text_url` 由适配层注入，所以插件本身不用 import Telethon。

## 6. 异常与性能

- 插件抛异常**不会**中断链路，框架记日志并写入 `ctx.extras["plugin_errors"]`
- 关键插件（如过滤）自己捕获异常，别让规则失效导致垃圾消息漏网
- 单个 hook 超过 200ms 会打 WARNING 日志——插件里别做同步 IO
- 插件里可以用 `ctx.extras` 缓存跨消息状态，但要注意多账号并发

## 7. 写一个完整插件

```python
"""把片名统一改成规范格式。"""
import re
from tgflow.core import MessageContext, Plugin

class TitleNormalizer(Plugin):
    name = "title_normalizer"
    priority = 30
    requires = ("cleaner",)

    PATTERN = re.compile(r"^《(.+?)》")

    async def transform(self, ctx: MessageContext) -> None:
        lines = (ctx.text or "").split("\n")
        if not lines:
            return
        m = self.PATTERN.match(lines[0].strip())
        if not m:
            return
        title = m.group(1).strip()
        lines[0] = title
        ctx.text = "\n".join(lines)
        ctx.extras["title"] = title

PLUGIN = TitleNormalizer()
```

放进 `tgflow/plugins/` 或自己的包目录即可被发现。

## 8. 发布插件

把插件做成独立包，暴露 `PLUGIN`：

```
my_plugin/
├── pyproject.toml
└── my_plugin/
    ├── __init__.py     # from .plugin import PLUGIN
    └── plugin.py
```

安装后在宿主项目里：

```python
registry = build_registry("tgflow.plugins")
load_plugins("my_plugin", registry)   # 手动加载外部包
```

## 9. 自检

框架自带断言式测试脚本，不需要 pytest：

```bash
python3 tests/test_core.py   # 退出码 0 = 通过
```

写自己的插件时也这么干——一个 `tests/test_my_plugin.py`，`assert` 完 `raise SystemExit(0)`。
