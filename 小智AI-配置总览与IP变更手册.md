# 小智 AI 自建服务端 — 配置总览与 IP 变更手册

> 整理时间：2026-10-13
> 硬件：ESP32-S3 面包板 WiFi 版（`CONFIG_BOARD_TYPE_BREAD_COMPACT_WIFI`，设备 MAC `a0:85:e3:e6:53:a4`）
> 当前电脑 WLAN IP：**`10.1.10.130`**（SSID `MM Intelligence_5G 4`；设备连的是 `启明`）
> 本文是「换网络/换 IP 时照着改」的操作手册，配套文档：`小智AI-学习进度与下一步计划.md`

---

## 0. TL;DR —— 换 WiFi / IP 变了要做的事

| 场景 | 要做的事 | 工作量 |
|---|---|---|
| **只换 WiFi，电脑 IP 不变** | 设备长按 BOOT 重新配网，**不用重编译** | 2 分钟 |
| **电脑 IP 也变了** | 改 2 个文件 → **重新编译 → 烧录** → 重新配网 | 20~30 分钟 |
| **想彻底免除后患** | 在路由器上给电脑 WLAN 网卡做 **DHCP 静态绑定** | 5 分钟，一劳永逸 ✅ |

**只有 1 处是"硬编码进固件、必须重编译"的：设备端 `OTA_URL`。** 服务端侧因为用的是自动探测，基本不用动。详见第 5 章。

---

## 1. 系统全景

### 1.1 五个组件 / 端口 / 启动方式

| 组件 | 路径 | 端口 | 技术栈 | 启动方式 |
|---|---|---|---|---|
| **xiaozhi-server** | `main/xiaozhi-server` | **8000**(WS) / **8003**(HTTP) | Python asyncio | 命令行（见 3.4） |
| **manager-api** | `main/manager-api` | **8002**（前缀 `/xiaozhi`） | Spring Boot 3.4.3 + **JDK 21** | IntelliJ IDEA 跑 `AdminApplication` |
| **manager-web**（智控台界面） | `main/manager-web` | **8001** | Vue 2 + vue-cli | `npm run serve` |
| **MySQL 5.7** | `C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe` | **3306** | 库名 `xiaozhi_esp32_server` | Windows 服务 |
| **Redis 5.0** | `D:\Java\redis\Redis-x64-5.0.14.1` | **6379** | 存验证码 / 配置缓存 | `redis-server.exe` |

> 注意：本机 **MySQL 8.0 在 3307**，5.7 在 3306。项目配置连的是 **3306（5.7）**，别搞混实例。

### 1.2 一次完整对话的数据流

```
ESP32 ──① POST http://<电脑IP>:8003/xiaozhi/ota/ ──▶ xiaozhi-server(:8003)
      ◀── 返回 {"websocket":{"url":"ws://<电脑IP>:8000/xiaozhi/v1/"}}
        │
      ──② WebSocket ws://<电脑IP>:8000/xiaozhi/v1/ ─▶ xiaozhi-server(:8000)
        │                                              │
        │                                              ├─ ③ POST /xiaozhi/config/agent-models
        │                                              │      （带 Bearer server.secret）
        │                                              ▼
        │                                        manager-api(:8002) ──▶ MySQL(ai_device)
        │                                              │
        │  ◀── ④ 下发该设备的 ASR/LLM/TTS/Prompt 配置 ──┘
        │
      ──⑤ 语音流（Opus 60ms）──▶ VAD → ASR → LLM → TTS ──▶ 音频回传
```

### 1.3 关键身份标识

| 项 | 值 |
|---|---|
| 设备 MAC | `a0:85:e3:e6:53:a4` |
| 设备 client-id | `4a9e1bf4-a9be-4ee2-b9a7-cb1662c8cbc6` |
| 设备串口 | **COM31** @ 115200 |
| `manager-api.secret` | 见智控台【参数管理】`server.secret`（存于 MySQL `sys_params` 表） |
| 智能体 | 智控台里自建（示例 `TEST001`） |

---

## 2. 环境与路径速查

