#!/bin/sh
# ============================================================
# Guest WiFi + 留言板网络自动配置脚本
# 在 OpenWrt 路由器 SSH 中执行
# ============================================================
set -e

BOARD_IP="192.168.2.1"   # 路由器 LAN IP（按需修改）
GUEST_SUBNET="192.168.8"
GUEST_IP="${GUEST_SUBNET}.1"
DHCP_START="${GUEST_SUBNET}.100"
DHCP_END="${GUEST_SUBNET}.150"

echo "[1/7] 创建 Guest 接口..."
uci set network.guest=interface
uci set network.guest.proto='static'
uci set network.guest.ipaddr="$GUEST_IP"
uci set network.guest.netmask='255.255.255.0'
uci set network.guest.device='br-guest'
uci commit network

echo "[2/7] 刷新 Guest DHCP..."
uci set dhcp.guest=dhcp
uci set dhcp.guest.interface='guest'
uci set dhcp.guest.start='100'
uci set dhcp.guest.limit='51'
uci set dhcp.guest.leasetime='1h'
uci set dhcp.guest.leasetime='3600'
uci commit dhcp
/etc/init.d/dnsmasq reload

echo "[3/7] 创建 Guest 防火墙区域..."
uci set firewall.guest=zone
uci set firewall.guest.name='guest'
uci set firewall.guest.network='guest'
uci set firewall.guest.input='REJECT'
uci set firewall.guest.output='ACCEPT'
uci set firewall.guest.forward='REJECT'
uci commit firewall

echo "[4/7] 放行 Guest DNS/DHCP/留言板端口..."
uci set firewall.guest_dns=rule
uci set firewall.guest_dns.name='Guest-DNS'
uci set firewall.guest_dns.src='guest'
uci set firewall.guest_dns.dest_port='53'
uci set firewall.guest_dns.proto='udp'
uci set firewall.guest_dns.target='ACCEPT'

uci set firewall.guest_dhcp=rule
uci set firewall.guest_dhcp.name='Guest-DHCP'
uci set firewall.guest_dhcp.src='guest'
uci set firewall.guest_dhcp.dest_port='67'
uci set firewall.guest_dhcp.proto='udp'
uci set firewall.guest_dhcp.target='ACCEPT'

uci set firewall.guest_board80=rule
uci set firewall.guest_board80.name='Guest-Board-HTTP'
uci set firewall.guest_board80.src='guest'
uci set firewall.guest_board80.dest_port='8090'
uci set firewall.guest_board80.proto='tcp'
uci set firewall.guest_board80.target='ACCEPT'

uci set firewall.guest_board443=rule
uci set firewall.guest_board443.name='Guest-Board-HTTPS'
uci set firewall.guest_board443.src='guest'
uci set firewall.guest_board443.dest_port='8091'
uci set firewall.guest_board443.proto='tcp'
uci set firewall.guest_board443.target='ACCEPT'

echo "[5/7] 拒绝 Guest 访问 LAN/WAN..."
uci set firewall.guest_reject_wan=forwarding
uci set firewall.guest_reject_wan.src='guest'
uci set firewall.guest_reject_wan.dest='wan'
uci set firewall.guest_reject_wan.enabled='0'

uci set firewall.guest_reject_lan=forwarding
uci set firewall.guest_reject_lan.src='guest'
uci set firewall.guest_reject_lan.dest='lan'
uci set firewall.guest_reject_lan.enabled='0'
uci commit firewall

echo "[6/7] 添加强制门户 DNAT 规则到 /etc/firewall.user..."
cat >> /etc/firewall.user << 'EOF'

# ========== Visitor Board 强制门户 ==========
# Guest WiFi 80/443 → 留言板容器（host 网络模式）
# 注意：443 只重定向到 HTTPS 端口 8091，不能到 HTTP 8090！
iptables -t nat -A PREROUTING -i br-guest -p tcp --dport 80 \
  -j DNAT --to-destination '"$GUEST_IP"':8090
iptables -t nat -A PREROUTING -i br-guest -p tcp --dport 443 \
  -j DNAT --to-destination '"$GUEST_IP"':8091
EOF
fw4 reload 2>/dev/null || /etc/init.d/firewall reload

echo "[7/7] 确认网络状态..."
echo "  br-guest IP: $(ip addr show br-guest 2>/dev/null | grep 'inet ' | awk '{print $2}')"
echo "  Guest DHCP:   $(uci get dhcp.guest.start 2>/dev/null)-$(uci get dhcp.guest.limit 2>/dev/null)"
echo "  防火墙 guest 区域: $(uci get firewall.guest.name 2>/dev/null)"

echo ""
echo "=== Guest 网络配置完成 ==="
echo "下一步："
echo "  1. 在 LuCI → 网络 → 无线 为 radio0 添加 SSID 'Visitor-Board'，关联 guest 接口"
echo "  2. 确保 br-guest 桥接端口只有无线 AP（不含物理网口 eth0/eth1 等）"
echo "  3. 启动留言板容器: docker run -d --network host ..."
echo "  4. 验证: ip netns exec $(whoami) curl http://$GUEST_IP:8090/health"
