# 上下文分词器

这些文件直接用于本地输入预算计数，由 `core/token_counting.py` 加载并缓存。运行时不下载文件、不请求模型，也不附加固定 token 余量或比例系数。`manifest.json` 保存来源、文件 SHA-256，以及 tiktoken 的正则和特殊 token 定义；加载时核对实际文件。

| 模型标识 | 分词器 | 匹配范围 |
| --- | --- | --- |
| tiktoken 能识别且采用 `cl100k_base` 或 `o200k_base` 的模型 | 对应的本地 tiktoken 词表 | `model_encoding`，匹配文本编码；请求格式仍是估算 |
| Qwen 3.5 及以上编号 | `qwen35.json` | `family`，采用 Qwen3.5-0.8B 公开词表；包括当前 qwen3.8-flash 的模型族估算 |
| 其它 Qwen 标识 | SAG 已携带的 `tokenizer.json` | `family`，复用现有 Qwen 词表 |
| DeepSeek V4、deepseek-flash、deepseek-pro | `deepseek_v4.json` | `family`，采用官方离线计算包 |
| 其它 DeepSeek 标识 | `deepseek_v3.json` | `family`，采用 DeepSeek-V3.2 公开词表 |
| 尚未识别的型号 | SAG 已携带的 `tokenizer.json` | `generic`，明确为通用分词器估算 |

模型选择使用远端标识，支持 OpenRouter 的组织前缀及已知 Provider 的本地前缀。任意本地配置标识不会覆盖远端标识。未公开精确词表的商业型号使用模型族估算，不声明与线上 token 完全一致；真实用量以 Provider 返回的 usage 为准。切换词表不改写已保存会话或记忆记录。

Qwen 3.5 与 DeepSeek V3.2 文件固定到 manifest 指定的上游提交；DeepSeek V4 离线包用文件 SHA-256 固定当前内容。SAG 词表继续使用现有文件，manifest 中的 `existing_asset` 指向该文件，不另存副本。tiktoken 定义采用 0.14.0 的公开编码，词表 SHA-256 与其上游声明一致。

来源：

- [Qwen3.5-0.8B](https://huggingface.co/Qwen/Qwen3.5-0.8B/tree/2fc06364715b967f1860aea9cf38778875588b17)，许可证见 `qwen.LICENSE`。
- [DeepSeek-V3.2](https://huggingface.co/deepseek-ai/DeepSeek-V3.2/tree/a7e62ac04ecb2c0a54d736dc46601c5606cf10a6)，许可证见 `deepseek.LICENSE`。
- [DeepSeek 官方离线 token 计算](https://api-docs.deepseek.com/quick_start/token_usage/)，当前分发包为 `deepseek_v4_tokenizer.zip`。
- [tiktoken](https://github.com/openai/tiktoken)，许可证见 `tiktoken.LICENSE`。
- [SAG 来源清单](../../../vendor/sag/source_manifest.json)。

修改分词规则或词表时同步更新离线计数测试及此清单。后台执行契约指纹包含此清单，恢复时沿现有契约不一致处理停止，不重置旧尝试的请求额度。