| 依赖 | 路径 / 版本 | 备注 |
|---|---|---|
| ESP-IDF | `C:\Espressif\frameworks\esp-idf-v5.4.4`（v5.4.4） | **必须用 PowerShell 的 `export.ps1`**，`export.sh` 在 Git Bash 里不可用 |
| Python 服务端环境 | conda env `xiaozhi-server`<br>`D:\ProgramData\anaconda_envs\envs\xiaozhi-server\python.exe` | |
| JDK 21 | `D:\Java\jdk21`（21.0.12 LTS） | manager-api 必须用 21；**全局 `JAVA_HOME` 仍是 jdk1.8**，IDEA 里单独配 |
| Maven | `D:\Java\mvn\apache-maven-3.9.11` | |
| Node / npm | v22.22.2 / 10.9.7 | `.npmrc` 已配 npmmirror |
| MySQL | root / **root** @ 127.0.0.1:3306 | 库 `xiaozhi_esp32_server`，utf8mb4 |
| Redis | 127.0.0.1:6379，无密码 | |

---

## 3. 今天（2026-10-13）的配置步骤复盘

### 3.1 服务端 Python（`main/xiaozhi-server`）

1. **配置文件 `data/.config.yaml`**（注意真正的运行时目录是 `main/xiaozhi-server/data/`，不是仓库根目录那个空的 `data/`）：
   - `server` 段：`websocket` / `vision_explain` **保持注释**（留空 → 服务端用 `get_local_ip()` 自动探测本机 IP 下发）
   - 新增 `manager-api` 段，把配置来源切到智控台数据库：
     ```yaml
     manager-api:
       url: http://127.0.0.1:8002/xiaozhi
       secret: "<智控台 sys_params 表里的 server.secret>"
     ```
2. **依赖与代码补丁**：见第 4 章。

### 3.2 智控台（manager-api / manager-web）

1. 建库（只需一次）：`CREATE DATABASE xiaozhi_esp32_server CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;`
2. 改 `main/manager-api/src/main/resources/application-dev.yml` 的数据源账号密码（当前 `root/root`）。
3. **不用手工导 SQL**：项目带 Liquibase，首次启动自动建 **18 张表**（含 `DATABASECHANGELOG`）并灌种子数据，同时随机生成 `server.secret`。
4. 用 **JDK 21** 启动 `manager-api`（IDEA 跑 `AdminApplication`）→ 访问 `http://127.0.0.1:8002/xiaozhi/doc.html` 验证。
5. 启动 `manager-web`：`cd main/manager-web` → `npm install`（首次）→ `npm run serve` → 浏览器开 **`http://127.0.0.1:8001`**，**注册的第一个账号即超级管理员**。

### 3.3 设备端固件（`xiaozhi-esp32`）

把 OTA 地址指向自建服务端（**这是唯一写进固件、必须重编译的配置**）：

| 文件 | 行 | 值 |
|---|---|---|
| `main/Kconfig.projbuild` | 7 | `default "http://10.1.10.130:8003/xiaozhi/ota/"` |
| `sdkconfig` | 574 | `CONFIG_OTA_URL="http://10.1.10.130:8003/xiaozhi/ota/"` |

### 3.4 启动顺序（4 个进程都要活着）

```
① MySQL(3306)  →  ② Redis(6379)  →  ③ manager-api(8002)  →  ④ manager-web(8001)
                                          ↓
                                  ⑤ xiaozhi-server(8000/8003)
```

```powershell
# ⑤ Python 服务端（必须在 main/xiaozhi-server 目录下启动，否则找不到 data/.config.yaml）
cd D:\CODE\TEST\ESP32\xiaozhi-esp32-server\main\xiaozhi-server
D:\ProgramData\anaconda_envs\envs\xiaozhi-server\python.exe -u app.py 2>&1 | tee tmp\server.log

# ④ 智控台界面
cd D:\CODE\TEST\ESP32\xiaozhi-esp32-server\main\manager-web
npm run serve

# ③ manager-api：IDEA 里运行 AdminApplication
# ② Redis
D:\Java\redis\Redis-x64-5.0.14.1\redis-server.exe
```

### 3.5 验收命令

