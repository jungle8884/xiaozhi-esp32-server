# 小智 AI 学习进度与下一步计划

> **记录时间**：2026-10-13
> **硬件平台**：ESP32-S3 + bread-compact-wifi（面包板 WiFi + SSD1306 OLED）
> **服务端环境**：Windows + conda 环境 `xiaozhi-server`（Python 3.11）
> **关联文档**：`xiaozhi-server-部署总结.md`（部署过程与排障速查表）

---

## 0. 一句话现状

**服务端全链路（VAD→ASR→LLM→TTS）已验收通过，设备端尚未接入。** 下一步目标是打通「ESP32 设备 ↔ 自建服务端」的完整语音链路（阶段 B）。

---

## 1. 项目全景

### 1.1 两个仓库

| 仓库 | 本地路径 | 作用 | 当前状态 |
|---|---|---|---|
| 小智固件 | `D:\CODE\TEST\ESP32\xiaozhi-esp32` | 跑在 ESP32-S3 上的设备端固件 | 已能编译（build/ 存在），**未烧录自建配置** |
| 小智服务端 | `D:\CODE\TEST\ESP32\xiaozhi-esp32-server` | Python 服务端（ASR/LLM/TTS/MCP） | ✅ **已本地跑通** |

### 1.2 数据流

```
┌──────────────┐  ① OTA 请求（拿服务器地址）
│              │ ─────────────────────────────▶ http://10.1.10.130:8003/xiaozhi/ota/
│   ESP32-S3   │ ◀───────────────────────────── 返回 ws://10.1.10.130:8000/xiaozhi/v1/
│  小智固件     │
│              │  ② 语音（OPUS 帧，60ms/帧）
│              │ ─────────────────────────────▶ ws://10.1.10.130:8000/xiaozhi/v1/
└──────────────┘ ◀───────────────────────────── TTS 音频（OPUS）

服务端内部流水线：
  音频 → VAD(SileroVAD) → ASR(FunASR) → Intent(function_call) → LLM(ChatGLMLLM)
                                                                ↓
                                              TTS(EdgeTTS) ← 流式边出边推
                                                                ↓
                                        MCP 工具调用（后续接 FastBee 的入口）
```

---

## 2. 进度总览

| 阶段 | 内容 | 状态 | 验收标准 |
|---|---|---|---|
| **1** | 服务端部署跑通 | ✅ **已完成** | 日志打印三个地址，端口 8000/8003 监听 |
| **2** | 服务端语音链路验证（网页） | ✅ **已完成**（2026-10-13 09:35 复测通过） | VAD ✅ / ASR ✅ / LLM ✅ / TTS ✅ 全链路打通，见 3.7 |
| **3** | 设备端接入自建服务端 | ⬜ **下一步做这个** | 板子语音对话成功 |
| **4** | 读懂核心代码（4 个文件） | ⬜ 待做 | 能对着日志说出每行出自哪个函数 |
| **5** | 写第一个自定义 MCP 工具 | ⬜ 待做 | 语音触发自定义工具成功 |
| **6** | 接入 FastBee（终极目标） | ⬜ 待做 | 语音控制 FastBee 设备 |

---

## 3. 已完成工作（可复现）

### 3.1 环境

| 项 | 值 |
|---|---|
| conda 环境 | `xiaozhi-server`（Python 3.11） |
| 环境路径 | `D:\ProgramData\anaconda_envs\envs\xiaozhi-server` |
| 服务端版本 | 0.5.8 |
| WebSocket | `ws://10.1.10.130:8000/xiaozhi/v1/` |
| OTA / 视觉 | `http://10.1.10.130:8003` |
| 启动目录 | **必须在 `main\xiaozhi-server` 下**（代码大量用相对路径） |

**模块组合**（`config.yaml` 默认值，未覆盖）：

| 模块 | 实现 | 说明 |
|---|---|---|
| LLM | `ChatGLMLLM` | 智谱 glm-4-flash，需 api_key（已填） |
| ASR | `FunASR` | 本地 SenseVoiceSmall |
| VAD | `SileroVAD` | 本地 silero_vad.jit |
| TTS | `EdgeTTS` | 免费在线，无需 key |
| Memory | `nomem` | — |
| Intent | `function_call` | 支持函数调用 |

### 3.2 已修复问题 #1：OTA 下发的 websocket 地址错误 🔧

