# Agent Teams System - 密码安全机制说明

## 🔒 密码加密存储机制

### 安全实现

本项目使用 **werkzeug.security** 提供的密码哈希功能，采用业界标准的安全存储方式。

### 加密算法

**使用的算法：PBKDF2 + SHA256**

```python
from werkzeug.security import generate_password_hash, check_password_hash

# 加密密码
password_hash = generate_password_hash('user_password')

# 验证密码
is_valid = check_password_hash(password_hash, 'user_password')
```

### 技术细节

**1. 算法参数**
- **算法**: PBKDF2 (Password-Based Key Derivation Function 2)
- **哈希函数**: SHA256
- **迭代次数**: 260,000 次（默认）
- **盐值长度**: 16 字节随机生成

**2. 存储格式**
```
pbkdf2:sha256:260000$盐值$哈希值
```

**示例：**
```
pbkdf2:sha256:260000$5K8h2ZqN3mXpQwRt$v9Yf3kL7mN1pQwRtYuIp0aSdFgHjKlMnOpQrStUvWxYz
```

**3. 安全特性**
- ✅ **单向加密**: 无法从哈希值逆向还原密码
- ✅ **随机盐值**: 每个用户密码使用不同的盐值
- ✅ **防彩虹表**: 相同密码产生不同的哈希值
- ✅ **防暴力破解**: 高迭代次数增加计算成本
- ✅ **防时序攻击**: 验证时使用常量时间比较

### 代码实现

**User 模型（models.py）**
```python
class User(db.Model):
    # ...
    password_hash = db.Column(db.String(255), nullable=False)

    def set_password(self, password):
        """设置密码（加密存储）"""
        # 使用 PBKDF2-SHA256 加密
        # 自动生成随机盐值
        # 存储: pbkdf2:sha256:260000$salt$hash
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """验证密码"""
        # 提取盐值和算法参数
        # 计算输入密码的哈希
        # 安全比较两个哈希值
        return check_password_hash(self.password_hash, password)
```

### 数据库存储

**数据库表结构**
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,  -- 存储加密后的哈希值
    email VARCHAR(100),
    created_at TIMESTAMP,
    last_login TIMESTAMP
);
```

**存储内容**
- ❌ **不存储**: 明文密码
- ✅ **存储**: 哈希值（包含算法、迭代次数、盐值）

### 验证流程

```
用户输入密码
    ↓
提取数据库中的 password_hash
    ↓
从 password_hash 提取盐值和算法参数
    ↓
对输入密码使用相同参数计算哈希
    ↓
比较两个哈希值是否匹配
    ↓
返回验证结果
```

### 安全性分析

**1. 防御彩虹表攻击**
- 每个密码使用随机盐值
- 相同密码产生不同哈希值
- 攻击者需要为每个密码单独构建彩虹表

**2. 防御暴力破解**
- 260,000 次迭代大幅增加计算成本
- 每次尝试需要 ~100ms
- 破解 8 位强密码需要数年时间

**3. 数据库泄露防护**
- 即使数据库被窃取
- 攻击者无法还原原始密码
- 只能尝试暴力破解

### 密码强度要求

**建议密码策略：**
- 最小长度: 8 位
- 包含: 大小写字母、数字、特殊字符
- 避免常见词汇和规律
- 定期更换（建议 90 天）

### 示例演示

**1. 创建用户**
```python
from models import User

user = User(username='alice', email='alice@example.com')
user.set_password('MySecureP@ss123')  # ✅ 自动加密
db.session.add(user)
db.session.commit()

# 数据库中存储:
# password_hash = "pbkdf2:sha256:260000$AbCdEfGhIjKlMnOp$v9Yf3kL7mN1p..."
```

**2. 验证密码**
```python
# 正确密码
user.check_password('MySecureP@ss123')  # → True

# 错误密码
user.check_password('wrong_password')   # → False
```

**3. 数据库查询**
```sql
SELECT username, password_hash FROM users WHERE username = 'alice';

-- 结果:
-- username: alice
-- password_hash: pbkdf2:sha256:260000$AbCdEfGhIjKlMnOp$v9Yf3kL7mN1p...
-- ❌ 无法从 password_hash 还原原始密码
```

### 常见问题

**Q1: 为什么不能解密密码？**
A: PBKDF2 是单向哈希函数，只能从密码生成哈希值，不能从哈希值还原密码。这是密码存储的标准做法。

**Q2: 用户忘记密码怎么办？**
A: 系统提供"重置密码"功能，而不是"找回密码"。管理员重置密码后，旧密码哈希被替换。

**Q3: 如何修改密码强度？**
A: 在前端和后端添加密码强度验证：
```python
import re

def validate_password_strength(password):
    if len(password) < 8:
        return False
    if not re.search(r'[A-Z]', password):
        return False
    if not re.search(r'[a-z]', password):
        return False
    if not re.search(r'[0-9]', password):
        return False
    return True
```

**Q4: 迭代次数是否越多越好？**
A: 需要平衡安全性和性能。当前 260,000 次是 werkzeug 默认值，可在 100-500ms 内完成验证，既安全又不影响用户体验。

**Q5: 是否需要定期更换盐值？**
A: 不需要。每次设置密码时自动生成新盐值，已足够安全。重点是鼓励用户定期更换密码。

### 相关文档

- [werkzeug.security 文档](https://werkzeug.palletsprojects.com/en/latest/utils/#werkzeug.security.generate_password_hash)
- [PBKDF2 标准 (RFC 2898)](https://tools.ietf.org/html/rfc2898)
- [OWASP 密码存储指南](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)

---

**文档版本**: 1.0
**更新时间**: 2026-03-12