```powershell
# 服务端启动成功的标志
#   日志出现「从API读取配置」+「Websocket地址是 ws://10.1.10.130:8000/xiaozhi/v1/」

# OTA 下发地址是否正常（返回的 websocket.url 不能为空）
curl.exe -s -X POST "http://10.1.10.130:8003/xiaozhi/ota/" `
  -H "Content-Type: application/json" -H "Device-Id: a0:85:e3:e6:53:a4" `
  -d '{"application":{"version":"1.7.3"},"board":{"type":"bread-compact-wifi"},"mac_address":"a0:85:e3:e6:53:a4"}'

# 设备是否连上服务端
Get-NetTCPConnection -State Established | Where-Object { $_.LocalPort -in 8000,8003 }
```

---

## 4. 本次全部改动清单（升级依赖前先确认是否已合入上游）

### 4.1 服务端 Python

| 文件 | 改动 | 原因 |
|---|---|---|
| `data/.config.yaml` | `websocket`/`vision_explain` 注释掉；新增 `manager-api` 段 | 走自动探测 + 接入智控台 |
| `core/providers/tts/edge.py` | 导入时替换 `edge_tts.communicate.WSS_URL` 为 v2 端点 | 微软 Edge TTS v1→v2 迁移，否则全线 403 |
| `requirements.txt` | `edge_tts==7.0.0` → `>=7.2.8` | 同上 |
| `core/api/ota_handler.py` | ① `except` 里补 `logger.error`；② `_get_websocket_url` 空值兜底 | ① 原来静默吞异常；② 见 5.1 根因 |
| `config/config_loader.py` | `get_config_from_api()` 的 `server` 段补透传 `websocket` + `timezone_offset` | 智控台模式**不合并 config.yaml**，原实现漏传这两项 → OTA 下发空 URL |
| `core/http_server.py` | 同上加空值判断，判定串与 ota_handler 统一为 `"你的"` | 一处判定是 `"你"`、一处是 `"你的"`，不一致 |

### 4.2 设备端

| 文件 | 改动 |
|---|---|
| `main/Kconfig.projbuild` | `OTA_URL` default → 自建服务端地址 |
| `sdkconfig` | `CONFIG_OTA_URL` 同步 |

### 4.3 智控台侧

| 项 | 改动 |
|---|---|
| `manager-api/.../application-dev.yml` | 数据源账号密码 |
| MySQL | 新建库 `xiaozhi_esp32_server`（表由 Liquibase 自动建） |
| 环境 | 安装 JDK 21 |

---

## 5. ⭐ IP 变更操作手册（核心）

### 5.1 先搞清楚：IP 到底出现在哪些地方

| # | 位置 | 当前值 | 换 IP 要不要改 | 说明 |
|---|---|---|---|---|
| 1 | 设备端 `main/Kconfig.projbuild:7` | `http://10.1.10.130:8003/xiaozhi/ota/` | ✅ **必须改 + 重编译烧录** | 编译期写死进固件 |
| 2 | 设备端 `sdkconfig:574` `CONFIG_OTA_URL` | 同上 | ✅ 必须改 | 与 1 保持一致 |
| 3 | 服务端 `data/.config.yaml` 的 `server.websocket` / `vision_explain` | **注释状态（空）** | ❌ 不用改 | 留空时服务端用 `get_local_ip()` 自动探测并下发，换网自动适配 |
| 4 | 服务端 `data/.config.yaml` 的 `manager-api.url` | `http://127.0.0.1:8002/xiaozhi` | ❌ 不用改 | 本机回环 |
| 5 | 智控台 `manager-web/vue.config.js` 代理 | `127.0.0.1:8002` | ❌ 不用改 | 本机回环 |
| 6 | MySQL / Redis 连接串 | `127.0.0.1` | ❌ 不用改 | 本机回环 |
| 7 | 智控台 DB `sys_params` 的 `server.ota` / `server.websocket` | 都是 `null` | ❌ 不用改 | 这是 **Docker 版由 manager-api 提供 OTA** 时才用的；我们设备 OTA 走 Python 8003，不读这两项 |
| 8 | 设备 NVS 里保存的 WiFi SSID/密码 | `启明` | ✅ 换 WiFi 时必须重新配网 | 长按 BOOT 进配网 AP |

> **结论：真正要改的只有设备端那 2 行 + 重新配网。** 服务端之所以不用改，就是因为当初把 `websocket` 留空改成自动探测 —— 这是今天做的最值的一个决定。