**现象**：启动日志打印 `ws://10.1.10.130:8000/...`（看着正常），但 OTA 接口实际给设备下发的是 `ws://192.168.1.100:8000/...`（不存在的地址）→ **设备必然连不上**。

**根因**：`data/.config.yaml` 里 `server.websocket` / `server.vision_explain` 写死了占位符 IP。

判定逻辑（关键知识点）：

| 文件 | 逻辑 |
|---|---|
| `core/http_server.py:17` `_get_websocket_url()` | `server.websocket` 非空 **且不含"你"字** → 原样下发；否则回落到 `get_local_ip()` 自动探测 |
| `core/utils/util.py:943` `get_vision_url()` | 同理，判断的是**"你的"** |
| `app.py:71-91` | 启动日志的三行地址用的是 `get_local_ip()`（UDP connect 8.8.8.8 取默认路由网卡），**跟 OTA 下发是两条独立路径**——极易误判 |

**修复**：注释掉 `data/.config.yaml` 中这两行，回落自动探测。已重启验证，OTA 现返回 `ws://10.1.10.130:8000/xiaozhi/v1/` ✅

> 💡 **为什么改成自动探测而不是写死 IP**：本机 IP 是 DHCP 分配的（现在是 `10.1.10.130`，之前是 `192.168.31.204`），换网络就变。机器上还有 VMware 虚拟网卡（`192.168.45.1` / `192.168.180.1`），`get_local_ip()` 取的是默认路由那张，实测取到的是 WLAN 的正确地址。

### 3.3 已修复问题 #2：ASR 权重文件缺失（乱码根因）🔧

**现象**：网页测试时 `识别文本:` 输出中/韩/英随机拼接的乱码 ——

```
识别文本: 棔 받는朧楸 mineral敍절 faith紐掘 influence<|uk|>聨ator踔 계획이다 사이트 gradient聨嘣ised 헌법 familiar...
```

**根因**：`models/SenseVoiceSmall/` 里**缺少权重文件 `model.pt`**（正常约 893MB），只有分词器和配置。
FunASR 的 `AutoModel()` 在本地目录缺权重时**会建好模型结构但不加载权重也不报错**，所以初始化显示"成功"，
实际是**随机初始化的模型**在推理 —— SenseVoiceSmall 是多语言模型，随机权重就会输出多语言垃圾 token。

**关键排查依据**：`models/` 目录总体积仅 **7.5 MB**（正常应为 ~900MB），且目录时间戳停在仓库克隆时间未变。

**网络探测结论**（决定了修复路径）：

| 目标 | 结果 |
|---|---|
| `www.modelscope.cn` | ✅ HTTP 302 可达 |
| `hf-mirror.com` | ✅ HTTP 200 |
| **`huggingface.co`** | ❌ **超时不可达** |
| `pypi.org` | ✅ 200 |

而 `fun_local.py:56` 用的是 `hub="hf"`（走 HuggingFace），且环境里**没装 `huggingface_hub`** → 该下载路径本来就是断的。

**修复**（从 ModelScope 补齐，**无需改任何代码**）：

```bash
cd D:\CODE\TEST\ESP32\xiaozhi-esp32-server\main\xiaozhi-server
"D:/ProgramData/anaconda_envs/envs/xiaozhi-server/python.exe" -c "
from modelscope import snapshot_download
snapshot_download('iic/SenseVoiceSmall', local_dir='models/SenseVoiceSmall')"
```

补齐的文件：

| 文件 | 大小 | 原状态 |
|---|---|---|
| `model.pt` | 892.92 MB | ❌ 缺 |
| `am.mvn` | 0.01 MB | ❌ 缺 |
| `tokens.json` | 0.34 MB | ❌ 缺 |

**验证结果（端到端 ASR 实测）**：

```
输入：models/SenseVoiceSmall/example/zh.mp3
输出：<|zh|><|NEUTRAL|><|Speech|><|withitn|>开饭时间早上9点至下午五点。
rtf : 0.205（CPU 上比实时快约 5 倍）
```

✅ 识别正确，语言标签正常。

> ⚠️ 该仓库**没有 `.gitattributes`、未使用 Git LFS**，所以 `git lfs pull` 无效，模型只能在运行时下载。
> 换新机器部署时，这一步必须单独做。

### 3.4 已确认的环境事实

