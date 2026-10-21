# xiaozhi-esp32-server 服务器部署 SOP

> 生成时间：2026-10-21
> 服务器：OpenCloudOS（Linux，root）
> 部署目标：
>
> **全模块**
>
>  \= 语音服务端 + 智控台 Web + MySQL + Redis
> 本地代码目录：
>
> `D:\CODE\TEST\ESP32\xiaozhi-esp32-server`



***

## 部署方式推荐（结论）

**直接在服务器上用官方 Docker 预构建镜像 + docker-compose 全模块**。

理由：



* 项目官方已把「语音服务端 + 智控台 Java + 前端 Web」打包成镜像（`server_latest` / `web_latest`），**无需在服务器上编译 Java/Node**。

* 只需上传 2 样东西：`data/.config.yaml`（配置）+ `models/SenseVoiceSmall/model.pt`（语音识别模型，936MB）。

* 镜像源有国内限制，我们用连通性测试决定走哪个源。

不需要上传的东西：整个项目源码、models 里除 SenseVoiceSmall 之外的文件。



***

## 端口规划（全模块）



| 端口        | 用途                                                 |
| --------- | -------------------------------------------------- |
| 8000      | 语音服务 WebSocket（设备连接 `ws://服务器IP:8000/xiaozhi/v1/`） |
| 8002      | 智控台 Web 管理界面（浏览器访问 `http://服务器IP:8002`）            |
| 8003      | OTA / 视觉分析接口                                       |
| 3306/6379 | MySQL、Redis（仅容器内部，compose 内部网络）                    |



***

## 第一步：服务器安装 Docker

在服务器上执行（OpenCloudOS 基于 CentOS/RHEL 系）：



```
# 1) 安装必要工具
yum install -y yum-utils

# 2) 配置 Docker 官方源（yum 安装）
yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo

# 3) 安装 docker-ce 及 compose 插件
yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 4) 启动并设开机自启
systemctl enable --now docker

# 5) 验证
docker --version
docker compose version
```

> 若 
>
> `yum-config-manager`
>
>  报错找不到，先 
>
> `yum install -y yum-utils`
>
> 。若官方源拉不到（国内网络），改用阿里云 Docker 源：
>

```
yum-config-manager --add-repo https://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo
yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
```



***

## 第二步：测试镜像源连通性（关键分支）

先测试官方使用的镜像源 `ghcr.nju.edu.cn` 是否可访问：



```
docker pull ghcr.nju.edu.cn/xinnan-tech/xiaozhi-esp32-server:server_latest
```

**分支判断：**

### ✅ 情况 A：能拉取成功

直接用 `ghcr.nju.edu.cn` 源，跳过换源步骤，直接进第三步。

### ❌ 情况 B：拉取失败（网络受限）

依次尝试以下**镜像源别名**，把 `ghcr.nju.edu.cn` 替换成能成功的那个：



* `ghcr.io/xinnan-tech/xiaozhi-esp32-server:server_latest`（官方原源）

* `ghcr.nju.edu.cn/...`（南大镜像）

* 国内加速源（任选其一试）：



```
docker pull docker.m.daocloud.io/ghcr.io/xinnan-tech/xiaozhi-esp32-server:server_latest
docker pull ghcr.dockerproxy.com/xinnan-tech/xiaozhi-esp32-server:server_latest
docker pull docker.1ms.run/ghcr.io/xinnan-tech/xiaozhi-esp32-server:server_latest
```

**换源后要改 compose 文件里的 image 行**（见第五步）。哪个能拉成功，就把 compose 里的 `image:` 改成哪个前缀。两个镜像都要测：



* `server_latest`（服务端）

* `web_latest`（智控台）

> 注意：加速源前缀可能随时变动，以实测能 pull 成功为准。若全都失败，说明服务器外网受限较严，需走「先下到本地再导入」方案（见备选方案）。



***

## 第三步：准备上传的文件（本地）

在本地把以下 2 项准备到同一目录，方便一起上传。

### 1. 配置文件 `data/.config.yaml`

本地已有：`D:\CODE\TEST\ESP32\xiaozhi-esp32-server\main\xiaozhi-server\data\.config.yaml`

**必须修改&#x20;**`server.websocket`**&#x20;为服务器公网 / 局域网 IP**（设备要连的是这个）：