### 5.2 三种场景分别怎么做

#### 场景 A：只换 WiFi，但电脑 IP 不变

**什么都不用改代码/固件**，只要让设备连上新 WiFi：

1. 长按开发板 **BOOT 键**（进配网 AP 模式，串口会打印 `WifiConfigurationAp`）
2. 手机/电脑连该 AP，打开配网网页，填新 WiFi 的 SSID + 密码，点**完成**（会触发 `POST /reboot` → 设备重启）
3. 设备重启后以 STA 模式连新 WiFi → 请求 OTA → 连 WS
4. 验证：串口看到 `WS: Connected to websocket server`，服务端日志出现该设备 `conn - Headers: {...'device-id': 'a0:85:...'}`

> ⚠️ 前提：新 WiFi 必须和电脑**同网段且能互通**（比如都连同一个路由器）。设备连的是"启明"，电脑连的是 `MM Intelligence_5G 4`，当前都在 `10.1.10.0/24` —— **这两个必须是同一台路由器/同一局域网**。

#### 场景 B：电脑 IP 也变了（比如换了路由器、换了网络）

**必须重编译固件**，因为 OTA 地址写死在固件里：

```powershell
# ---- 第 1 步：查电脑新 IP（选 WLAN 那块网卡的 IPv4）----
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' } | Select-Object IPAddress,InterfaceAlias

# ---- 第 2 步：改 2 个文件（把 10.1.10.130 替换成新 IP）----
#   D:\CODE\TEST\ESP32\xiaozhi-esp32\main\Kconfig.projbuild   第 7 行
#   D:\CODE\TEST\ESP32\xiaozhi-esp32\sdkconfig                第 574 行
#   （注意：Kconfig 那行的 default 必须顶格写，前面不能有空格）

# ---- 第 3 步：编译（必须 PowerShell，不能用 Git Bash）----
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
& "C:\Espressif\frameworks\esp-idf-v5.4.4\export.ps1"
Set-Location D:\CODE\TEST\ESP32\xiaozhi-esp32
idf.py build

# ---- 第 4 步：验证新地址真的进固件了（必须只剩新 IP，不能有 api.tenclass.net）----
cd D:\CODE\TEST\ESP32\xiaozhi-esp32
strings build/xiaozhi.bin | Select-String -Pattern "ota|tenclass"

# ---- 第 5 步：烧录 + 监视（先关掉占用 COM31 的串口工具！）----
idf.py -p COM31 flash monitor

# ---- 第 6 步：长按 BOOT 重新配网（同场景 A）----
```

**编译前必查**：`Get-Process ninja,ccache -ErrorAction SilentlyContinue`
同一 build 目录**严禁并发编译**，否则会报 `xxx.obj.d: Permission denied`（那个报错的真因就是两个 ninja 抢写，不是权限问题）。

#### 场景 C（推荐）：一劳永逸 —— 路由器 DHCP 静态绑定

既然烦的是"IP 会变"，最省事的解法是**让 IP 不要变**：

1. 查到电脑 WLAN 网卡的 **MAC 地址**：
   ```powershell
   Get-NetAdapter | Where-Object { $_.Name -like "*WLAN*" } | Select-Object Name,MacAddress
   ```
2. 登录路由器管理页（`10.1.10.1`）→ 找到「DHCP 保留 / 静态 IP 分配 / MAC-IP 绑定」→ 给该 MAC 固定分配 `10.1.10.130`
3. 之后**无论重启多少次，电脑永远是 10.1.10.130**，固件永远不用重编译

> 这条路是首选。换到别的路由器（比如公司/出差）时仍需按场景 B 处理，但在家里/固定工位就再也不用动了。

### 5.3 顺带要同步的文档

- `xiaozhi-server-部署总结.md` 里记录的 IP 还是旧网络 `192.168.31.204`，换 IP 时记得同步（或在文档里注明"以本手册为准"）。

---

## 6. 设备绑定（激活码）机制 —— 今天踩的坑

### 6.1 为什么设备说"没有找到该设备的版本信息，请正确配置 OTA地址，然后重新编译固件"

