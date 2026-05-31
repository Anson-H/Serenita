# Serenita v0.1.0 账号注册与登录技术设计

> 文档状态：当前执行 / 当前执行版本
>
> 关联产品需求文档：[账号注册与登录 产品需求文档](../prd/auth.md)
>
> 技术设计索引：[README.md](./README.md)

## 1. 接口清单

| 接口 | 说明 |
| --- | --- |
| `POST /api/auth/sign_up` | 注册 |
| `POST /api/auth/sign_in` | 登录 |
| `GET /api/auth/session` | 会话恢复 |
| `POST /api/auth/sign_out` | 退出登录 |

前端认证页面路由：

| 路由 | 说明 |
| --- | --- |
| `/sign_in` | 登录页 |
| `/sign_up` | 注册页 |
| `/` | 登录成功后的患者主工作台 |
| `/chat/{session_id}` | 受登录保护的指定会话页 |
| `/favorites` | 受登录保护的我的收藏页 |
| `/setting` | 受登录保护的账号设置页 |

未登录访问 `/`、`/chat/{session_id}`、`/favorites` 或 `/setting` 时跳回 `/sign_in`。已登录访问 `/sign_in` 或 `/sign_up` 时跳到 `/`。账号设置从左下角账号按钮直接进入 `/setting`，并复用患者主工作台外壳；退出登录入口位于账号设置页一级导航。登录页与注册页的切换必须同步更新浏览器 URL。

## 2. 注册 接口

```http
POST /api/auth/sign_up
Content-Type: application/json
```

请求字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `account` | string | 是 | 登录账号 |
| `user_name` | string | 是 | 用户名称 |
| `password` | string | 是 | 密码 |
| `confirm_password` | string | 是 | 确认密码 |

校验要求：

- `account` 在服务端去除首尾空白后校验，并按不区分大小写方式匹配。
- 建议使用统一小写后的值作为规范化账号目录名和唯一索引。
- `account` 只允许英文字母、数字、下划线和短横线，长度为 1-20 个字符。
- 不满足格式或长度限制时返回 `INVALID_REQUEST`，不得创建账号记录或账号私有目录。
- 所有文件路径中的账号目录名必须使用通过校验后的规范化 `account`。
- `user_name` 不能为空，且不能包含任何空白字符。
- 密码不能为空，不设置长度限制，不做复杂度要求。
- `confirm_password` 必须与 `password` 完全一致。
- 账号已存在时返回 `ACCOUNT_EXISTS`，不得覆盖已有登录凭证或账号私有目录。
- 密码不得明文保存。

请求示例：

```json
{
  "account": "demo_patient",
  "user_name": "陈女士",
  "password": "********",
  "confirm_password": "********"
}
```

响应字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `authenticated` | boolean | 注册后自动登录时为 `true` |
| `account` | string | 规范化后的账号 |
| `user_name` | string | 用户名称 |
| `session_token` | string | 会话 token |
| `expires_at` | string | 会话过期时间 |

响应示例：

```json
{
  "authenticated": true,
  "account": "demo_patient",
  "user_name": "陈女士",
  "session_token": "sess_8f2b7c9d",
  "expires_at": "2026-10-23T10:15:00+08:00"
}
```

注册成功后：

- 在 `all_users/auth/auth_info.db` 中写入凭证记录。
- 初始化 `{account}/` 账号私有目录。
- 创建当前会话记录。
- 响应体返回 `session_token`，同源 Web 部署场景下同时设置 HttpOnly、SameSite=Lax 的会话 Cookie。

## 3. 登录 接口

```http
POST /api/auth/sign_in
Content-Type: application/json
```

请求字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `account` | string | 是 | 登录账号 |
| `password` | string | 是 | 密码 |

校验要求：

- 登录时 `account` 同样先去除首尾空白并按注册规则校验。
- 账号不存在或密码不匹配时返回 `SIGN_IN_FAILED`。
- 密码为空时返回 `INVALID_REQUEST`。
- 登录成功时创建新的会话 token，并初始化账号私有目录。

