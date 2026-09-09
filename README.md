# 📝 访客留言板 Visitor Message Board

[![GitHub Repo](https://img.shields.io/badge/GitHub-私有仓库-2ea44f?style=flat-square&logo=github)](https://github.com/lan-zz/visitor-message-board)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)
[![Docker: arm64+x86_64](https://img.shields.io/badge/Docker-arm64%2bx86__64-2496ed?style=flat-square&logo=docker)](https://github.com/lan-zz/visitor-message-board/pkgs/container/visitor-message-board)

> 访客连上 WiFi → 自动弹出留言板 → 提交文字/图片/视频/语音 → 主人收到推送通知

访客 WiFi 与内网完全隔离，支持 Bark / 飞书 / 企业微信 / 钉钉四种推送渠道，后台可视化管理。

**快速链接**：[功能说明](#-功能特性) · [部署教程](./INSTALL.md) · [推送配置](./PUSH.md) · [故障排查](./docs/troubleshoot.md) · [Guest 网络自动配置](./deploy/guest-network.sh)

> 🐳 **不想手动 build？** GitHub Actions 已自动构建好 arm64 + x86_64 双架构镜像，可直接拉取使用（见下方「容器镜像」段落）。

---

## 🎯 功能特性

| 特性 | 说明 |
|------|------|
| **强制门户** | 访客连上开放 WiFi 后自动弹出留言板（无需输密码） |
| **访客隔离** | 访客只能访问留言板，无法访问内网设备和外网 |
| **多媒体留言** | 文字 / 图片 / 视频 / 语音（>5 分钟长录音） |
| **多平台推送** | Bark（iOS）/ 飞书 / 企业微信 / 钉钉，可视化配置 |
| **访客身份识别** | 按 MAC 地址区分不同访客，访客只看到自己的留言 |
| **管理员视角** | 内网 192.168.2.x 可删任意留言、查看全部 |
| **配置持久化** | 推送配置存入 `data/config.json`，重启不丢失 |
| **自动清理** | 超过 30 天的旧留言自动删除 |
| **单文件部署** | 一键脚本，修改代码后重启容器即可生效（无需重建镜像） |

---

## 🖥️ 硬件要求

| 项目 | 最低要求 |
|------|----------|
| **路由器** | OpenWrt 23.05+，带 USB 存储 |
| **CPU 架构** | aarch64（ARM64，如 Rockchip RK3568）、x86_64 |
| **内存** | ≥ 256MB 可用 |
| **存储** | ≥ 100MB（媒体文件另计） |
| **无线** | 支持 2.4GHz 802.11n（`mac80211` 驱动） |
| **USB** | 用于存放媒体文件和数据库（推荐 ext4 分区） |

> ⚠️ 本项目 **不依赖特定路由型号**，只要能跑 OpenWrt + Docker 即可。
> 已测试：HINLINK OPi 3 (Rockchip RK3588)、x86_64 软路由。

---

## 📦 软件要求

| 软件 | 版本 | 说明 |
|------|------|------|
| **OpenWrt** | ≥ 23.05 | 需含 LuCI Web 管理 |
| **Docker** | 任意 | 用于运行留言板容器 |
| **Docker Compose** | 任意 | 可选，更方便管理 |
| **network** | iStoreOS / 标准 OpenWrt | 提供防火墙、DHCP、DNS 劫持 |
| **dnsmasq** | 内置 | 需可写租约文件到 `/tmp/dhcp.leases` |

### 安装 Docker（OpenWrt）

```bash
# 在路由器 SSH 中执行
opkg update
opkg install docker docker-compose
/etc/init.d/docker start
/etc/init.d/docker enable
```

---

## 🚀 快速部署（推荐）

### 1. 准备工作目录

```bash
# 在路由器上创建目录（建议挂载到 USB 存储）
mkdir -p /mnt/sda1/message-board
cd /mnt/sda1/message-board

# 创建必要子目录
mkdir -p uploads data certs templates
```

### 2. 上传源码

把本项目所有文件上传到 `/mnt/sda1/message-board/`，目录结构如下：

```
/mnt/sda1/message-board/
├── app.py              # Flask 后端
├── push.py             # 多推送引擎
├── start.sh            # gunicorn 启动脚本
├── Dockerfile
├── templates/
│   ├── index.html      # 访客留言板页面
│   └── admin.html      # 管理后台（推送配置）
├── uploads/            # 媒体文件（自动创建）
├── data/               # 数据库+配置（自动创建）
└── certs/              # HTTPS 证书（见下方）
```

### 3. 生成自签证书（HTTPS 语音必需）

> 语音录音需要安全上下文（HTTPS），必须先生成证书。
> 自签证书会在手机浏览器弹一次警告，点「继续」即可正常使用。

```bash
cd /mnt/sda1/message-board/certs

# 生成私钥和证书（有效期 10 年，SAN 含 192.168.8.1 和 192.168.2.1/2）
openssl req -new -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
  -keyout board.key -out board.crt -days 3650 -nodes \
  -subj "/CN=VisitorBoard" \
  -addext "subjectAltName=DNS:localhost,IP:192.168.8.1,IP:192.168.2.1,IP:192.168.2.2"
```

### 4. 配置 Guest WiFi 网络（OpenWrt LuCI）

在 LuCI → 网络 → 无线中：

- **radio0**（2.4GHz）→ 新增 SSID：`Visitor-Board`（ASCII，不要用中文）
- 网络：`guest`（新建一个接口）
- 安全：开放（无密码）

在 LuCI → 网络 → 接口中：

- **guest** 接口：IP `192.168.8.1` / 子网 `255.255.255.0`
- DHCP：范围 `192.168.8.100` - `192.168.8.150`，租约 1 小时
- DHCP 选项：`3,192.168.8.1`（网关），`6,192.168.8.1`（DNS）

在 LuCI → 网络 → 防火墙中：

- 新建区域 `guest_zone`，Input=Reject，Output=Accept，Forward=Reject
- 放行：DNS（53）、DHCP（67）、HTTP（8090）、HTTPS（8091）
- 拒绝：到 wan、到 lan
- Guest 区域转发到 wan：关闭

### 5. 配置 DNS 劫持 + 强制门户（nftables）

```bash
# SSH 到路由器，执行以下命令

# === Guest 接口入方向 DNAT（80/443 → 留言板）===
# 将访客的 HTTP/HTTPS 流量重定向到留言板
# 192.168.8.2 是留言板容器实际 IP（host 网络模式下就是路由器本身）

# 在 /etc/firewall.user 中添加（持久化）：
cat >> /etc/firewall.user << 'EOF'

# === Guest WiFi → 留言板强制门户 ===
# Guest DNAT：访客访问任何网站 → 跳转留言板
iptables -t nat -A PREROUTING -i br-guest -p tcp --dport 80 \
  -j DNAT --to-destination 192.168.8.1:8090
iptables -t nat -A PREROUTING -i br-guest -p tcp --dport 443 \
  -j DNAT --to-destination 192.168.8.1:8091
EOF

# 重载防火墙
/etc/init.d/firewall reload
```

### 6. 构建并启动容器

```bash
cd /mnt/sda1/message-board

# 给脚本加执行权限
chmod +x start.sh

# 构建镜像（首次运行需要）
docker build -t visitor-board .

# 启动容器
docker run -d \
  --name visitor-board \
  --network host \
  --restart unless-stopped \
  -v $(pwd)/certs:/certs:ro \
  -v $(pwd)/uploads:/app/uploads \
  -v $(pwd)/data:/app/data \
  -v /tmp/dhcp.leases:/tmp/dhcp.leases:ro \
  -v $(pwd)/start.sh:/app/start.sh:ro \
  -e MAX_UPLOAD_MB=500 \
  -e CLEANUP_DAYS=30 \
  -e ADMIN_SUBNET=192.168.2. \
  visitor-board sh /app/start.sh

# 验证
curl http://127.0.0.1:8090/health
# 应返回 {"ok": true, ...}
```

以后更新代码只需：

```bash
# 重启容器即可（卷挂载，文件已更新）
docker restart visitor-board
```

---

## 📱 推送平台配置指南

### 方式一：后台可视化配置（推荐）

1. 用内网设备（192.168.2.x）打开 `http://192.168.2.1:8090/admin`
2. 选择推送平台（Bark / 飞书 / 企业微信 / 钉钉）
3. 填入对应参数，点击「发送测试」
4. 收到测试通知后，点击「保存配置」

> ⚠️ 只有从 **192.168.2.x** 内网访问 `/admin` 才能配置。访客网络（192.168.8.x）无法访问。

---

### 方式二：直接编辑 config.json

配置文件在容器的 `/app/data/config.json`（映射到宿主 `/mnt/sda1/message-board/data/config.json`）：

```json
{
  "enabled": true,
  "platform": "bark",
  "bark": {
    "key": "你的 Bark Key"
  }
}
```

---

### Bark（iOS）

1. 在 iPhone 下载 [Bark](https://apps.apple.com/app/bark/id1403753865)
2. 打开 App → 点击左上角头像 → 获取「Bark URL」
3. URL 格式：`https://api.day.app/你的BarkKey`
4. 填入中间那段 Key

```json
{
  "enabled": true,
  "platform": "bark",
  "bark": { "key": "你的BarkKey" }
}
```

---

### 飞书

1. 在飞书群 → 右上角「···」→「群设置」→「群机器人」→「添加机器人」
2. 选择「自定义机器人」
3. 复制 Webhook 地址（格式：`https://open.feishu.cn/open-apis/bot/v2/hook/xxx`）
4. 在后台填入 Webhook 地址

```json
{
  "enabled": true,
  "platform": "feishu",
  "feishu": { "webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/你的ID" }
}
```

---

### 企业微信

1. 企业微信群 → 添加群机器人
2. 复制 Webhook 地址（格式：`https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx`）

```json
{
  "enabled": true,
  "platform": "wecom",
  "wecom": { "webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=你的key" }
}
```

---

### 钉钉

1. 钉钉群 → 群设置 → 智能群助手 → 添加机器人
2. 选择「自定义」机器人
3. 复制 Webhook 地址
4. **可选**：开启「加签」，复制密钥（以 `SEC` 开头）

```json
{
  "enabled": true,
  "platform": "dingtalk",
  "dingtalk": {
    "webhook": "https://oapi.dingtalk.com/robot/send?access_token=你的token",
    "secret": "SEC...你的密钥（不加签可不填）"
  }
}
```

---

## 🔧 完整网络架构图

```
访客手机
  │  连接 SSID: Visitor-Board（开放 WiFi，无密码）
  │  DHCP 获得 192.168.8.100-150（1小时租约）
  │
  ▼
OpenWrt Guest 网关 192.168.8.1
  │  nftables/iptables 强制门户
  │  所有 HTTP(80)/HTTPS(443) → DNAT → 本机 8090/8091
  │
  ▼
访客留言板容器（--network host）
  │  HTTP  8090 ← 文字/图片/视频留言
  │  HTTPS 8091 ← 语音录音（自签证书）
  │  读取 /tmp/dhcp.leases → 解析访客 MAC
  │
  ├──▶ 写入 /mnt/sda1/message-board/data/board.db（SQLite）
  │
  └──▶ 推送通知（Bark / 飞书 / 企业微信 / 钉钉）
           │
           └──▶ 主人手机
```

---

## 📂 目录结构

```
visitor-message-board/
├── app.py              # Flask 主应用（含全部 API）
├── push.py             # 多推送引擎（各平台推送实现）
├── start.sh            # gunicorn 启动命令（双端口）
├── Dockerfile          # 容器镜像定义
├── README.md           # 本文档
├── INSTALL.md          # 详细安装步骤
├── PUSH.md             # 推送平台配置详解
├── templates/
│   ├── index.html      # 访客留言板页面
│   └── admin.html      # 管理后台（推送配置 + 参数）
├── docs/
│   └── troubleshoot.md  # 常见问题排查
└── deploy/
    ├── guest-network.sh     # Guest 网络自动配置（OpenWrt）
    └── recreate-board.sh    # 一键重建容器
└── deploy/
    ├── guest-network.sh     # Guest 网络自动配置（OpenWrt）
    └── recreate-board.sh    # 一键重建容器
```

---

## 🐳 容器镜像（无需本地 build）

GitHub Actions 在每次 push 时自动构建并存放到 GitHub Container Registry（GHCR）。

```bash
# arm64（RK3568 / RK3588 / Apple Silicon / 小型 ARM 开发板）
docker pull ghcr.io/lan-zz/visitor-message-board:latest-arm64

# x86_64（软路由、x86 设备、VM）
docker pull ghcr.io/lan-zz/visitor-message-board:latest
```

> ⚠️ GHCR 镜像仓库为**私有**，同一 GitHub 账号下可直接拉取。
> 如需在别的机器拉取，请参考 [GHCR 文档](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry) 登录后再拉。

镜像拉下来后，按「快速部署」第 5 步（网络配置）往后执行即可，无需再 `docker build`。

---

## ❓ 常见问题

### Q: 访客连上 WiFi 后不弹出留言板？

访客可能手动关闭了弹窗。手动打开浏览器访问任意 HTTP 网站（如 `http://example.com`），
DNS 劫持会将其引导到留言板。HTTPS 网站无法劫持（正常行为）。

### Q: 语音录音按钮点不了？

语音需要安全上下文（麦克风 API 仅在 HTTPS 下可用）。
- 方式一：在留言板页面顶部点击「🔗 点此打开语音留言」，跳转到 `https://192.168.8.1:8091`（首次会提示证书不安全，点「继续」即可）
- 方式二：在手机浏览器地址栏直接输入 `https://192.168.8.1:8091`

### Q: HTTPS 证书警告能消除吗？

**不能消除**。自签证书在手机上必然弹「此连接非私人连接」警告，
这是浏览器安全机制，无法绕过。访客点一次「继续/高级→继续」后即可正常使用。
如需完全消除警告，需要：
1. 拥有一个自己的域名（如 `xxx.duckdns.org`）
2. 用 Let's Encrypt 签发受信任证书
3. 将域名 DNS 解析到 `192.168.8.1`

### Q: 图片/视频选不了文件？

部分手机在强制门户弹窗内无法调起文件选择器（系统限制）。
解决：点击留言板页面顶部横幅「💡 发送图片/视频请在手机浏览器中打开...」，
在浏览器中打开 `http://192.168.8.1:8090` 即可正常上传。

### Q: 想同时跑 5G + 2.4G 两个 SSID？

单射频网卡（如 MT7921e）同时只能广播一个 SSID。
如果有两个无线网卡（如一个 PCIe 5G + 一个 USB 2.4G），可以为每个 radio
各建一个 guest 接口，实现双频各一个 SSID。

### Q: 如何查看容器日志？

```bash
docker logs --tail 50 visitor-board
```

### Q: 如何完全卸载？

```bash
# 删除容器
docker rm -f visitor-board

# 删除镜像
docker rmi visitor-board

# 删除数据（谨慎！）
rm -rf /mnt/sda1/message-board

# 恢复 Guest 网络（LuCI 中删除 guest 接口和防火墙规则即可）
```

---

## 📄 License

MIT License · 开源免费，可随意 Fork 和改造