这句提示来自 `main/xiaozhi-server/core/handle/receiveAudioHandle.py:133`：设备说话时服务端做绑定检查，**拿不到 6 位验证码**（`conn.bind_code` 为空）就播这句。

而 `bind_code` 只在 manager-api 抛 `DeviceBindException` 时才会有值，条件是 **Redis 里已存在该 MAC 的激活记录**：

```
ota:activation:data:<mac_下划线化>  =  {"activation_code":"xxxxxx", ...}
ota:activation:code:<xxxxxx>       =  "<mac>"
```

### 6.2 两套 OTA 的分工（关键）

| OTA 接口 | 提供方 | 职责 |
|---|---|---|
| `http://<IP>:8003/xiaozhi/ota/` | **Python** xiaozhi-server | 只下发 websocket 地址（单模块运行模式用） |
| `http://<IP>:8002/xiaozhi/ota/` | **manager-api**（智控台） | 下发 websocket 地址 + **生成激活码**（`buildActivation()`），码写 Redis |

我们的设备 OTA 指向 8003，所以 **`buildActivation()` 从没被执行过** → Redis 里没有码 → 设备播报"没有找到版本信息"。
（网页测试端之所以能拿到码，是因为它的 OTA 地址指向了 8002。）

### 6.3 拿码的三条路

**① 代设备向 8002 要一次码（推荐，不改固件不改库）**

```powershell
curl.exe -s -X POST "http://127.0.0.1:8002/xiaozhi/ota/" `
  -H "Content-Type: application/json" `
  -H "Device-Id: a0:85:e3:e6:53:a4" -H "Client-Id: 4a9e1bf4-a9be-4ee2-b9a7-cb1662c8cbc6" `
  -d '{"application":{"version":"1.7.3"},"board":{"type":"bread-compact-wifi"},"mac_address":"a0:85:e3:e6:53:a4"}'