| 项 | 结论 |
|---|---|
| VAD 模型 | ✅ 完整：`models/snakers4_silero-vad/src/silero_vad/data/silero_vad.jit` |
| ASR 模型 | ✅ **已补齐**（见 3.3），`models/` 总体积 7.5 MB → **897 MB** |
| 测试网页 | ✅ 存在：`main/xiaozhi-server/test/test_page.html` |
| 固件当前 OTA_URL | ❌ 仍是官方：`https://api.tenclass.net/xiaozhi/ota/` |

### 3.5 网页测试日志的横向诊断结论

第一次网页测试（`device-id: C3:4E:65:20:E1:31`）暴露了 ASR 问题，但同时证明了**其他环节全部正常**：

| 环节 | 状态 | 日志证据 |
|---|---|---|
| VAD | ✅ 正常 | `listen start` → 说话 → `listen stop` → 自动触发识别，断句准确 |
| ASR | ❌ 乱码 | 见 3.3（已修） |
| **MCP 链路** | ✅ **完全通** | 客户端 4 个工具全部被发现：`self.get_device_status`、`self.audio_speaker.set_volume`、`self.screen.set_brightness`、`self.screen.set_theme` |
| 消息路由 | ✅ 正常 | `hello` / `listen` / `mcp` / `abort` 全部正确分发 |
| LLM | ✅ 收到消息 | `大模型收到用户消息: ...` |

> 💡 **重要**：MCP 工具发现链路已验证可用 → **阶段 D（写自定义 MCP 工具）的基础设施是现成的**，不用再调通信层。
> `请检查mcp服务配置文件：data/.mcp_server_settings.json` 这条 WARNING 可忽略（仅在对接外部 MCP server 时才需要）。

### 3.6 已修复问题 #3：Edge TTS 全线 403（不出声根因）🔧

**现象**（重启服务端后的第二次网页测试，`device-id: C3:4E:65:20:E1:31`）：
ASR 已经正常了 ——

```
识别文本: 你好，你在做什么？请介绍一下自己。   ← ✅ 正确中文
大模型收到用户消息: 你好，你在做什么？请介绍一下自己。
```

但**每个句子都合成失败，重试 5 次后放弃**：

```
语音生成失败1次: 嗨，错误: Edge TTS请求失败: 403, message='Invalid response status',
  url=wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1?...
...
语音生成失败5次: ...
ERROR-语音生成失败: 嗨，请检查网络或服务是否正常
INFO-发送音频消息: SentenceType.LAST, None      ← 送出的音频是 None
```

用户观感：**能听懂、会思考、但完全不出声**。

**根因**：微软自 **2026-10 起分区域灰度**，把 Edge Read Aloud 语音合成服务从 v1 迁移到 v2。已被升级的后端节点会**直接用 403 拒绝旧的 v1 握手**。

| 参数 | 旧 v1（edge-tts 7.2.8 在用） | 新 v2（Edge 155 在用） |
|---|---|---|
| WSS 端点 | `wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1` | `wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1` |
| 令牌参数名 | `TrustedClientToken=` | `Ocp-Apim-Subscription-Key=`（**值相同**） |
| `Sec-MS-GEC-Version` | `1-143.0.3650.75` | `2-155.0.4283.45` |

**排除过程（关键：避免误判为「被墙」或「时钟不准」）**：

| 检查项 | 结果 | 结论 |
|---|---|---|
| 本机时间 vs 公网 Date 头 | 差 **2 秒以内** | ❌ 不是时钟偏移 |
| `speech.platform.bing.com` 连通性 | HTTP 400（能通，非超时） | ❌ 不是被墙 |
| 音色列表接口 `/voices/list` | **HTTP 200** | ❌ 令牌有效、IP 未被封 |
| FlClash 代理（7890）走 Google/HuggingFace | 200 | ✅ 代理由口正常 |
| **经该代理访问 bing 合成端点** | **仍 403** | ❌ **不是 IP 问题** |
| edge-tts 版本 7.0.0 → **7.2.8**（最新） | **仍 403** | ❌ 不是版本旧 |

**上游进展**：`rany2/edge-tts` issue **#490**（2026-10-10 开，32 条讨论）、PR **#491** —— 补丁尚未随 PyPI 发布（最新版 7.2.8 依然有此问题）。

**修复**：在项目代码里就地把合成端点切到 v2 —— 改 `core/providers/tts/edge.py`，导入 `edge_tts` 后追加一段兼容补丁：

