# 外挂插件目录

往这里丢 `.py` 插件文件，容器重启后自动被 `tgflow/plugins` 发现机制加载。

每个插件文件需导出模块级 `PLUGIN`（单个实例）或 `PLUGINS`（列表）：

```python
from tgflow.core import MessageContext, Plugin


class MyPlugin(Plugin):
    name = "my_plugin"
    priority = 30

    async def transform(self, ctx: MessageContext) -> None:
        ctx.text = ctx.text.replace("foo", "bar")


PLUGIN = MyPlugin()
```

详见 `docs/PLUGIN_SDK.md`。