# 响应里的 "activation":{"code":"xxxxxx"} 就是这个设备的验证码
```

拿到码 → 智控台【智能体 → 设备管理 → 添加设备】→ 输入码 → 绑定。
绑定成功后 `ai_device` 表会插入该设备，Redis 里的两条 key 被清理。

**② 直接查 Redis 看是否已有码**

```powershell
D:\Java\redis\Redis-x64-5.0.14.1\redis-cli.exe KEYS "ota:activation:*"
```

**③ 直接往 `ai_device` 插一行（不走绑定的兜底做法）**
需要 `agent_id` / `user_id`，改完即生效，但绕过官方流程，不建议作为常规手段。

> ⚠️ **换网络/重新部署后如果设备又"失联"，先按第 5 章查 OTA 地址，再按本章查是否有激活记录。**

### 6.4 绑定之后：智控台的模型 Key 必须自己填

**切到智控台后，`data/.config.yaml` 里的模型配置全部失效**（配置来源变成数据库）。而数据库里
`ai_model_config` 表的**所有模型默认都是占位符**：

```json
{"type": "openai", "api_key": "你的api_key", "base_url": "https://open.bigmodel.cn/api/paas/v4/", "model_name": "glm-4-flash"}
```

这时 LLM 调用会失败并回一句莫名其妙的提示：

```
【OpenAI服务响应异常: 'ascii' codec can't encode characters in position 7-8: ordinal not in range(128)】
```

**原因**：httpx 拼 `Authorization: Bearer 你的api_key` 时，HTTP 头不允许非 ASCII 字符，
`position 7-8` 正是 `Bearer `（7 个字符）之后的两个中文字。

**处理（在智控台里做，改完断开设备重连即可，不用重启 Python 服务端）**：

| 步骤 | 菜单 | 操作 |
|---|---|---|
| 1 | 【模型配置】→ LLM | 找到该智能体用的模型（如 `智谱AI / ChatGLMLLM`）→ 编辑 → 填**真实 api_key** → 保存 |
| 2 | 【模型配置】→ VLLM | 只有用视觉功能时才需要；填同一个智谱 key 即可 |
| 3 | 【智能体管理】→ 对应智能体 → 记忆模型 | 默认是 `Mem0AI`（要 mem0 云服务 key），**改成「本地短期记忆」**，复用上面的 LLM key |

> 💡 为什么改名明明是 ASR 识别对了、第一句还正常说话了？因为**唤醒词那句回复走了缓存**
> （【参数管理】的 `enable_wakeup_words_response_cache`），没经过 LLM，容易误判成"一切都好"。
> 真正验证 LLM 是否通，要**问一个需要思考的问题**（比如"今天天气怎么样"）。

**当前设备的模型配置（示例）**

| 项 | 值 |
|---|---|
| 设备 | `a0:85:e3:e6:53:a4` |
| 绑定智能体 | `TEST002-设备端` |
| LLM | `LLM_ChatGLMLLM`（智谱 glm-4-flash）→ **需填 key** |
| VLLM | `VLLM_ChatGLMVLLM`（智谱 glm-4v-flash）→ 用视觉时填 key |
| ASR | `ASR_FunASR`（本地模型，无需 key） |
| TTS | `TTS_EdgeTTS`（免 key） |
| 记忆 | `Memory_mem0ai` → **建议改成本地短期记忆** |

---

## 7. 排障速查表

| 现象 | 根因 | 处理 |
|---|---|---|
| 设备日志 `WS: Connecting to websocket server: ` + `Invalid URI format` | OTA 下发了**空** websocket 地址 | 检查 `config_loader.py` 是否透传了 `websocket`；`curl` OTA 看返回是否为空 |
| 设备日志 `Connecting to websocket server: ws://192.168.1.100/...` | 某处写死了占位 IP | 把 `data/.config.yaml` 里 `websocket`/`vision_explain` **注释掉**恢复自动探测 |
| 设备说"没有找到该设备的版本信息…" | Redis 里没有该设备的激活记录 | 见 6.3 ① |
| `idf.py build` 报 `xxx.obj.d: Permission denied` | **两个编译在抢写**（不是权限问题） | `Get-Process ninja,ccache` 清干净后单进程重编 |
| 服务端日志 `Failed to fetch server config from API` | manager-api 没起 / url 不通 | 检查 8002、`manager-api.url` |
| 服务端日志 `manager-api的url或secret配置错误` | secret 不对（智控台重装会换） | 从 `sys_params` 表取 `server.secret` 重新填 |
| ASR 输出乱码 | `models/SenseVoiceSmall/model.pt` 缺失 | 必须走 ModelScope：`modelscope.snapshot_download('iic/SenseVoiceSmall', local_dir='models/SenseVoiceSmall')`（HuggingFace 本机不可达） |
| 对话回复 `【OpenAI服务响应异常: 'ascii' codec can't encode characters in position 7-8...】` | 智控台模型配置里的 **api_key 还是占位符 `你的api_key`** | 智控台【模型配置】填真实 key，见 6.4 |
| TTS 全线 403 | Edge TTS 端点 v1→v2 迁移 | 确认 `edge.py` 的 v2 补丁还在 |
| TTS 偶发 429 | v2 端点限流（回复越长越容易触发） | 后续换国内 TTS |
| 智控台打得开但配置不生效 | 只启动了部分进程 | 4 个进程 + MySQL/Redis 必须都活着 |
| 串口工具占着 COM31 导致烧录失败 | 端口被占用 | 烧录前关掉监视器 |

---

## 8. 待办 / 下一步

| # | 事项 | 状态 |
|---|---|---|
| 1 | 在智控台输入激活码绑定 ESP32 | ⬜ 待做（码见 6.3 ①） |
| 2 | 重启 xiaozhi-server，确认设备连上后能正常对话 | ⬜ 待做 |
| 3 | 换国内 TTS 替换 Edge TTS（解决 429） | ⬜ 待做 |
| 4 | `xiaozhi-server-部署总结.md` 里的旧 IP 同步/标注 | ⬜ 待做 |
| 5 | 路由器做 DHCP 静态绑定（场景 C） | ⬜ 建议尽快做 |
| 6 | 读核心代码（`core/connection.py`、`core/handle/*`、`core/providers/*`、`core/mcp/*`） | ⬜ 阶段 C |
| 7 | 写第一个自定义 MCP 工具（`self.lamp.*` 已有现成例子） | ⬜ 阶段 D |
| 8 | 接入 FastBee（语音控制物联网设备，终极目标） | ⬜ 阶段 E |