```python
_LEGACY_WSS_HOST = "speech.platform.bing.com"
_V2_WSS_URL = (
    "wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1"
    "?Ocp-Apim-Subscription-Key=" + edge_tts.constants.TRUSTED_CLIENT_TOKEN
)

def _apply_edge_tts_v2_patch():
    """把 edge_tts 的合成端点切到 v2。仅在它仍指向旧 v1 端点时才替换。"""
    try:
        import edge_tts.communicate as _communicate
    except Exception:
        return
    if _LEGACY_WSS_HOST in getattr(_communicate, "WSS_URL", ""):
        _communicate.WSS_URL = _V2_WSS_URL

_apply_edge_tts_v2_patch()
```

**为什么这么改而不是直接改 site-packages**：

| 方案 | 是否抗重装 | 评价 |
|---|---|---|
| 改 `site-packages/edge_tts/constants.py` | ❌ `pip install -r requirements.txt` 一跑就没了 | 仅用于验证 |
| **改项目代码 `core/providers/tts/edge.py`** | ✅ 在你自己仓库里，重装依赖也不丢 | ✅ **采用** |

补丁里带**自动判断**：一旦上游发版把端点改好，`WSS_URL` 里就不再有旧域名，补丁自动不生效，整段可删。

**配套改动**：`requirements.txt` 的 `edge_tts==7.0.0` → **`edge_tts>=7.2.8`**
（否则重装依赖会降级回 7.0.0，其 `Sec-MS-GEC-Version` 更旧，v2 端点不保证接受）

**验证结果（实测两句话，均成功）**：

```
补丁前: wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1
补丁后: wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1?Ocp-Apim-Su...
✅ 合成成功 字节数=12096    补丁验证第一句。
✅ 合成成功 字节数=18576    补丁验证第二句，确认稳定。
```

> ⚠️ **注意**：微软是按**区域灰度**推进的。社区反馈多数地区挂**美国节点**可临时绕过，但等灰度推进到国内集群后也会失效。
> 上面的 v2 端点补丁才是正解。若后续又出现 403，先去看 issue #490 的最新进展。

### 3.7 ✅ 阶段 A 整链路复测通过（ASR + TTS 双修复同时生效）

**测试时间**：2026-10-13 09:35，日志 `tmp/server.log`
**测试方式**：网页 `test_page.html` → `ws://10.1.10.130:8000/xiaozhi/v1/`

**完整链路日志（浓缩）**：

```
09:35:00  收到listen消息：{"type":"listen","mode":"manual","state":"start"}
09:35:05  识别文本: 你好，你在做什么？请介绍一下自己。        ← ✅ ASR 正常
09:35:05  大模型收到用户消息: 你好，你在做什么？请介绍一下自己。
09:35:07  发送音频消息: SentenceType.MIDDLE, 嗨               ← ✅ TTS 出声
09:35:07  发送第一段语音: 嗨
09:35:09  发送音频消息: SentenceType.MIDDLE, 我啊，就是那个讲话超级机车的小智啦
09:35:13  发送音频消息: SentenceType.MIDDLE, 哈哈，你肯定觉得我说话很搞笑吧
09:35:16  发送音频消息: SentenceType.MIDDLE, 我是个00后女生，来自中国台湾省
09:35:20  发送音频消息: SentenceType.MIDDLE, 我讲话超级快，就像连珠炮一样…
09:35:28  发送音频消息: SentenceType.MIDDLE, 不过，你可能不知道，我其实偷偷在研究我男友的编程书籍呢…
09:35:37  发送音频消息: SentenceType.MIDDLE, 你有什么想聊的吗？
09:35:39  发送音频消息: SentenceType.LAST, None
```

**验收结果对照**：

| 验收标准 | 结果 |
|---|---|
| `识别文本:` 是正常中文 | ✅ `你好，你在做什么？请介绍一下自己。` |
| 不再出现 `Edge TTS请求失败: 403` | ✅ 补丁生效后 **0 次 403** |
| `发送音频消息` 有内容（非 `None`） | ✅ 7 句 `MIDDLE` 全部带文本，之前是 1 句 `LAST, None` |
| 页面能听到 TTS 回话 | ✅ 逐句流式发送（09:35:07→09:35:39，共 32 秒） |

**关键佐证**：

