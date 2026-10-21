# xiaozhi-esp32-server 本地部署完整总结

> 记录时间：2026-09-23
> 项目路径：`D:\CODE\TEST\ESP32\xiaozhi-esp32-server`
> 服务端运行环境：Windows + conda（Python 3.11）

---

## 一、整体架构

```
ESP32 设备 (xiaozhi 固件, 如 bread-compact-wifi)
        │  ws://192.168.31.204:8000/xiaozhi/v1/
        ▼
xiaozhi-server (Python 服务端, 本机 192.168.31.204)
   ├─ WebSocket 服务 :8000     → 与设备通信主通道
   ├─ HTTP 服务      :8003     → OTA / 视觉分析接口
   ├─ LLM:  ChatGLMLLM (智谱 glm-4-flash, 需 api_key)
   ├─ ASR:  FunASR (本地 SenseVoiceSmall 模型)
   ├─ VAD:  SileroVAD (本地模型)
   ├─ TTS:  EdgeTTS (免费在线)
   └─ Memory: nomem / Intent: function_call
```

---

## 二、环境要求

| 项 | 要求 |
|----|------|
| Python | **3.8 ~ 3.11**（本项目实际用 **3.11**） |
| 依赖 | 见 `main/xiaozhi-server/requirements.txt` |
| 原生库 | **libopus**（Opus 编解码）、**ffmpeg** |
| 本地模型 | `models/SenseVoiceSmall`、`models/snakers4_silero-vad`（已在仓库内） |

> ⚠️ 关键坑：**Python 3.12+ 无法安装 torch 2.2.2 / numpy 1.26.4 / websockets 14.2**。
> 你的 conda base 是 Python 3.14，必须单独建 3.11 环境，不能直接用 base。

---

## 三、完整安装步骤（复现用）

### 1. 创建 Python 3.11 环境

```powershell
conda create -y -n xiaozhi-server python=3.11
conda activate xiaozhi-server
```

### 2. 安装 requirements 依赖

```powershell
cd D:\CODE\TEST\ESP32\xiaozhi-esp32-server\main\xiaozhi-server
pip install -r requirements.txt
```

> ⚠️ 已修正一处版本号（重要）：
> 原文件 `sherpa_onnx==1.12.0` **在 PyPI 上不存在**（1.12 系列从 1.12.26 开始），
> 已改为 `sherpa_onnx==1.12.40`。
> 若重新拉取仓库代码需留意此改动，否则安装会报 "No matching distribution found"。

### 3. 安装原生库 libopus（Opus 编码）

```powershell
conda install -y -n xiaozhi-server --override-channels -c conda-forge libopus
```

> `pip` 不装原生库，`opuslib_next` 需要 `opus.dll`。
> ⚠️ 注意包名是 **`libopus`**，不是 `opus`（`opus` 在镜像通道查不到）。
> 装好后 dll 位于 `D:\ProgramData\anaconda_envs\envs\xiaozhi-server\Library\bin\opus.dll`，
> `conda activate` 后会自动加入 PATH，无需额外操作。
> （另在 `main\xiaozhi-server\` 下也留了一份 `opus.dll` 作兜底，可保留。）

### 4. 安装 ffmpeg（pydub 需要）

```powershell
conda install -y -n xiaozhi-server --override-channels -c conda-forge ffmpeg
```

> 消除启动时 `Couldn't find ffmpeg` 的 RuntimeWarning。

---

## 四、配置服务端

### 1. 创建配置文件

代码要求存在 `main/xiaozhi-server/data/.config.yaml`（`data` 目录默认不存在，需自建）。

```powershell
cd D:\CODE\TEST\ESP32\xiaozhi-esp32-server\main\xiaozhi-server
# 手动创建 data 目录，在其中新建 .config.yaml
```

`.config.yaml` 采用"增量覆盖"机制：**只写你要改的项**，其余自动读取 `config.yaml` 默认值（不用整份复制）。

### 2. 最小配置内容（当前生效）

```yaml
# ============ 本地运行最小配置 ============
server:
  ip: 0.0.0.0
  port: 8000
  http_port: 8003
  websocket: "ws://192.168.31.204:8000/xiaozhi/v1/"
  vision_explain: "http://192.168.31.204:8003/mcp/vision/explain"

LLM:
  ChatGLMLLM:
    api_key: "在此填入你的智谱api_key"   # ← 必须改成真实 key
```

