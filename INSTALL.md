# 📖 详细安装步骤

本文档是 [README.md](README.md) 的补充，提供完整、分步骤的安装说明。

---

## 环境说明

- **宿主系统**：OpenWrt 23.05+（已测试 iStoreOS 24.x / 标准 OpenWrt）
- **目标平台**：aarch64（ARM64，如 Rockchip RK3568/RK3588）或 x86_64
- **存储**：USB 存储（ext4 文件系统，推荐 `/mnt/sda1`）

---

## 步骤 0：安装 Docker（如已安装跳过）

```bash
opkg update
opkg install docker docker-compose
/etc/init.d/docker start
/etc/init.d/docker enable
```

确认 Docker 正常：

```bash
docker info | head -5
docker ps   # 应无报错
```

---

## 步骤 1：准备 USB 存储

```bash
# 查看磁盘分区
lsblk

# 格式化（⚠️ 会清空数据，请先备份！）
# mkfs.ext4 -F /dev/sda1

# 挂载
mkdir -p /mnt/sda1
mount /dev/sda1 /mnt/sda1

# 开机自动挂载（编辑 /etc/config/fstab）
# 在 LuCI → 系统 → 挂载点 中添加更直观
```

---

## 步骤 2：上传项目文件

在**电脑端**执行（PowerShell）：

```powershell
# 克隆本仓库
git clone https://github.com/YOUR_USERNAME/visitor-message-board.git

# 上传到路由器
$pw = "你的路由器密码"
$pscp = "C:\Program Files\PuTTY\pscp.exe"
$user = "root@192.168.2.1"
$hostkey = "ssh-ed25519 255 你的指纹"

# 上传全部文件（递归）
& $pscp -pw $pw -hostkey $hostkey -r .\visitor-message-board\* "${user}:/mnt/sda1/message-board/"
```

---

## 步骤 3：生成 HTTPS 证书

```bash
cd /mnt/sda1/message-board/certs

openssl req -new -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
  -keyout board.key -out board.crt -days 3650 -nodes \
  -subj "/CN=VisitorBoard" \
  -addext "subjectAltName=DNS:localhost,IP:192.168.8.1,IP:192.168.2.1,IP:192.168.2.2"
```

> **为什么需要 HTTPS 证书？**  
> 浏览器的 `getUserMedia()` API（麦克风）只允许在安全上下文（HTTPS）下使用。
> 自签证书会产生一次性的「不安全」警告，访客点一次「继续」即可，之后正常使用。

---

## 步骤 4：配置 Guest 网络（LuCI 图形界面）

### 4.1 新建 Guest 接口

LuCI → 网络 → 接口 → 新建接口：
- 名称：`guest`
- 协议：`静态地址`
- 设备：`br-guest`（新建桥接）
- IP：`192.168.8.1`，子网掩码：`255.255.255.0`

### 4.2 配置 Guest DHCP

在 guest 接口设置中 → DHCP 服务器：
- 忽略接口：❎（取消勾选，启用）
- 起始 IP：`192.168.8.100`
- 终止 IP：`192.168.8.150`
- 租约时间：3600 秒（1小时）

### 4.3 新建 Guest 防火墙区域

LuCI → 网络 → 防火墙 → 新建区域 `guest`：
- 入站：拒绝 / 输出：接受 / 转发：拒绝
- 覆盖 MASQUERADE：✅
- 允许转发到目标区域：wan（拒绝） / lan（拒绝）
- 允许来自源区域的：DNS（53）+ DHCP（67）

### 4.4 配置 Guest 无线

LuCI → 网络 → 无线 → radio0（2.4GHz）→ 添加：
- SSID：`Visitor-Board`（ASCII，建议纯英文字母）
- 网络：选择 `guest` 接口
- 安全：开放（无加密）
- 模式：802.11n
- 信道：任选（推荐 1/6/11）
- 国家：中国（CN）→ 发射功率上限 20 dBm

### 4.5 检查 br-guest 桥接设备

LuCI → 网络 → 接口 → 设备 → 检查 `br-guest`：
- **重要**：`br-guest` 的「桥接端口」**只能包含**无线 AP（phy0-ap0）
- **不能包含** eth0 / eth1 / eth2 等物理网口（否则访客能进内网）

---

## 步骤 5：配置 Guest 接口的物理端口（关键！）

这一步决定访客能否访问内网：

```bash
# 查看当前 br-lan 的端口
uci show network.lan | grep ports

# 示例输出：network.lan=interface\nnetwork.lan.ifname='eth0 eth2 eth3'
# 这表示 br-lan 包含 eth0/eth2/eth3

# 从 br-lan 移除无线 AP 端口（防止被错误桥接）
# 注意：只需要移除无线 AP phy0-ap0，不是物理网口！
# 如果 br-lan 里已经不含 phy0-ap0，可跳过

# 创建 br-guest 桥接设备（OpenWrt UCI 方式）
uci set network.guest=interface
uci set network.guest.proto='static'
uci set network.guest.ipaddr='192.168.8.1'
uci set network.guest.netmask='255.255.255.0'
uci set network.guest.device='br-guest'

# 添加 Guest 桥接设备（只有无线 AP）
uci add_list network.guest.device='phy0-ap0'
# （或通过 LuCI → 网络 → 接口 → 设备 → br-guest → 桥接端口 添加）

# 提交
uci commit network
/etc/init.d/network reload
```

---

## 步骤 6：配置 DNS 劫持 + 强制门户

### 6.1 启用 dnsmasq DNS 劫持