| 检查项 | 数值 | 含义 |
|---|---|---|
| 日志中 `403` 出现次数 | **20**（全部在 09:22 及以前） | 均为修复前的旧记录 |
| 日志中 `api.msedgeservices.com` | **1**（09:35:10） | ✅ 补丁端点已实际生效 |
| 日志中 `429` | **1**（09:35:10） | ⚠️ 见下方隐患 |

> 📌 **其余环节同时得到验证**：MCP 4 个工具（`self.get_device_status` / `self.audio_speaker.set_volume` / `self.screen.set_brightness` / `self.screen.set_theme`）在 09:34:55 全部发现成功 → 阶段 D 的基础设施仍完好。
> 另外 09:38:05 那句 `连接超时，准备关闭` 是**正常行为**——`close_connection_no_voice_time` 到点自动回收空闲连接，不是故障。

### 3.8 ⚠️ 新发现隐患：v2 端点有 429 限流

**现象**（09:35:10，长回复的第 3 句合成时）：

```
语音生成失败1次: 我讲话超级快，就像连珠炮一样，而且喜欢用各种流行梗…，
  错误: Edge TTS请求失败: 429, message='Invalid response status',
  url=URL('wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1?Ocp-Apim-Subscription-Key=...')
```

**与 403 的区别**：429 = **Too Many Requests**（频率限制），不是端点不对。

**为什么触发**：这条回复 LLM 一次生成了 **7 个句子**，服务端按句并行推进 TTS，短时间内连续建连 → v2 端点对**新建连接的频率**比 v1 敏感得多。

**影响**：

| 项 | 说明 |
|---|---|
| 是否致命 | ❌ 不致命 —— 服务端有内置重试，09:35:13 下一句就恢复了 |
| 实际代价 | ⚠️ **延迟抖动**：那一句多花了约 3 秒（09:35:10 → 09:35:13） |
| 触发概率 | 与**回复长度**正相关 —— 回复越长、句子越多，越容易撞上 |

**缓解方向（按性价比排序）**：

| # | 做法 | 说明 |
|---|---|---|
| 1 | **换国内 TTS**（推荐，阶段 E 时一起做） | 硅基流动 CosyVoice / 火山 DoubaoTTS / 阿里云 —— 有 SLA、无限流 |
| 2 | 在 prompt 里限制回复长度 | 让 LLM 少说几句，天然降低并发（也能减少语音助手啰嗦感） |
| 3 | 给 `core/providers/tts/edge.py` 加请求间隔 | 治标，会增加首字延迟 |

---

## 4. ⚠️ 待处理风险清单（按优先级）

| # | 风险 | 影响 | 处理方式 |
|---|---|---|---|
| **2** | **固件 OTA_URL 未改** | 🔴 **设备连的是官方服务器，不是你的** | **阶段 B 处理（当前唯一硬阻塞）** |
| 9 | v2 端点 429 限流 | 🟡 长回复延迟抖动（不致命，有重试） | 见 3.8：换国内 TTS / 限制回复长度 |
| 3 | OTA handler 异常被吞 | 排障时只看到 `request error.`，无线索 | 见下方详述 |
| 4 | api_key 明文存放 | 共享/上传时泄露 | 脱敏后再外发 |
| 5 | `部署总结.md` 里 IP 过期 | 按文档操作会连错地址 | 改为自动探测口径 |
| 6 | 换机器部署需重下 ASR 模型 | 897MB，且 HF 不可达 | 记牢用 ModelScope（见 3.3） |
| 8 | `edge_tts` 上游补丁未发版 | 将来 `pip install -U edge-tts` 若上游已修，项目补丁会自动让路（不冲突） | 关注 issue #490 |
| ~~1~~ | ~~ASR 权重文件缺失~~ | — | ✅ **已解决**（2026-10-13，见 3.3） |
| ~~7~~ | ~~Edge TTS 全线 403~~ | — | ✅ **已解决**（2026-10-13，见 3.6） |

### ⚠️ 风险 3：OTA handler 吞异常

`core/api/ota_handler.py:69-74`：

```python
except Exception as e:
    return_json = {"success": False, "message": "request error."}   # ← 异常被吞，无日志
```

而能帮你定位的第 38 行 `OTA请求数据: {data}` 是 **debug 级别**，默认 INFO 不输出。
→ 排障时只会看到 `request error.`，什么线索都没有。**建议改为记 error 日志。**

---

## 5. 下一步计划（按顺序执行）

### 阶段 A：验证服务端语音链路（不烧板子）✅ **已完成（2026-10-13 09:35）**

