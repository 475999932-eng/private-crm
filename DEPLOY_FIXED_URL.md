# 私域 CRM 固定网址部署（推荐 Render）

## 1) 准备代码
当前目录已包含：
- `crm_multiuser.html`
- `multiuser_crm_server.py`

后端已支持云平台端口变量：`PORT`。

## 2) 上传到 GitHub
1. 新建一个仓库（例如：`private-crm`）
2. 把这两个文件上传到仓库根目录

## 3) 在 Render 创建 Web Service
1. 打开 [https://render.com](https://render.com) 并登录
2. `New` -> `Web Service`
3. 选择你的 GitHub 仓库
4. 配置：
   - `Runtime`: `Python 3`
   - `Build Command`: 留空
   - `Start Command`: `python multiuser_crm_server.py`

## 4) 环境变量（可选但建议）
- `PORT` 不用手动填，Render 会自动注入。

## 5) 部署完成后
Render 会给你一个固定 `https://xxxx.onrender.com` 域名，这就是长期可访问网址。

---

## 生产建议
1. 首次上线后立即注册一个老板账号，再删掉测试账号。
2. 建议改造密码存储为 `bcrypt`（当前是 `sha256`，可用但不够强）。
3. 数据库建议换成托管 PostgreSQL（避免单机 sqlite 文件风险）。