LuCI → 网络 → DHCP → 高级设置：
- 忽略解析文件：❎
- 在 `/etc/dnsmasq.conf` 中添加（或在 LuCI → 网络 → DHCP → 高级设置 → 扩展选项）：

```
address=/# /192.168.8.1
```

或使用 UCI：

```bash
uci add_list dhcp.@dnsmasq[0].address='/#/192.168.8.1'
uci commit dhcp
/etc/init.d/dnsmasq reload
```

### 6.2 iptables / nftables DNAT 规则

在 LuCI → 网络 → 防火墙 → 自定义规则（或 SSH 直接编辑）：

```bash
cat >> /etc/firewall.user << 'EOF'

# ========== Visitor Board 强制门户 ==========
# Guest WiFi 流量 DNAT：80 → 留言板 HTTP，443 → 留言板 HTTPS
# 注意：443 只能 DNAT 到 HTTPS 服务，不能到 HTTP（会导致 gunicorn 崩溃）

# Guest 入方向 DNAT（访客 → 留言板）
iptables -t nat -A PREROUTING -i br-guest -p tcp --dport 80 \
  -j DNAT --to-destination 192.168.8.1:8090
iptables -t nat -A PREROUTING -i br-guest -p tcp --dport 443 \
  -j DNAT --to-destination 192.168.8.1:8091

# Guest 区域放行（input chain）
iptables -A input_guest -p tcp --dport 8090 -j ACCEPT
iptables -A input_guest -p tcp --dport 8091 -j ACCEPT
iptables -A input_guest -p udp --dport 53  -j ACCEPT
iptables -A input_guest -p udp --dport 67  -j ACCEPT

# Guest 隔离：拒绝访问内网（可选，加强安全）
iptables -A forwarding_guest -d 192.168.2.0/24 -j REJECT
iptables -A forwarding_guest -d 192.168.0.0/16 -j REJECT
EOF

# 重载防火墙
/etc/init.d/firewall reload
```

> ⚠️ **不要**把 443 DNAT 到 HTTP（80）端口！TLS 握手被 gunicorn 解析会触发 `Invalid HTTP method` 错误，
> 导致 worker 崩溃循环，容器进入「Up 但假死」状态。

---

## 步骤 7：构建镜像并启动

```bash
cd /mnt/sda1/message-board

# 构建镜像
docker build -t visitor-board .

# 首次启动
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

# 确认运行
docker ps
docker logs --tail 10 visitor-board
curl http://127.0.0.1:8090/health
```

以后更新代码只需：

```bash
docker restart visitor-board
```

---

## 步骤 8：验证端到端

### 8.1 访客视角验证

```bash
# 用网络命名空间模拟真实访客
ip netns add test-guest
ip link add test-veth0 type veth peer name test-veth0h
ip link set test-veth0h netns test-guest
ip link set test-veth0 master br-guest
ip link set test-veth0 up
ip -n test-guest addr add 192.168.8.199/24 dev test-veth0h
ip -n test-guest link set test-veth0h up
ip -n test-guest route add default via 192.168.8.1

# 测试留言板可达
ip netns exec test-guest curl -s --max-time 5 http://192.168.8.1:8090/health

# 测试强制门户（访客访问任意 HTTP 网站应跳转到留言板）
ip netns exec test-guest curl -s --max-time 5 -o /dev/null -w '%{http_code}' http://1.2.3.4/

# 测试外网隔离（应无法访问）
ip netns exec test-guest curl -s --max-time 3 http://8.8.8.8/
# 应返回 HTTP=000 或超时

# 测试内网隔离（应无法访问）
ip netns exec test-guest curl -s --max-time 3 http://192.168.2.1/
# 应返回 HTTP=000 或超时

# 清理
ip netns del test-guest 2>/dev/null; ip link del test-veth0 2>/dev/null
```

### 8.2 推送验证

在管理后台（`http://192.168.2.1:8090/admin`）→ 点击「发送测试」，
应收到 Bark / 飞书 / 企业微信 / 钉钉通知。

---

## 步骤 9：生成二维码

访客扫码连 WiFi 后还需要能快速打开留言板，可以生成二维码：

**WiFi 二维码**（贴门口，访客扫码连 WiFi）：

```
WIFI:S:Visitor-Board;T:nopass;;
```
> 可用在线工具（如 `qrcode.monster`）生成，或用 Python：

```python
# pip install qrcode pillow
import qrcode
qr = qrcode.QRCode(version=1, box_size=10)
qr.add_data('WIFI:S:Visitor-Board;T:nopass;;')
qr.make(fit=True)
img = qr.make_image()
img.save('Visitor-Board-WiFi.png')
```

**留言板地址二维码**（放在 WiFi 二维码旁边，访客扫码直接打开留言板）：

```
http://192.168.8.1:8090
```
> 建议同时注明：「如弹窗未出现，请在浏览器地址栏输入上方地址」

---

## 故障排查索引

详细排查见 [docs/troubleshoot.md](docs/troubleshoot.md)。快速对照：

| 现象 | 可能原因 |
|------|----------|
| 连上 WiFi 无弹窗 | DNS 劫持未生效 / 浏览器禁用了弹窗 |
| 留言板打不开 | 容器未启动 / 端口被占用 / 防火墙规则缺失 |
| 图片/视频发送失败 | 容器假死 / 磁盘空间不足 |
| 语音按钮点不了 | 强制门户 webview 限制，用浏览器打开 |
| Bark 收不到推送 | Bark Key 填错 / 容器无法访问外网 |
| 访客能访问内网 | br-guest 桥接了内网物理网口 |
| 5G 和 2.4G 只能开一个 | 单射频网卡限制，两频各需独立网卡 |