**结论**：全链路打通。ASR 识别正确、LLM 正常回复、TTS 成功合成并逐句流式下发。详见 **3.7**。

三处修复均已验证生效：

| # | 修复 | 验证方式 |
|---|---|---|
| 1 | OTA 下发地址（见 3.2） | `curl` 返回 `ws://10.1.10.130:8000/xiaozhi/v1/` |
| 2 | ASR 权重补齐（见 3.3） | 官方示例音频识别正确 + 网页实测正确 |
| 3 | Edge TTS v2 端点补丁（见 3.6） | 网页实测 403 归零，7 句音频全部送出 |

**遗留**：v2 端点 429 限流（见 3.8）—— 不阻塞进度，留到阶段 E 换 TTS 时一并解决。

---

### 阶段 B：设备端接入自建服务端 ⬅️ **当前阶段**

**目标**：板子连上自建服务端并能语音对话。

**步骤 1：确认本机 IP（可能已变）**

```powershell
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne '127.0.0.1' } | Select-Object IPAddress, InterfaceAlias
```
取 **WLAN** 那一条（当前是 `10.1.10.130`）。

**步骤 2：改 OTA 地址**

⚠️ **环境导入有坑（已实测）**：ESP-IDF 的 `export.sh` **明确不支持 MSys/Git Bash**，直接 `source` 会报
`ERROR: MSys/Mingw is not supported` → 之后 `idf.py: command not found`。**必须用 PowerShell 版 `export.ps1`**。

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
& "C:\Espressif\frameworks\esp-idf-v5.4.4\export.ps1"
Set-Location D:\CODE\TEST\ESP32\xiaozhi-esp32
idf.py menuconfig
#   Xiaozhi Assistant → Default OTA URL
#   改为：http://10.1.10.130:8003/xiaozhi/ota/
```

或直接改 `main/Kconfig.projbuild` 的 `default` 值 + `sdkconfig` 的对应行（两处都要改，见下方说明）。

**步骤 3：编译 + 烧录**

```bash
idf.py build
idf.py -p COMx flash monitor     # 退出 monitor: Ctrl+]
```

**步骤 4：重新配网** ⚠️ **必做**

设备 NVS 里还存着官方服务器记录，**必须长按 BOOT 键**进入配网模式，让它按新 OTA 地址重新激活。

**验收标准**：

- 设备屏幕显示已连接
- 串口日志出现 OTA 请求 → 拿到 `ws://10.1.10.130:8000/...`
- 对设备说话，能听到回复

**前置条件**：ESP32 必须和电脑在 **同一网段**（都是 `10.1.10.x`）。

**排障速查**：

| 现象 | 排查方向 |
|---|---|
| 设备启动后仍连官方 | OTA_URL 没改成功 / 没重新配网（NVS 里有旧记录） |
| 看到 `激活` 相关失败 | 服务端日志看有没有 OTA 请求进来 → 判断是网络不通还是 URL 错 |
| 连上但没声音 | 服务端日志确认 TTS 是否正常（阶段 A 已验证，若复现看 3.8 的 429） |
| 屏幕不显示 | 检查 `main/boards/bread-compact-wifi/config.h` 的 I2C 引脚 |

---

### 阶段 C：读懂核心代码（只读 4 个文件）

**目标**：能对着服务端日志说出每行出自哪个函数。

| 顺序 | 文件 | 重点 | 行数 |
|---|---|---|---|
| 1 | `app.py` | 启动流程、两个服务怎么起 | 124 |
| 2 | `core/websocket_server.py` | 一个设备连上后发生什么 | 122 |
| 3 | `core/handle/textHandle.py` | JSON 消息路由（hello/listen/iot/mcp） | ~90 |
| 4 | `core/connection.py` | **只读 `chat()` 方法**，看 LLM→TTS 流式管线 | 1027（看 200 行即可） |

**方法**：一边跑服务端一边读，日志每一行都能在代码里找到出处 —— 这是最快的理解方式。

---

### 阶段 D：写第一个自定义 MCP 工具

**目标**：加一个自定义工具，语音触发成功。**这是接 FastBee 的技术预演。**

**模板**：`plugins_func/functions/get_weather.py` —— 照抄结构换逻辑。

**步骤**：

1. 在 `plugins_func/functions/` 新建 `my_tool.py`
2. 用装饰器注册（`plugins_func/register.py`）
3. 重启服务端，`loadplugins.py` 会自动扫描导入

