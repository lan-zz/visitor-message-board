# 🔔 推送平台配置详解

本文档介绍访客留言板支持的四种推送平台：Bark、飞书、企业微信、钉钉。

---

## 工作原理

```
访客提交留言
     │
     ▼
app.py /api/upload
     │
     ▼
push.py → 读取 data/config.json
     │
     ├──▶ platform="bark"     → _push_bark()
     ├──▶ platform="feishu"    → _push_feishu()
     ├──▶ platform="wecom"    → _push_wecom()
     └──▶ platform="dingtalk" → _push_dingtalk()
          │
          ▼
     HTTP POST 到各平台 Webhook
          │
          ▼
     主人手机 / 群聊收到通知
```

---

## 配置文件格式

路径：`/mnt/sda1/message-board/data/config.json`

```json
{
  "enabled": true,
  "platform": "bark",
  "bark": {
    "key": "你的BarkKey"
  },
  "feishu": {
    "webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
  },
  "wecom": {
    "webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx"
  },
  "dingtalk": {
    "webhook": "https://oapi.dingtalk.com/robot/send?access_token=xxx",
    "secret": "SEC...xxx"
  }
}
```

配置后端会自动判断各字段是否存在，**无需填写所有平台**，只需填写选中的那个即可。

---

## ① Bark（推荐国内 iOS 用户）

### 原理

Bark 是一款 iOS App，提供了简单的 HTTP API。
只需一个 Key，即可通过 `api.day.app` 发送推送通知到你的 iPhone。

### 获取 Bark Key

1. 在 iPhone App Store 搜索并安装 **Bark**（免费，无内购）
2. 打开 App → 点击左上角 **头像** → **生成 URL**
3. 复制的 URL 格式如下：

```
https://api.day.app/你的BarkKey/这是推送内容
```

4. 去掉后面的路径，只取中间的 Key：`你的BarkKey`

### 配置

**方式一：后台页面**

1. 访问 `http://192.168.2.1:8090/admin`
2. 勾选「启用推送」
3. 选择「Bark」
4. 粘贴 Key
5. 点击「发送测试」→ 收到通知后「保存配置」

**方式二：直接编辑**

```json
{
  "enabled": true,
  "platform": "bark",
  "bark": {
    "key": "你的BarkKey"
  }
}
```

### 高级参数（可选）

Bark 支持更多参数（声音、图标等），如需可在 config.json 中添加：

```json
{
  "bark": {
    "key": "你的BarkKey",
    "sound": "bell",
    "group": "访客留言",
    "icon": "https://example.com/icon.png"
  }
}
```

---

## ② 飞书

### 原理

飞书群机器人通过 Webhook 接收消息并转发到群里。
无需企业账号，个人飞书群也可以用。

### 创建飞书机器人

1. 在飞书群 → 右上角「···」→「设置」
2. 「群机器人」→「添加机器人」
3. 选择「**自定义机器人**」（最后一个选项，不是「Agent」）
4. 设置机器人名称（如「访客留言通知」）
5. 点击「添加」
6. **复制 Webhook 地址**（格式：`https://open.feishu.cn/open-apis/bot/v2/hook/xxx`）

> ⚠️ Webhook 地址每个群不同，不要泄露给他人。

### 配置

```json
{
  "enabled": true,
  "platform": "feishu",
  "feishu": {
    "webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/你的实际地址"
  }
}
```

### 测试

在 [飞书开放平台消息调试工具](https://open.feishu.cn/document/tools-and-resources/bots/webhook) 可以先测试 Webhook 是否可用。

---

## ③ 企业微信

### 原理

企业微信群机器人通过 Webhook URL 接收消息并转发到群里。
需要创建「企业」（个人可免费创建）或使用已有的企业微信。

### 创建企业微信机器人

1. 打开企业微信 App → 「工作台」→「自建应用」（或网页端）
2. 或直接创建一个「企业微信群」
3. 在群里 → 添加群机器人
4. 复制 Webhook URL（格式：`https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx`）

### 配置

```json
{
  "enabled": true,
  "platform": "wecom",
  "wecom": {
    "webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=你的key"
  }
}
```

---

## ④ 钉钉

### 原理

钉钉群机器人通过 Webhook 接收消息，支持加签验证增强安全性。

### 创建钉钉机器人

1. 打开钉钉群 → 右上角「···」→「群设置」→「智能群助手」
2. 「添加机器人」→「自定义机器人」
3. 设置机器人名称
4. **重要**：开启「加签」可以获得 `SEC` 开头的密钥
5. 复制 Webhook URL 和密钥（如果开启了加签）

### Webhook URL 格式

```
https://oapi.dingtalk.com/robot/send?access_token=你的token
```

### 配置（无加签）

```json
{
  "enabled": true,
  "platform": "dingtalk",
  "dingtalk": {
    "webhook": "https://oapi.dingtalk.com/robot/send?access_token=你的token"
  }
}
```

### 配置（有加签）

```json
{
  "enabled": true,
  "platform": "dingtalk",
  "dingtalk": {
    "webhook": "https://oapi.dingtalk.com/robot/send?access_token=你的token",
    "secret": "SEC你复制的密钥"
  }
}
```

加签原理：
1. 当前毫秒时间戳 + `\n` + 密钥，拼成签名
2. 用 HMAC-SHA256 + Base64 编码
3. 拼到 Webhook URL 的 query 参数中
4. 钉钉服务端用同样方式验证请求来源

---

## 多平台对比

| 平台 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **Bark** | 最简单，消息直达 iPhone 通知栏 | 仅 iOS，Key 暴露等同消息权限 | ⭐⭐⭐⭐⭐ |
| **飞书** | 个人可用，图文丰富 | 消息发到群里，不直达手机通知栏 | ⭐⭐⭐⭐ |
| **企业微信** | 企业可用，生态完善 | 消息到群通知，需关注才能及时看到 | ⭐⭐⭐⭐ |
| **钉钉** | 支持加签，可靠性高 | 需要群管理权限，界面偏商务 | ⭐⭐⭐ |

---

## 推送测试脚本

手动测试各平台推送（需在路由器上执行）：

```bash
# 测试 Bark
curl -X POST https://api.day.app/你的BarkKey \
  -H "Content-Type: application/json" \
  -d '{"title":"测试标题","body":"测试内容","sound":"bell"}'

# 测试飞书
curl -X POST "https://open.feishu.cn/open-apis/bot/v2/hook/你的Webhook" \
  -H "Content-Type: application/json" \
  -d '{"msg_type":"text","content":{"text":"测试内容"}}'

# 测试企业微信
curl -X POST "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=你的Key" \
  -H "Content-Type: application/json" \
  -d '{"msgtype":"text","text":{"content":"测试内容"}}'

# 测试钉钉
curl -X POST "https://oapi.dingtalk.com/robot/send?access_token=你的Token" \
  -H "Content-Type: application/json" \
  -d '{"msgtype":"text","text":{"content":"测试内容"}}'
```