```
server:
  ip: 0.0.0.0
  port: 8000
  http_port: 8003
  # 改成服务器实际 IP
  websocket: "ws://服务器IP:8000/xiaozhi/v1/"
  vision_explain: "http://服务器IP:8003/mcp/vision/explain"

LLM:
  ChatGLMLLM:
    api_key: "你的智谱api_key"   # 填真实 key
```

### 2. 语音识别模型 `models/SenseVoiceSmall/model.pt`

本地路径：`D:\CODE\TEST\ESP32\xiaozhi-esp32-server\main\xiaozhi-server\models\SenseVoiceSmall\model.pt`（936MB）

> **可选优化**
>
> ：如果服务器能访问 
>
> [modelscope.cn](https://modelscope.cn)
>
> ，可直接在服务器上重新下载模型，免去上传 936MB：
>

```
mkdir -p models/SenseVoiceSmall && cd models/SenseVoiceSmall
curl -L -o model.pt "https://modelscope.cn/models/iic/SenseVoiceSmall/resolve/master/model.pt"
```

> 若服务器拉 model 慢 / 失败，就改为本地 scp 上传。



***

## 第四步：上传文件到服务器

在本地 PowerShell 用 `scp` 上传（也可用你常用的 WinSCP / 宝塔）。把 `data` 和 `models` 放到服务器上你想部署的目录，例如 `/root/xiaozhi`：



```
# 本地 PowerShell 执行（换成你的服务器 IP、端口、用户名）
scp -P 22 -r "D:\CODE\TEST\ESP32\xiaozhi-esp32-server\main\xiaozhi-server\data" root@服务器IP:/root/xiaozhi/
scp -P 22 -r "D:\CODE\TEST\ESP32\xiaozhi-esp32-server\main\xiaozhi-server\models\SenseVoiceSmall" root@服务器IP:/root/xiaozhi/models/
```

> 若服务器已按第三步优化直接在服务器下载了 model.pt，则只需上传 
>
> `data`
>
>  目录。



***

## 第五步：服务器上创建 compose 文件

在服务器 `/root/xiaozhi` 目录创建 `docker-compose.yml`，内容用项目官方全模块版（已按需改镜像源 + 端口映射）:



```
version: '3'
services:
  # Server模块
  xiaozhi-esp32-server:
    image: IMAGE_PREFIX/xinnan-tech/xiaozhi-esp32-server:server_latest
    container_name: xiaozhi-esp32-server
    depends_on:
      - xiaozhi-esp32-server-db
      - xiaozhi-esp32-server-redis
    restart: always
    networks: [default]
    ports:
      - "8000:8000"
      - "8003:8003"
    security_opt:
      - seccomp:unconfined
    environment:
      - TZ=Asia/Shanghai
    volumes:
      - ./data:/opt/xiaozhi-esp32-server/data
      - ./models/SenseVoiceSmall/model.pt:/opt/xiaozhi-esp32-server/models/SenseVoiceSmall/model.pt

  # manager-api 和 manager-web 模块
  xiaozhi-esp32-server-web:
    image: IMAGE_PREFIX/xinnan-tech/xiaozhi-esp32-server:web_latest
    container_name: xiaozhi-esp32-server-web
    restart: always
    networks: [default]
    depends_on:
      xiaozhi-esp32-server-db:
        condition: service_healthy
      xiaozhi-esp32-server-redis:
        condition: service_healthy
    ports:
      - "8002:8002"
    environment:
      - TZ=Asia/Shanghai
      - SPRING_DATASOURCE_DRUID_URL=jdbc:mysql://xiaozhi-esp32-server-db:3306/xiaozhi_esp32_server?useUnicode=true&characterEncoding=UTF-8&serverTimezone=Asia/Shanghai&nullCatalogMeansCurrent=true&connectTimeout=30000&socketTimeout=30000&autoReconnect=true&failOverReadOnly=false&maxReconnects=10
      - SPRING_DATASOURCE_DRUID_USERNAME=root
      - SPRING_DATASOURCE_DRUID_PASSWORD=123456
      - SPRING_DATA_REDIS_HOST=xiaozhi-esp32-server-redis
      - SPRING_DATA_REDIS_PORT=6379
    volumes:
      - ./uploadfile:/uploadfile

  # MySQL
  xiaozhi-esp32-server-db:
    image: mysql:8
    container_name: xiaozhi-esp32-server-db
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      timeout: 45s
      interval: 10s
      retries: 10
    restart: always
    networks: [default]
    expose:
      - 3306
    volumes:
      - ./mysql/data:/var/lib/mysql
    environment:
      - TZ=Asia/Shanghai
      - MYSQL_ROOT_PASSWORD=123456
      - MYSQL_DATABASE=xiaozhi_esp32_server

  # Redis
  xiaozhi-esp32-server-redis:
    image: redis:7
    expose: [6379]
    container_name: xiaozhi-esp32-server-redis
    restart: always
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3
    networks: [default]

networks:
  default:
```

**把&#x20;**`IMAGE_PREFIX`**&#x20;替换成第二步测试成功的前缀**，例如：



* 成功的是 `ghcr.nju.edu.cn` → `image: ghcr.nju.edu.cn/xinnan-tech/xiaozhi-esp32-server:server_latest`

* 成功的是 `docker.m.daocloud.io/ghcr.io` → `image: docker.m.daocloud.io/ghcr.io/xinnan-tech/xiaozhi-esp32-server:server_latest`

> 我用的是 
>
> `mysql:8`
>
>  和 
>
> `redis:7`
>
>  固定版本，避免 
>
> `latest`
>
>  漂移。如果你的 Docker Hub 也受限，把这两个 image 前缀也换成 Docker 加速源（如 
>
> `docker.m.daocloud.io/mysql:8`
>
> ）。



***

## 第六步：启动



```
cd /root/xiaozhi
docker compose up -d
```

## 第七步：验证



```
# 1) 容器状态（4 个都应为 Up）
docker compose ps

# 2) 看服务端日志（确认启动完成、打印出 websocket 地址）
docker logs -f xiaozhi-esp32-server
# 看到 "Websocket地址是 ws://xxx:8000/xiaozhi/v1/" 即成功

# 3) 智控台日志
docker logs -f xiaozhi-esp32-server-web

# 4) 浏览器验证智控台
# 访问 http://服务器IP:8002  → 看到登录页 = 智控台 OK
# 首次登录点「新用户注册」创建第一个超管账号
```

**设备对接：**



* 设备连接地址：`ws://服务器IP:8000/xiaozhi/v1/`

* OTA 接口：`http://服务器IP:8003/xiaozhi/ota/`

* 需在服务器安全组 / 防火墙放行 **8000、8002、8003** 三个端口（云服务器一般是安全组，在云控制台加规则）。



***

## 备选方案：本地镜像导出 → 服务器导入

如果所有镜像源在服务器都拉不动（外网严重受限），用此方案：



1. **本地**（能访问外网的机器）拉镜像并导出：



```
docker pull ghcr.nju.edu.cn/xinnan-tech/xiaozhi-esp32-server:server_latest
docker pull ghcr.nju.edu.cn/xinnan-tech/xiaozhi-esp32-server:web_latest
docker pull mysql:8
docker pull redis:7
docker save -o xiaozhi_images.tar ghcr.nju.edu.cn/xinnan-tech/xiaozhi-esp32-server:server_latest ghcr.nju.edu.cn/xinnan-tech/xiaozhi-esp32-server:web_latest mysql:8 redis:7
```



1. **上传** 那个 tar（很大，几个 G）到服务器，然后：



```
docker load -i xiaozhi_images.tar
```



1. 把 compose 里所有 `image:` 改成**本地能识别但不拉取的名称**，并去掉 `pull`。此时本地 docker 已有这些镜像，compose 直接用本地的即可。



***

## 常见问题



| 现象                          | 原因 / 解决                                         |
| --------------------------- | ----------------------------------------------- |
| `docker: command not found` | Docker 未装，见第一步                                  |
| 容器起不来，端口占用                  | 服务器 8000/8002/8003 被占，`ss -lntp` 查占用            |
| MySQL 连不上                   | 等 db 容器 healthy 后再起 web；`docker compose ps` 看状态 |
| 智控台 8002 打不开                | 安全组 / 防火墙没放行 8002                               |
| 设备连不上 8000                  | websocket 配置 IP 是否 = 服务器 IP；安全组放行 8000          |
| 镜像拉取超时                      | 换镜像源（第二步）或走备选方案                                 |