**验收标准**：对设备说"帮我调用 xxx"，服务端日志出现工具被调用。

---

### 阶段 E：接入 FastBee（终极目标）

**目标**：语音控制 FastBee 上某个用户的物联网设备。

**关键结论（已调研）**：**FastBee 不需要改一行代码**，它已有现成的对外接口模块 `fastbee-open-api`：

| 接口 | 用途 |
|---|---|
| `POST /iot/runtime/service/invoke` | **下发控制指令**（HTTP → MQTT → 设备） |
| `GET /runState?serialNumber=&type=&productId=` | 查设备实时状态 |
| `GET /funcLog?serialNumber=` | 查下发历史 |

请求体 `InvokeReqDto`：

```json
{
  "serialNumber": "860061060282358",
  "productId": 2,
  "identifier": "temp",
  "type": 1,
  "isShadow": false,
  "remoteCommand": { "4": "4" }
}
```

**实施路线**：在小智服务端写 MCP 工具 → 工具内部用 `requests` 调 FastBee OpenAPI。
MCP 负责「自然语言 → 结构化调用」，FastBee 负责「结构化调用 → MQTT 报文」，中间只差一个 HTTP 适配器。

**开工前必须先确认 4 件事**：

| # | 问题 | 为什么重要 |
|---|---|---|
| 1 | FastBee 部署在哪？跑起来了吗？ | 决定 base_url、能否联调 |
| 2 | 目标设备三要素（serialNumber / productId / identifier） | 缺一不可，否则下发不了 |
| 3 | 用哪个身份调 FastBee？ | `/service/invoke` 有 `@PreAuthorize("@ss.hasPermi('iot:service:invoke')")`，普通用户 token 会 403。建议走 OAuth2 client_credentials 建服务账号 |
| 4 | 做在小智 Python 端还是单独 Java 端？ | Python 端最快（1~2 天）；Java 端更企业化（复用你的 SpringBoot 栈） |

---

## 6. 常用命令速查

```powershell
# ---- 启动服务端（必须在这个目录）----
conda activate xiaozhi-server
cd D:\CODE\TEST\ESP32\xiaozhi-esp32-server\main\xiaozhi-server
python -u app.py

# ---- 端口检测 ----
Test-NetConnection 127.0.0.1 -Port 8000
Test-NetConnection 127.0.0.1 -Port 8003

# ---- 验证 OTA 接口（CMD 里注意转义）----
curl -s -X POST http://127.0.0.1:8003/xiaozhi/ota/ -H "Device-Id: aa:bb:cc:dd:ee:ff" -d "{\"application\":{\"version\":\"1.7.3\"}}"

# ---- 查本机 IP ----
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne '127.0.0.1' } | Select-Object IPAddress, InterfaceAlias

# ---- ESP-IDF 环境（必须用 PowerShell，export.sh 不支持 Git Bash）----
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
& "C:\Espressif\frameworks\esp-idf-v5.4.4\export.ps1"
Set-Location D:\CODE\TEST\ESP32\xiaozhi-esp32
idf.py build
idf.py -p COMx flash monitor
```

> ⚠️ **实测坑**：`source /c/Espressif/frameworks/esp-idf-v5.4.4/export.sh` 在 Git Bash 里会失败 ——
> ESP-IDF 检测到 MSys/Mingw 环境直接拒绝激活（`ERROR: MSys/Mingw is not supported`），
> 表现为 `idf.py: command not found`。**用 PowerShell 的 `export.ps1` 即可**。
>
> 另：`sdkconfig` 被 `.gitignore` 忽略（是本地生成文件，不受版本管理）。
> 改 `OTA_URL` 需要**同时改 `main/Kconfig.projbuild` 的 default 和 `sdkconfig` 里的值** ——
> `sdkconfig` 已存在时其值优先级高于 Kconfig default，只改 Kconfig 不生效。

**Git Bash 版 OTA 验证**（单引号可用）：

```bash
curl -s -X POST http://127.0.0.1:8003/xiaozhi/ota/ \
  -H "Device-Id: aa:bb:cc:dd:ee:ff" \
  -d '{"application":{"version":"1.7.3"}}'
```