> 🔑 **必须**：填入智谱开放平台的 api_key（免费 glm-4-flash）。
> 申请地址：https://bigmodel.cn/usercenter/proj-mgmt/apikeys
> 不填 key 时服务能启动，但设备对话会失败。

### 3. 关键说明

- 默认模块组合（`config.yaml`）：`LLM=ChatGLMLLM`、`ASR=FunASR`、`VAD=SileroVAD`、`TTS=EdgeTTS`、`Memory=nomem`、`Intent=function_call`
- `ChatGLMLLM` 的 `type: openai` → 走智谱的 OpenAI 兼容接口，provider 目录是 `core/providers/llm/openai/`
- 若想换大模型：可用 `DoubaoLLM`（豆包）、`DeepSeekLLM`、`OllamaLLM`（本地）等，在 `.config.yaml` 里加对应配置并把 `selected_module.LLM` 改掉

---

## 五、启动服务端

```powershell
conda activate xiaozhi-server
cd D:\CODE\TEST\ESP32\xiaozhi-esp32-server\main\xiaozhi-server   # ← 必须在 main\xiaozhi-server 子目录下！
python -u app.py
```

> ⚠️ **必须在 `main\xiaozhi-server` 目录下启动**（不是 server 根目录）。
> 代码大量使用相对路径（`core/...`、`models/...`、`data/...`），在根目录启动会报
> `ValueError: 不支持的LLM类型: openai` 之类的错。
> `app.py` 不需要加引号。

---

## 六、验证服务是否启动成功

### 成功标志（日志末尾）

```
初始化组件: llm成功 ChatGLMLLM
初始化组件: asr成功 FunASR
...
Websocket地址是    ws://192.168.31.204:8000/xiaozhi/v1/
=======上面的地址是websocket协议地址，请勿用浏览器访问=======
```

- 终端**一直挂着不退**（不再出现 `PS>` 提示符）= 服务在运行。
- 若打印出 `Websocket地址` 等三行地址信息 = 启动成功。

### 端口检测（另开一个终端）

```powershell
Test-NetConnection 127.0.0.1 -Port 8000
# TcpTestSucceeded : True  → 服务在监听
```

### 用测试网页验证（推荐）

浏览器打开 `main/xiaozhi-server/test/test_page.html`（日志里也有提示），
页面会连上 WebSocket 并与服务端交互；连接成功后服务端日志出现
`127.0.0.1 conn - ... device-id: ... client-id: web_test_client` 即为连接成功。

### 真实设备对接

- ESP32 固件需要把服务器地址配成 `ws://192.168.31.204:8000/xiaozhi/v1/`
- 固件与电脑需在同一局域网（本机 IP `192.168.31.204`，若变动需同步改 `.config.yaml`）

---

## 七、本次排障问题速查表

| # | 报错 | 原因 | 解决 |
|---|------|------|------|
| 1 | `No module named 'aioconsole'` | 缺依赖 | `pip install -r requirements.txt` |
| 2 | `torch==2.2.2 No matching distribution` | Python 3.14 太新 | 建 Python 3.11 环境 |
| 3 | `websockets==14.2` 装不上 | Python 3.8 太旧（需≥3.9） | 用 Python 3.9~3.11 |
| 4 | `sherpa_onnx==1.12.0` 找不到 | 版本号在 PyPI 不存在 | 改为 `==1.12.40` |
| 5 | `Could not find Opus library` | 缺 opus.dll | `conda install libopus` |
| 6 | `Couldn't find ffmpeg`（警告） | 缺 ffmpeg | `conda install ffmpeg` |
| 7 | `找不到data/.config.yaml文件` | 没建配置 | 创建 `data/.config.yaml` |
| 8 | `ValueError: 不支持的LLM类型: openai` | 启动目录不对 | 在 `main\xiaozhi-server` 下启动 |

---

## 八、环境与版本信息快照

| 项 | 值 |
|----|-----|
| conda 环境 | `xiaozhi-server` (Python 3.11) |
| 环境路径 | `D:\ProgramData\anaconda_envs\envs\xiaozhi-server` |
| torch | 2.2.2 (cpu) |
| websockets | 14.2 |
| numpy | 1.26.4 |
| loguru | 0.7.3 |
| sherpa_onnx | 1.12.40 |
| ffmpeg | 7.1.0 (conda-forge) |
| libopus | 1.6.1 |
| 服务端版本 | 0.5.8 |
| 服务端 IP | 192.168.31.204 |
| WebSocket | ws://192.168.31.204:8000/xiaozhi/v1/ |
| HTTP (OTA/视觉) | http://192.168.31.204:8003 |