请求示例：

```json
{
  "account": "demo_patient",
  "password": "********"
}
```

响应示例：

```json
{
  "authenticated": true,
  "account": "demo_patient",
  "user_name": "陈女士",
  "session_token": "sess_8f2b7c9d",
  "expires_at": "2026-10-23T10:15:00+08:00"
}
```

## 4. 会话恢复接口

```http
GET /api/auth/session
```

登录态传递要求：

- Web 同源部署优先使用 HttpOnly Cookie。
- 本地开发、桌面壳或无法使用 Cookie 的客户端可通过 `Authorization: Bearer {session_token}` 调用。
- 服务端保存 `session_token` 的不可逆哈希，不保存明文 token。
- 该接口必须只依赖 Cookie 或 Authorization 头中的 token 定位当前账号。
- 不要求前端在恢复登录态前传入 `account`。
- `session_token` 有效期为 6 个月。
- 当前会话恢复接口会捕获缺失、过期、撤销或查无记录的 token，并统一返回 `authenticated: false`；受保护业务接口在 token 过期时仍可返回 `SESSION_EXPIRED`。

已认证响应示例：

```json
{
  "authenticated": true,
  "account": "demo_patient",
  "user_name": "陈女士",
  "expires_at": "2026-10-23T10:15:00+08:00"
}
```

未认证响应示例：

```json
{
  "authenticated": false
}
```

## 5. 退出登录接口

```http
POST /api/auth/sign_out
```

要求：

- 退出登录由服务端根据当前登录态识别用户身份，无需请求体。
- 若请求携带有效 token，服务端撤销当前 session。
- 响应时删除会话 Cookie。
- 前端清除本地 `session_token`、当前工作台状态、会话列表、收藏列表、当前对话和模型选择状态。

响应示例：

```json
{
  "success": true,
  "message": "已 sign out"
}
```

## 6. Auth 数据存储

Auth 数据位于公共目录：

```text
serenita_files/
  all_users/
    auth/
      auth_info.db
      {account}/session.json
```

当前代码还支持将旧目录 `all_users/login/key_info.db` 和旧账号登录目录迁移到 `all_users/auth/`。旧 cookie 名 `serenita_session_token` 仍可被读取，并在前端本地存储中迁移到 `serenita_auth_session_token`。

`auth_info.db` 至少包含两张表：

### auth_accounts

| 字段 | 说明 |
| --- | --- |
| `account` | 账号标识，主键 |
| `password_hash` | 密码哈希 |
| `user_name` | 用户名称 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

表结构示例：

```sql
CREATE TABLE IF NOT EXISTS auth_accounts (
    account TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    user_name TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### auth_sessions

| 字段 | 说明 |
| --- | --- |
| `session_token_hash` | token 哈希，主键 |
| `account` | 当前账号 |
| `user_name` | 会话创建或同步后的用户名称 |
| `expires_at` | 过期时间 |
| `revoked_at` | 撤销时间，未撤销为空 |
| `created_at` | 创建时间 |
| `updated_at` | 更新时间 |

表结构示例：

```sql
CREATE TABLE IF NOT EXISTS auth_sessions (
    session_token_hash TEXT PRIMARY KEY,
    account TEXT NOT NULL,
    user_name TEXT,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (account) REFERENCES auth_accounts(account)
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_account
ON auth_sessions(account);
```

`session.json` 是账号目录下的当前登录态摘要，至少包含：

- `account`
- `user_name`
- `session_token_hash`
- `authenticated`
- `expires_at`
- `last_login_at`

`session.json` 不得保存明文 `session_token`。

## 7. 前端安全要求

- 密码输入框可使用显示/隐藏切换，但该切换只改变输入控件可见性。
- 前端不得将密码写入日志、URL、查询参数或可持久读取的普通文本配置。
- 登录失败、注册失败和恢复登录态失败均不得展示上一位用户的数据。