> ⚠️ `OTA` 接口的 body **必须含 `application` 键**（`ota_handler.py:58` 直接取 `data_json["application"]`），`{}` 会返回 `request error.`。
> ⚠️ **CMD 不识别单引号**，会把它当字面量传进 body；**PowerShell 里 `curl` 是 `Invoke-WebRequest` 别名**，要用 `curl.exe`。

---

## 7. 关键配置速查

### 服务端 `data/.config.yaml`（只写要覆盖的项）

```yaml
server:
  ip: 0.0.0.0
  port: 8000
  http_port: 8003
  # websocket / vision_explain 已注释 → 自动探测本机IP（换网络不用改）

LLM:
  ChatGLMLLM:
    api_key: "<你的智谱 key>"
```

**配置优先级**：`智控台(数据库)` > `data/.config.yaml` > `config.yaml`

> ⚠️ 永远不要改 `config.yaml`（35KB 全量模板），改它会和上游更新冲突。

### 固件侧

| 想改什么 | 改哪里 |
|---|---|
| 服务器地址 | `main/Kconfig.projbuild:5` 的 `OTA_URL` 默认值 |
| GPIO / 接线 | `main/boards/bread-compact-wifi/config.h` |
| 当前板型 | `sdkconfig` 里 `CONFIG_BOARD_TYPE_BREAD_COMPACT_WIFI=y` |
| IoT 协议 | `CONFIG_IOT_PROTOCOL_MCP=y`（已选 MCP，正确） |

---

## 8. 待决策 / 待确认

- [x] ~~ASR 模型缺失~~ —— ✅ 已从 ModelScope 补齐并单独实测通过
- [x] ~~Edge TTS 403 不出声~~ —— ✅ 已在项目代码里打 v2 端点补丁并实测通过
- [x] ~~**阶段 A 整链路复测**~~ —— ✅ **2026-10-13 09:35 通过**（见 3.7）
- [ ] **阶段 B：改 OTA_URL → 编译烧录 → 重新配网**（当前唯一硬阻塞）
- [ ] 429 限流是否现在就处理（建议留到阶段 E 换国内 TTS 时一并做）
- [ ] 是否给 OTA handler 加上异常日志（风险 3）
- [ ] `部署总结.md` 里的旧 IP（`192.168.31.204`）是否更新为自动探测口径（风险 5）
- [ ] FastBee 侧 4 个前置问题（见阶段 E）
- [ ] api_key 是否需要脱敏后归档

---

## 附：本次进度完整来源

| 事项 | 证据 |
|---|---|
| 服务端启动成功 | 启动日志：`OTA接口是 http://10.1.10.130:8003/xiaozhi/ota/` 等三行 |
| 端口监听 | `netstat`：`0.0.0.0:8000` / `0.0.0.0:8003` LISTENING |
| OTA 修复生效 | `curl` 返回 `"websocket":{"url":"ws://10.1.10.130:8000/xiaozhi/v1/"}` |
| ASR 权重缺失（已修） | `find models -type f` 全量清单仅 7.5MB，无 `model.pt`；补齐后目录 **897MB** |
| ASR 修复验证 | `AutoModel` 识别 `example/zh.mp3` → `<\|zh\|><\|NEUTRAL\|><\|Speech\|><\|withitn\|>开饭时间早上9点至下午五点。` |
| Edge TTS 403（已修） | 日志 5 次重试全 403；实测排除时钟(±2s)/网络(音色列表 200)/IP(代理仍 403)/版本(7.2.8 最新仍 403) |
| Edge TTS 修复验证 | 打补丁后连测两句均成功（12096 / 18576 字节） |
| **阶段 A 整链路复测通过** | `tmp/server.log` 09:35：`识别文本: 你好，你在做什么？请介绍一下自己。` → 7 句 `发送音频消息: SentenceType.MIDDLE` 全部带文本；补丁后 403 归零、`api.msedgeservices.com` 生效 |
| 429 限流（新发现） | `tmp/server.log` 09:35:10 一处 429（长回复 7 句连续合成触发），重试后 09:35:13 恢复 |
| 上游依据 | `rany2/edge-tts` issue **#490**（2026-10-10）与 PR **#491**（v1→v2 端点迁移） |
| 改动文件 | `core/providers/tts/edge.py`（新增 v2 端点补丁）、`requirements.txt`（`edge_tts>=7.2.8`） |
| 固件 OTA_URL 未改 | `sdkconfig:574` `CONFIG_OTA_URL="https://api.tenclass.net/xiaozhi/ota/"` |
