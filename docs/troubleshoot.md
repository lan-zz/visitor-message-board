# 🔧 故障排查

## 排查入口点

```bash
# 1. 容器状态
docker ps -a | grep visitor

# 2. 容器是否假活（Up 但不服务）
curl --max-time 5 http://127.0.0.1:8090/health
# HTTP=000 → 容器不响应

# 3. 容器日志
docker logs --tail 30 visitor-board

# 4. iptables 规则是否存在
iptables -t nat -L PREROUTING -vn | grep 8090

# 5. Guest 网桥是否正常
ip link show br-guest
ip addr show br-guest | grep 192.168.8.1

# 6. 端口监听
ss -tlnp | grep '8090\|8091'
```

---

## 常见问题

### ① 容器「Up」但所有请求超时（HTTP=000）

**症状**：docker ps 显示 Up，但 curl 完全不通（TCP 建立都失败或超时）。

**可能原因 1**：gunicorn worker 全部崩溃，容器假活。

```bash
# 诊断
docker logs visitor-board | grep -i error

# 修复：重启容器
docker restart visitor-board
sleep 3
curl --max-time 5 http://127.0.0.1:8090/health
```

**可能原因 2**：大量请求把 worker 占满（大文件上传未完成时 worker 被占用）。

```bash
# 诊断：看 gunicorn worker 是否全在处理请求
docker exec visitor-board ps aux | grep gunicorn

# 修复：增加 worker 数量，或增大 timeout
# 编辑 start.sh，把 -w 4 改成 -w 8
```

**可能原因 3**：端口被占用。

```bash
ss -tlnp | grep 8090
# 如果有其他进程占用，杀掉或改端口
```

---

### ② 访客连上 WiFi 后无弹窗

**可能原因 1**：DNS 劫持未生效。

```bash
# 诊断：访客侧能否解析到留言板 IP
ip netns exec test-guest nslookup example.com 192.168.8.1
# 应返回 192.168.8.1

# 修复：确保 dnsmasq 有 address=/#/192.168.8.1
grep address /etc/dnsmasq.conf
uci get dhcp.@dnsmasq[0].address 2>/dev/null
```

**可能原因 2**：设备禁用了强制门户弹窗（部分 iOS/Android 系统行为）。

手动打开浏览器访问 `http://example.com` 触发跳转。

**可能原因 3**：浏览器缓存了之前的「已登录」状态。

清除浏览器缓存，或用隐身模式。

---

### ③ 留言板打开但「发送」无任何提示

**可能原因**：Bark Key 未配置导致后端静默失败，但前端正常。

```bash
# 检查 Bark 配置是否存在
cat /mnt/sda1/message-board/data/config.json | grep -A5 bark

# 在后台（http://192.168.2.1:8090/admin）配置 Bark Key 并测试推送
```

**可能原因**：网络问题（容器无法访问 api.day.app）。

```bash
# 从容器内测试外网连通性
docker exec visitor-board wget -q -O - https://api.day.app/ && echo OK

# 如果失败：检查 host 网络模式是否正常
docker exec visitor-board ip route
# 应有默认路由到 192.168.2.1
```

---

### ④ 图片/视频上传失败

**可能原因 1**：磁盘空间不足。

```bash
df -h /mnt/sda1
du -sh /mnt/sda1/message-board/uploads
```

**可能原因 2**：上传被防火墙阻断。

```bash
# 确认防火墙允许 8090 端口
iptables -L input_guest -vn | grep 8090
# 修复：
iptables -A input_guest -p tcp --dport 8090 -j ACCEPT
```

**可能原因 3**：文件大小超过上限（500MB）。

前端会提前检查；后端在文件保存后也会检查。
确认 app.py 中 `MAX_UPLOAD_MB=500` 与实际环境变量一致。

---

### ⑤ 语音录音无法工作

**表现**：点击录音按钮后浏览器报错或无响应。

**可能原因 1**：不在 HTTPS 页面。

语音需要 `getUserMedia` API，仅在安全上下文（HTTPS/WSS）下可用。
在留言板页面顶部点击「🔗 点此打开语音留言」跳转到 `https://192.168.8.1:8091`。

**可能原因 2**：自签证书未信任。

首次访问 `https://192.168.8.1:8091` 时，浏览器会弹出「不安全」警告，
点「继续 / 高级 → 继续前往」即可，之后正常使用。

**可能原因 3**：手机系统权限禁止麦克风。

iOS：设置 → Safari → 麦克风 → 允许
Android：设置 → 应用 → 浏览器 → 权限 → 麦克风 → 允许

---

### ⑥ 访客能访问内网（最严重安全问题）

**现象**：访客可以打开内网设备（如 192.168.2.x 的管理后台）。

**根因**：br-guest 桥接了内网物理网口。

```bash
# 检查 br-guest 的桥接端口
ip link show type bridge | -A -d
# 或
brctl show

# 确认 br-guest 只包含 phy0-ap0（无线 AP），不包含 eth0/eth1 等
```

**修复**：

LuCI → 网络 → 接口 → 设备 → br-guest → 桥接端口：
- 移除所有物理网口（eth0, eth2, eth3 等）
- 只保留无线 AP 端口（通常叫 `phy0-ap0` 或 `wlan0`）

```bash
# 或用 UCI 命令修复
# 从 network.lan.device 移除 phy0-ap0（如果它在里面）
# 从 network.guest.device 添加 phy0-ap0（如果它不在里面）
uci show network | grep -E 'device|br-guest|phy0'
```

---

### ⑦ docker0 桥消失（容器无法启动）

**现象**：容器创建时报错 `Device "docker0" does not exist`。

**根因**：某些 OpenWrt 网络重载操作会删除 docker0 桥。

```bash
# 诊断
ip link show docker0

# 修复：重建 docker0 桥
ip link add docker0 type bridge
ip link set docker0 up

# 重启 Docker 服务
/etc/init.d/docker restart
```

**防止复发**：把重建 docker0 的命令加到 `/etc/rc.local` 或 `/etc/hotplug.d/net/40-docker-bridge`。

---

## 调试工具

### 网络命名空间模拟访客

```bash
ip netns add vv
ip link add vv0 type veth peer name vv0h
ip link set vv0h netns vv
ip link set vv0 master br-guest
ip link set vv0 up
ip -n vv addr add 192.168.8.199/24 dev vv0h
ip -n vv link set vv0h up
ip -n vv route add default via 192.168.8.1

# 测试
ip netns exec vv curl -s --max-time 5 http://192.168.8.1:8090/health
ip netns exec vv curl -s --max-time 3 http://8.8.8.8/  # 应失败
ip netns exec vv curl -s --max-time 3 http://192.168.2.1/  # 应失败

# 清理
ip netns del vv; ip link del vv0
```

### 查看 dnsmasq 租约

```bash
# 访客 MAC 和 IP 对应关系
cat /tmp/dhcp.leases
# 格式: <过期时间> <MAC> <IP> <主机名> <Client-ID>
```

### 抓包

```bash
# 抓取 Guest 网桥上的 DNS 流量
tcpdump -i br-guest -n port 53

# 抓取到留言板 8090 的流量
tcpdump -i br-guest -n port 8090

# 容器内抓包
docker exec visitor-board tcpdump -i any -n port 80
```
