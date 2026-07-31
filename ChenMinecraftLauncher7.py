#!/usr/bin/env python3
"""Chen Minecraft Launcher 7 (CML7)
©2026 童顺 cn19491001cn@yeah.net admin@amateurradio.org.cn"""

import os, sys, json, subprocess, threading, time, shutil
import getpass, tarfile, logging, re, uuid, platform, secrets, string
import urllib.request, urllib.parse, urllib.error
import zipfile, hashlib, io, stat, base64
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any

# ============================================================
# 颜色定义
# ============================================================
class C:
    RESET="\033[0m"; BOLD="\033[1m"; DIM="\033[2m"
    RED="\033[31m"; GREEN="\033[32m"; YELLOW="\033[33m"
    BLUE="\033[34m"; MAGENTA="\033[35m"; CYAN="\033[36m"
    WHITE="\033[37m"; GRAY="\033[90m"
    BG_RED="\033[41m"; BG_GREEN="\033[42m"; BG_YELLOW="\033[43m"
    ORANGE="\033[38;5;208m"; TEAL="\033[38;5;51m"
    BRIGHT_GREEN="\033[92m"; BRIGHT_BLUE="\033[94m"; BRIGHT_CYAN="\033[96m"
    BROWN="\033[38;5;130m"; PINK="\033[38;5;213m"

# Windows 下启用 ANSI 颜色支持
if os.name == 'nt':
    os.system('color')

# ============================================================
# 日志系统
# ============================================================
# 日志级别对应的颜色映射
LOG_COLORS = {
    'DEBUG': C.GRAY, 'INFO': C.CYAN,
    'WARNING': C.YELLOW, 'ERROR': C.RED,
    'CRITICAL': C.BG_RED + C.WHITE
}

class ColoredFormatter(logging.Formatter):
    """带颜色的日志格式化器"""
    def format(self, r):
        c = LOG_COLORS.get(r.levelname, C.WHITE)
        return f"{C.DIM}[{datetime.now().strftime('%H:%M:%S')}]{C.RESET} {c}[{r.levelname}]{C.RESET} {r.getMessage()}"

# 创建日志记录器
logger = logging.getLogger("MC")
logger.setLevel(logging.DEBUG)
_h = logging.StreamHandler(sys.stdout)
_h.setFormatter(ColoredFormatter())
logger.addHandler(_h)

# 屏蔽第三方库的冗余日志
for _n in ("urllib3", "requests"):
    logging.getLogger(_n).setLevel(logging.WARNING)
    logging.getLogger(_n).propagate = False

# ============================================================
# 全局状态管理
# ============================================================
class State:
    """全局状态，保存启动器运行时的所有上下文"""

    def __init__(self):
        # 基础路径
        self.root_dir = os.path.dirname(os.path.abspath(__file__))
        self.current_dir = self.root_dir

        # Minecraft 相关目录
        self.minecraft_dir = os.path.join(self.root_dir, ".minecraft")
        self.versions_dir = os.path.join(self.minecraft_dir, "versions")
        self.libraries_dir = os.path.join(self.minecraft_dir, "libraries")
        self.assets_dir = os.path.join(self.minecraft_dir, "assets")
        self.saves_dir = os.path.join(self.minecraft_dir, "saves")
        self.mods_dir = os.path.join(self.minecraft_dir, "mods")

        # 启动器自身目录
        self.config_dir = os.path.join(self.root_dir, "config")
        self.runtime_dir = os.path.join(self.root_dir, "runtime")
        self.instances_dir = os.path.join(self.root_dir, "instances")
        self.accounts_dir = os.path.join(self.config_dir, "accounts")

        # 认证文件
        self.auth_file = os.path.join(self.config_dir, "auth.json")

        # 查找 Java
        self.java_path = self._find_java()

        # 登录状态
        self.logged_in = False
        self.username = ""
        self.uuid_str = ""
        self.access_token = ""
        self.auth_type = ""
        self.ms_refresh_token = ""
        self.mc_expires_at = 0

        # 游戏进程
        self.minecraft_process = None
        self.game_running = False

        # 版本清单缓存
        self.version_manifest = None

        # 环境管理器（延迟初始化）
        self._env_manager = None

        # 确保目录存在
        self._ensure_dirs()

    def get_env_manager(self):
        """获取环境管理器（延迟初始化）"""
        if self._env_manager is None:
            self._env_manager = EnvironmentManager(self)
        return self._env_manager

    def _find_java(self):
        """在常见位置查找 Java 可执行文件"""
        jh = os.environ.get("JAVA_HOME", "")
        if jh:
            for exe in ["bin/java.exe", "bin/java"]:
                p = os.path.join(jh, exe)
                if os.path.isfile(p):
                    return p
        p = shutil.which("java")
        if p:
            return p
        for p in [
            "/usr/bin/java", "/usr/local/bin/java",
            "/usr/lib/jvm/java-21-openjdk/bin/java",
            "/usr/lib/jvm/java-17-openjdk/bin/java",
            "/usr/lib/jvm/java-8-openjdk/bin/java",
            "/opt/homebrew/opt/openjdk/bin/java",
        ]:
            if os.path.isfile(p):
                return p
        return "java"

    def _ensure_dirs(self):
        """确保所有必要目录存在"""
        for d in [
            self.minecraft_dir, self.versions_dir, self.libraries_dir,
            self.assets_dir, self.saves_dir, self.mods_dir,
            self.config_dir, self.runtime_dir, self.instances_dir,
            self.accounts_dir,
        ]:
            os.makedirs(d, exist_ok=True)

    def get_cwd(self):
        """获取当前工作目录的显示字符串"""
        if self.current_dir == self.root_dir:
            return "/"
        return "/" + os.path.relpath(self.current_dir, self.root_dir).replace(os.sep, "/")

# ============================================================
# 认证模块 - Microsoft OAuth2 设备代码流
# ============================================================
class Auth:
    """Minecraft Microsoft OAuth2 认证（设备代码流）"""

    CLIENT_ID = "00000000402B5328"#警告：正版登录时不要使用这个 Client ID，这个是测试用的，如果你将其用作游戏，将会违反微软的政策。请将其换成你自己的 Client ID。在 https://portal.azure.com上可以免费申请 Client ID，不会可以问AI。CML、CML 的作者对用户因使用测试 ID 进行游戏而导致的账号封禁或其他任何法律后果不承担任何责任。
    TENANT = "consumers"
    SCOPE = "XboxLive.signin offline_access"

    U_DEV = "https://login.microsoftonline.com/" + TENANT + "/oauth2/v2.0/devicecode"
    U_TOK = "https://login.microsoftonline.com/" + TENANT + "/oauth2/v2.0/token"
    U_XBL = "https://user.auth.xboxlive.com/user/authenticate"
    U_XSTS = "https://xsts.auth.xboxlive.com/xsts/authorize"
    U_MC = "https://api.minecraftservices.com/authentication/login_with_xbox"
    U_PROF = "https://api.minecraftservices.com/minecraft/profile"

    @staticmethod
    def _post_json(url, data, headers=None):
        """发送 JSON POST 请求"""
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=h, method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())

    @staticmethod
    def _post_form(url, data):
        """发送表单格式 POST 请求"""
        req = urllib.request.Request(
            url, data=urllib.parse.urlencode(data).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())

    @staticmethod
    def request_device_code():
        """向 Microsoft 申请设备代码"""
        try:
            r = Auth._post_form(Auth.U_DEV, {"client_id": Auth.CLIENT_ID, "scope": Auth.SCOPE})
            return True, "OK", r
        except urllib.error.HTTPError as e:
            try:
                return False, json.loads(e.read().decode()).get("error_description", str(e)), {}
            except Exception:
                return False, f"HTTP {e.code}: {e.reason}", {}
        except Exception as e:
            return False, str(e), {}

    @staticmethod
    def poll_for_token(device_code, interval, expires_in):
        """轮询等待用户完成认证"""
        deadline = time.time() + expires_in
        last_err = ""
        while time.time() < deadline:
            try:
                r = Auth._post_form(Auth.U_TOK, {
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "client_id": Auth.CLIENT_ID,
                    "device_code": device_code,
                })
                return True, "OK", r
            except urllib.error.HTTPError as e:
                try:
                    err = json.loads(e.read().decode())
                    code = err.get("error", "")
                    if code == "authorization_pending":
                        last_err = "等待用户授权中..."
                    elif code == "slow_down":
                        interval += 5
                        last_err = "降低轮询频率..."
                    elif code == "access_denied":
                        return False, "用户拒绝了授权", {}
                    elif code == "expired_token":
                        return False, "设备代码已过期", {}
                    else:
                        last_err = err.get("error_description", code)
                except Exception:
                    last_err = f"HTTP {e.code}"
            except Exception as e:
                last_err = str(e)
            time.sleep(interval)
        return False, f"等待授权超时（最后状态: {last_err}）", {}

    @staticmethod
    def refresh_token(refresh_token):
        """使用刷新令牌获取新的访问令牌"""
        try:
            r = Auth._post_form(Auth.U_TOK, {
                "client_id": Auth.CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            })
            return True, "OK", r
        except Exception as e:
            return False, str(e), {}

# ============================================================
# 账号本地密码管理
# ============================================================
class AccountStore:
    """
    管理启动器本地账号密码。
    每个账号独立存储，密码使用 PBKDF2-HMAC-SHA256 加密。
    存储位置: config/accounts/<用户名>.json
    """

    # 加密参数
    KDF_ITERATIONS = 200000  # PBKDF2 迭代次数
    SALT_SIZE = 16           # 盐值长度（字节）
    KEY_SIZE = 32            # 派生密钥长度（字节）

    @staticmethod
    def _account_path(username, accounts_dir):
        """获取账号文件的存储路径"""
        safe = re.sub(r'[^\w.-]', '_', username)
        return os.path.join(accounts_dir, safe + ".json")

    @staticmethod
    def _hash_password(password, salt=None):
        """
        使用 PBKDF2-HMAC-SHA256 对密码进行哈希。
        返回 (salt_b64, hash_b64) 元组。
        """
        if salt is None:
            salt = os.urandom(AccountStore.SALT_SIZE)
        key = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt,
            AccountStore.KDF_ITERATIONS,
            AccountStore.KEY_SIZE
        )
        return base64.b64encode(salt).decode(), base64.b64encode(key).decode()

    @staticmethod
    def account_exists(username, accounts_dir):
        """检查某账号是否已在本地注册"""
        path = AccountStore._account_path(username, accounts_dir)
        return os.path.exists(path)

    @staticmethod
    def create_account(username, password, accounts_dir):
        """
        首次注册账号并设置密码。
        要求密码非空，内部会验证两遍一致性（由调用方负责）。
        返回 (success, message)
        """
        if not password:
            return False, "密码不能为空"
        if AccountStore.account_exists(username, accounts_dir):
            return False, "账号已存在，请使用 'lgn' 登录或修改密码"

        salt_b64, hash_b64 = AccountStore._hash_password(password)
        data = {
            "username": username,
            "salt": salt_b64,
            "hash": hash_b64,
            "iterations": AccountStore.KDF_ITERATIONS,
            "has_password": True,
            "created_at": datetime.now().isoformat(),
        }
        path = AccountStore._account_path(username, accounts_dir)
        os.makedirs(accounts_dir, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        return True, f"账号 '{username}' 已创建并设好密码"

    @staticmethod
    def verify_password(username, password, accounts_dir):
        """
        验证账号密码是否正确。
        返回 (success, message, account_data)
        """
        path = AccountStore._account_path(username, accounts_dir)
        if not os.path.exists(path):
            return False, "账号不存在，请先注册", None

        with open(path, 'r') as f:
            data = json.load(f)

        if not data.get("has_password", True):
            return True, "该账号未设置密码", data

        salt = base64.b64decode(data["salt"])
        stored_hash = data["hash"]
        _, computed_hash = AccountStore._hash_password(password, salt)
        if computed_hash == stored_hash:
            return True, "密码正确", data
        else:
            return False, "密码错误", None

    @staticmethod
    def change_password(username, old_password, new_password, accounts_dir):
        """
        修改账号密码。
        - 如果 old_password 为空且账号当前有密码 → 失败（必须先验证旧密码）
        - 如果 new_password 为空 → 关闭密码（has_password=false）
        - 否则 → 更改密码
        返回 (success, message)
        """
        path = AccountStore._account_path(username, accounts_dir)
        if not os.path.exists(path):
            return False, "账号不存在"

        with open(path, 'r') as f:
            data = json.load(f)

        # 如果当前有密码，必须先验证旧密码
        if data.get("has_password", True):
            if not old_password:
                return False, "该账号已设置密码，必须输入旧密码才能修改"
            salt = base64.b64decode(data["salt"])
            _, computed = AccountStore._hash_password(old_password, salt)
            if computed != data["hash"]:
                return False, "旧密码错误"

        # 关闭密码
        if not new_password:
            data["has_password"] = False
            data.pop("salt", None)
            data.pop("hash", None)
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            return True, f"账号 '{username}' 的密码已关闭"

        # 设置新密码
        salt_b64, hash_b64 = AccountStore._hash_password(new_password)
        data["salt"] = salt_b64
        data["hash"] = hash_b64
        data["has_password"] = True
        data["iterations"] = AccountStore.KDF_ITERATIONS
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        return True, f"账号 '{username}' 的密码已更新"

    @staticmethod
    def delete_account(username, accounts_dir):
        """删除账号本地记录"""
        path = AccountStore._account_path(username, accounts_dir)
        if os.path.exists(path):
            os.remove(path)
            return True, f"账号 '{username}' 已删除"
        return False, "账号不存在"

    @staticmethod
    def list_accounts(accounts_dir):
        """列出所有已注册的本地账号"""
        if not os.path.isdir(accounts_dir):
            return []
        accounts = []
        for f in sorted(os.listdir(accounts_dir)):
            if f.endswith(".json"):
                try:
                    with open(os.path.join(accounts_dir, f), 'r') as fh:
                        data = json.load(fh)
                    accounts.append({
                        "username": data.get("username", f[:-5]),
                        "has_password": data.get("has_password", True),
                        "created_at": data.get("created_at", ""),
                    })
                except Exception:
                    pass
        return accounts


def _ask_login_type():
    """
    询问用户登录方式。
    返回 'msa'（正版）或 'offline'（离线）。
    """
    while True:
        choice = input(
            f"登录方式: [1] Microsoft 正版  [2] 离线模式  [q] 取消: "
        ).strip().lower()
        if choice == '1' or choice == 'msa':
            return 'msa'
        elif choice == '2' or choice == 'offline':
            return 'offline'
        elif choice == 'q' or choice == 'quit':
            return None
        else:
            print(f"{C.RED}无效选择，请输入 1、2 或 q。{C.RESET}")

# ============================================================
# 下载引擎 - 支持断点续传、校验和、重试
# ============================================================
class DownloadEngine:
    """资源下载引擎（断点续传 + SHA 校验 + 自动重试 + 进度条）"""

    def __init__(self, max_retries=3):
        self.max_retries = max_retries

    def download(self, url, dest, sha1=None, sha256=None, progress=True):
        """下载文件，支持断点续传和校验"""
        os.makedirs(os.path.dirname(dest) if os.path.dirname(dest) else ".", exist_ok=True)
        tmp = dest + ".part"
        offset = 0
        if os.path.exists(tmp):
            offset = os.path.getsize(tmp)

        for attempt in range(self.max_retries):
            try:
                req = urllib.request.Request(url)
                if offset > 0:
                    req.add_header("Range", f"bytes={offset}-")

                with urllib.request.urlopen(req, timeout=60) as resp:
                    code = resp.getcode()
                    total = offset
                    if code == 206:
                        cl = resp.headers.get("Content-Length")
                        total += int(cl) if cl else offset
                    elif code == 200:
                        cl = resp.headers.get("Content-Length")
                        total = int(cl) if cl else 0
                        offset = 0
                        if os.path.exists(tmp):
                            os.remove(tmp)

                    mode = "ab" if offset > 0 else "wb"
                    with open(tmp, mode) as f, ProgressBar(total) as bar:
                        if offset > 0:
                            bar.update(offset)
                        while True:
                            chunk = resp.read(64 * 1024)
                            if not chunk:
                                break
                            f.write(chunk)
                            bar.update(len(chunk))

                if sha1:
                    h = hashlib.sha1()
                    with open(tmp, "rb") as f:
                        while True:
                            c = f.read(1024*1024)
                            if not c:
                                break
                            h.update(c)
                    if h.hexdigest().lower() != sha1.lower():
                        raise ValueError(f"SHA1 校验失败: 期望 {sha1}, 实际 {h.hexdigest()}")

                if sha256:
                    h = hashlib.sha256()
                    with open(tmp, "rb") as f:
                        while True:
                            c = f.read(1024*1024)
                            if not c:
                                break
                            h.update(c)
                    if h.hexdigest().lower() != sha256.lower():
                        raise ValueError(f"SHA256 校验失败")

                shutil.move(tmp, dest)
                return True, "OK"
            except Exception as e:
                logger.warning(f"下载尝试 {attempt+1} 失败: {e}")
                time.sleep(2 ** attempt)

        return False, f"重试 {self.max_retries} 次后仍失败"

    def verify_file(self, path, sha1=None, sha256=None):
        """校验已存在文件的哈希值"""
        if not os.path.exists(path):
            return False, "文件不存在"
        if sha1:
            h = hashlib.sha1()
            with open(path, "rb") as f:
                while True:
                    c = f.read(1024*1024)
                    if not c:
                        break
                    h.update(c)
            if h.hexdigest().lower() != sha1.lower():
                return False, "SHA1 校验失败"
        if sha256:
            h = hashlib.sha256()
            with open(path, "rb") as f:
                while True:
                    c = f.read(1024*1024)
                    if not c:
                        break
                    h.update(c)
            if h.hexdigest().lower() != sha256.lower():
                return False, "SHA256 校验失败"
        return True, "OK"


class ProgressBar:
    """简单的命令行进度条"""

    def __init__(self, total, width=40):
        self.total = total
        self.width = width
        self.done = 0
        self.start = time.time()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        sys.stdout.write("\n")
        sys.stdout.flush()

    def update(self, n):
        self.done += n
        if self.total > 0:
            pct = min(self.done / self.total, 1.0)
        else:
            pct = 0
        filled = int(self.width * pct)
        bar = "=" * filled + "-" * (self.width - filled)
        elapsed = max(time.time() - self.start, 0.1)
        speed = self.done / elapsed / 1024
        sys.stdout.write(f"\r[{bar}] {pct*100:.1f}% ({self.done/1024:.0f}KB, {speed:.0f}KB/s)")
        sys.stdout.flush()

# ============================================================
# 模组元数据解析
# ============================================================
class ModMetadata:
    """解析各种格式的模组元数据"""

    @staticmethod
    def parse_jar(jar_path):
        """从 .jar 文件中提取模组元数据"""
        if not os.path.exists(jar_path):
            return None
        mods = []
        try:
            with zipfile.ZipFile(jar_path, 'r') as z:
                names = z.namelist()

                # Fabric 模组
                if "fabric.mod.json" in names:
                    data = json.loads(z.read("fabric.mod.json").decode())
                    mods.append({
                        "name": data.get("name", "未知"),
                        "id": data.get("id", ""),
                        "version": data.get("version", ""),
                        "type": "fabric",
                        "depends": data.get("depends", {}),
                        "conflicts": data.get("conflicts", {}),
                        "breaks": data.get("breaks", {}),
                        "recommends": data.get("recommends", {}),
                    })

                # Quilt 模组
                if "quilt.mod.json" in names:
                    data = json.loads(z.read("quilt.mod.json").decode())
                    qm = data.get("quilt_loader", {})
                    mods.append({
                        "name": qm.get("metadata", {}).get("name", "未知"),
                        "id": qm.get("id", ""),
                        "version": qm.get("version", ""),
                        "type": "quilt",
                        "depends": qm.get("depends", {}),
                        "conflicts": qm.get("conflicts", {}),
                    })

                # Forge mods.toml
                for n in names:
                    if n.endswith("mods.toml") or n == "META-INF/mods.toml":
                        content = z.read(n).decode(errors='ignore')
                        mods.append(ModMetadata._parse_forge_toml(content))
                        break

                # mcmod.info（旧版 Forge）
                if "mcmod.info" in names:
                    data = json.loads(z.read("mcmod.info").decode())
                    if isinstance(data, list):
                        data = data[0]
                    mods.append({
                        "name": data.get("name", "未知"),
                        "id": data.get("modid", ""),
                        "version": data.get("version", ""),
                        "type": "forge_legacy",
                    })
        except Exception as e:
            logger.debug(f"解析模组失败 {jar_path}: {e}")

        return mods

    @staticmethod
    def _parse_forge_toml(content):
        """解析 Forge 的 mods.toml 格式"""
        mod = {"type": "forge", "depends": {}, "conflicts": {}}
        current_section = None
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[[") and line.endswith("]]"):
                current_section = line[2:-2].strip()
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"')
                if current_section == "mods":
                    if k == "modId":
                        mod["id"] = v
                    elif k == "version":
                        mod["version"] = v
                    elif k == "displayName":
                        mod["name"] = v
                elif current_section == "dependencies":
                    if k == "modId":
                        mod["depends"]["forge"] = v
        return mod

# ============================================================
# 依赖解析器
# ============================================================
class DependencyResolver:
    """构建模组依赖图，检测循环依赖和版本冲突"""

    def __init__(self):
        self.mods = {}
        self.graph = {}
        self.conflicts = {}

    def add_mod(self, mod_info):
        mid = mod_info.get("id", "")
        if not mid:
            return
        self.mods[mid] = mod_info
        self.graph[mid] = list(mod_info.get("depends", {}).keys())
        self.conflicts[mid] = list(mod_info.get("conflicts", {}).keys())

    def resolve(self):
        visited = set()
        visiting = set()
        order = []
        errors = []

        def dfs(node, path):
            if node in visiting:
                errors.append(f"检测到循环依赖: {' -> '.join(path + [node])}")
                return
            if node in visited:
                return
            visiting.add(node)
            for dep in self.graph.get(node, []):
                if dep in self.mods:
                    dfs(dep, path + [node])
            visiting.discard(node)
            visited.add(node)
            order.append(node)

        for mid in list(self.mods.keys()):
            if mid not in visited:
                dfs(mid, [])

        return order, errors

    def check_conflicts(self):
        issues = []
        installed = set(self.mods.keys())
        skip_deps = {"minecraft", "java", "forge", "fabricloader",
                     "fabric-api", "quilt_loader", "quilted_fabric_api"}

        for mid, mod in self.mods.items():
            for dep_id in mod.get("depends", {}):
                if dep_id not in installed and dep_id not in skip_deps:
                    issues.append({
                        "type": "missing_dep",
                        "mod": mid,
                        "detail": f"需要 {dep_id} 但未安装"
                    })
            for cf_id in mod.get("conflicts", {}):
                if cf_id in installed:
                    issues.append({
                        "type": "conflict",
                        "mod": mid,
                        "detail": f"与 {cf_id} 冲突（两者均已安装）"
                    })
        return issues

# ============================================================
# 环境管理器
# ============================================================
class EnvironmentManager:
    """自动检测并安装 Java、Git、C/C++ 编译器、Python 依赖"""

    def __init__(self, state):
        self.state = state
        self.java_versions_dir = os.path.join(state.runtime_dir, "java")
        os.makedirs(self.java_versions_dir, exist_ok=True)

        self.java_recommendations = {
            "1.20.5": 21, "1.21": 21, "1.22": 21,
            "1.17": 17, "1.18": 17, "1.19": 17, "1.20": 17,
            "1.12": 8, "1.13": 8, "1.14": 8, "1.15": 8, "1.16": 8,
        }

        self.loader_java_req = {
            "forge": {"min": 8, "recommended": 17},
            "fabric": {"min": 8, "recommended": 17},
            "quilt": {"min": 8, "recommended": 17},
            "neoforge": {"min": 17, "recommended": 21},
            "liteloader": {"min": 8, "recommended": 8},
            "optifine": {"min": 8, "recommended": 17},
        }

    def detect_platform(self):
        """检测操作系统和 CPU 架构"""
        sysname = platform.system().lower()
        arch = platform.machine().lower()

        if "windows" in sysname:
            os_name = "windows"
        elif "darwin" in sysname:
            os_name = "macos"
        else:
            os_name = "linux"

        if "aarch64" in arch or "arm64" in arch:
            arch_name = "aarch64"
        elif "arm" in arch:
            arch_name = "arm"
        elif "x86_64" in arch or "amd64" in arch:
            arch_name = "x64"
        else:
            arch_name = "x86"

        return os_name, arch_name

    def recommended_java(self, mc_version=None, loader=None):
        """获取推荐 Java 版本"""
        ver = 17
        if mc_version:
            for prefix, java_ver in sorted(self.java_recommendations.items(), reverse=True):
                if mc_version.startswith(prefix):
                    ver = java_ver
                    break
        if loader and loader.lower() in self.loader_java_req:
            req = self.loader_java_req[loader.lower()]
            ver = max(ver, req["recommended"])
        return ver

    def list_installed_javas(self):
        """列出所有已安装的 Java 版本"""
        javas = []
        if not os.path.exists(self.java_versions_dir):
            return javas
        for d in sorted(os.listdir(self.java_versions_dir)):
            jhome = os.path.join(self.java_versions_dir, d)
            for exe in ["bin/java.exe", "bin/java"]:
                jbin = os.path.join(jhome, exe)
                if os.path.isfile(jbin):
                    try:
                        out = subprocess.run([jbin, "-version"], capture_output=True, text=True, timeout=10)
                        ver_str = (out.stdout + out.stderr).strip().splitlines()[0]
                    except Exception:
                        ver_str = "未知"
                    javas.append({"name": d, "path": jbin, "version": ver_str})
                    break
        return javas

    def find_java(self, mc_version=None, loader=None):
        """查找满足版本要求的最佳 Java"""
        needed = self.recommended_java(mc_version, loader)
        installed = self.list_installed_javas()
        for j in installed:
            vstr = j["version"]
            m = re.search(r'(\d+)', vstr)
            if m:
                major = int(m.group(1))
                if "1.8" in vstr or "1.7" in vstr:
                    major = 8
                if major >= needed:
                    return j["path"]
        return self.state.java_path

    def install_java(self, version=17, progress_cb=None):
        """从 Adoptium Temurin 下载并安装 Java"""
        os_name, arch = self.detect_platform()
        api_arch = arch

        api_url = f"https://api.adoptium.net/v3/assets/latest/{version}/hotspot"
        try:
            req = urllib.request.Request(api_url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode())
        except Exception as e:
            return False, f"无法访问 Adoptium API: {e}"

        target = None
        for item in data:
            bin_info = item.get("binary", {})
            if bin_info.get("os", "").lower() == os_name and bin_info.get("architecture", "").lower() == api_arch:
                target = item
                break

        if not target:
            for item in data:
                if item.get("binary", {}).get("os", "").lower() == os_name:
                    target = item
                    break

        if not target:
            return False, f"未找到 Java {version} 的 {os_name}/{arch} 版本"

        binary = target["binary"]
        pkg = binary.get("package", {})
        url = pkg.get("link", "")
        sha256 = pkg.get("checksum", "")
        filename = pkg.get("name", f"java{version}.tar.gz")

        if not url:
            return False, "无可用下载链接"

        dest_dir = os.path.join(self.java_versions_dir, f"temurin-{version}")
        if os.path.exists(dest_dir):
            shutil.rmtree(dest_dir)
        os.makedirs(dest_dir, exist_ok=True)
        dest_file = os.path.join(dest_dir, filename)

        logger.info(f"正在从 Adoptium 下载 Java {version}...")
        dl = DownloadEngine()
        ok, msg = dl.download(url, dest_file, sha256=sha256, progress=True)
        if not ok:
            return False, f"下载失败: {msg}"

        logger.info("正在解压 Java...")
        if filename.endswith((".tar.gz", ".tgz")):
            with tarfile.open(dest_file, "r:gz") as t:
                extract_tmp = os.path.join(dest_dir, "_extract")
                os.makedirs(extract_tmp, exist_ok=True)
                t.extractall(extract_tmp)
                for item in os.listdir(extract_tmp):
                    item_path = os.path.join(extract_tmp, item)
                    if os.path.isdir(item_path) and ("jdk" in item.lower() or "jre" in item.lower()):
                        for sub in os.listdir(item_path):
                            shutil.move(os.path.join(item_path, sub), os.path.join(dest_dir, sub))
                        break
                shutil.rmtree(extract_tmp, ignore_errors=True)
        elif filename.endswith(".zip"):
            with zipfile.ZipFile(dest_file, 'r') as z:
                z.extractall(dest_dir)

        os.remove(dest_file)

        java_bin = None
        for root, dirs, files in os.walk(dest_dir):
            if "java.exe" in files:
                java_bin = os.path.join(root, "java.exe")
                break
            elif "java" in files:
                java_bin = os.path.join(root, "java")
                break

        if not java_bin or not os.path.isfile(java_bin):
            return False, "解压后未找到 Java 可执行文件"

        if os.name != 'nt':
            os.chmod(java_bin, 0o755)

        logger.info(f"Java {version} 安装完成: {java_bin}")
        return True, java_bin

    def check_git(self):
        p = shutil.which("git")
        if p:
            return True, p
        for c in [
            "/usr/bin/git", "/usr/local/bin/git",
            "C:\\Program Files\\Git\\bin\\git.exe",
            "C:\\Program Files (x86)\\Git\\bin\\git.exe",
        ]:
            if os.path.isfile(c):
                return True, c
        return False, ""

    def install_git(self):
        os_name, _ = self.detect_platform()
        if os_name == "windows":
            url = "https://github.com/git-for-windows/git/releases/download/v2.45.0.windows.1/MinGit-2.45.0-64-bit.zip"
            dest = os.path.join(self.state.runtime_dir, "git")
            os.makedirs(dest, exist_ok=True)
            zip_path = os.path.join(dest, "mingit.zip")
            logger.info("正在下载 MinGit...")
            dl = DownloadEngine()
            ok, msg = dl.download(url, zip_path, progress=True)
            if not ok:
                return False, msg
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(dest)
            os.remove(zip_path)
            return True, os.path.join(dest, "bin", "git.exe")
        elif os_name == "macos":
            return False, "请手动执行: brew install git"
        else:
            return False, "请手动执行: sudo apt install git"

    def check_compiler(self):
        for c in ["gcc", "clang", "cc"]:
            p = shutil.which(c)
            if p:
                return True, c, p
        if os.name == 'nt':
            p = shutil.which("cl")
            if p:
                return True, "msvc", p
        return False, "", ""

    def install_compiler(self):
        os_name, _ = self.detect_platform()
        if os_name == "linux":
            for pm, pkg in [
                ("apt", "sudo apt-get install -y build-essential"),
                ("dnf", "sudo dnf install -y gcc gcc-c++ make"),
                ("yum", "sudo yum install -y gcc gcc-c++ make"),
                ("pacman", "sudo pacman -S --noconfirm base-devel"),
            ]:
                if shutil.which(pm):
                    logger.info(f"正在通过 {pm} 安装编译器...")
                    r = subprocess.run(pkg.split(), capture_output=True, text=True)
                    if r.returncode == 0:
                        return True, "已安装"
                    return False, r.stderr
        elif os_name == "macos":
            return False, "请执行: xcode-select --install"
        else:
            return False, "请安装 Visual Studio Build Tools"

    def check_python_deps(self, deps=None):
        if deps is None:
            deps = ["requests", "toml", "zstandard"]
        missing = []
        for d in deps:
            try:
                __import__(d)
            except ImportError:
                missing.append(d)
        return missing

    def install_python_deps(self, deps=None):
        missing = self.check_python_deps(deps)
        if not missing:
            return True, "全部已安装"
        for d in missing:
            logger.info(f"正在安装 Python 模块: {d}")
            r = subprocess.run([sys.executable, "-m", "pip", "install", d], capture_output=True, text=True)
            if r.returncode != 0:
                logger.warning(f"安装 {d} 失败: {r.stderr}")
        return True, f"已安装: {missing}"

    def full_check(self, mc_version=None, loader=None):
        """运行完整环境检查"""
        report = {}
        needed = self.recommended_java(mc_version, loader)
        jpath = self.find_java(mc_version, loader)
        if jpath and jpath != "java":
            report["java"] = {"status": "ok", "detail": f"Java {needed}+ 位于 {jpath}"}
        else:
            report["java"] = {"status": "missing", "detail": f"需要 Java {needed}+"}

        ok, p = self.check_git()
        report["git"] = {"status": "ok" if ok else "missing", "detail": p if ok else "未找到 Git"}

        ok, name, p = self.check_compiler()
        report["compiler"] = {"status": "ok" if ok else "missing", "detail": f"{name} 位于 {p}" if ok else "无编译器"}

        missing = self.check_python_deps()
        report["python"] = {
            "status": "ok" if not missing else "partial",
            "detail": "全部已安装" if not missing else f"缺失: {missing}"
        }
        return report

# ============================================================
# 游戏启动器
# ============================================================
# ============================================================
# 启动规则引擎 - 完整实现 Mojang 启动器规范
# ============================================================
class LaunchRulesEngine:
    """
    完整解析 Minecraft 版本 JSON 中的 rules、features、os、arch 条件。

    规范文档: https://wiki.vg/Launcher
    支持的判断维度:
      - rules[].action: "allow" / "disallow"
      - rules[].os.name: "windows" / "osx" / "linux"
      - rules[].os.version: 正则匹配内核版本
      - rules[].os.arch: "x86" / "x86_64" / "aarch64" / "arm64"
      - rules[].features: is_demo_user / has_custom_resolution / has_quick_plays_support 等
      - rules[].game_directory: 游戏目录匹配
    """

    @staticmethod
    def detect_os():
        """返回当前操作系统标识（与启动器规范一致）"""
        s = platform.system().lower()
        if "windows" in s:
            return "windows"
        elif "darwin" in s:
            return "osx"
        else:
            return "linux"

    @staticmethod
    def detect_arch():
        """返回当前架构标识"""
        a = platform.machine().lower()
        if "aarch64" in a or "arm64" in a:
            return "aarch64"
        elif "arm" in a:
            return "arm"
        elif "x86_64" in a or "amd64" in a:
            return "x86_64"
        else:
            return "x86"

    @staticmethod
    def feature_value(name, context):
        """
        根据上下文计算 feature 的值。
        context 是一个 dict，可包含:
          is_demo_user, has_custom_resolution,
          has_quick_plays_support, is_quick_play_singleplayer,
          is_quick_play_multiplayer, is_quick_play_realms
        """
        return bool(context.get(name, False))

    @staticmethod
    def rule_os_matches(rule_os, context):
        """
        判断一条规则的 os 条件是否匹配当前系统。
        rule_os 是 rules[].os 字典。
        """
        current_os = context.get("_os", LaunchRulesEngine.detect_os())
        current_arch = context.get("_arch", LaunchRulesEngine.detect_arch())
        current_os_version = context.get("_os_version", platform.release())

        # name 匹配
        if "name" in rule_os:
            if rule_os["name"] != current_os:
                return False

        # arch 匹配（可选）
        if "arch" in rule_os:
            if rule_os["arch"] != current_arch:
                return False

        # version 正则匹配（可选）
        if "version" in rule_os:
            import re as re_mod
            pattern = rule_os["version"]
            if not re_mod.search(pattern, current_os_version):
                return False

        return True

    @staticmethod
    def evaluate_rules(rules, context):
        """
        评估一组 rules，返回 True 表示允许（allow），False 表示拒绝（disallow）。

        规则逻辑（Mojang 规范）:
          1. 从 "disallow" 开始
          2. 遍历所有规则，如果某条规则匹配且 action=allow → 允许
          3. 如果某条规则匹配且 action=disallow → 拒绝
          4. 如果没有任何规则匹配 → 保持当前结果
        """
        # 构建 features 上下文
        eval_context = {
            "_os": context.get("_os", LaunchRulesEngine.detect_os()),
            "_arch": context.get("_arch", LaunchRulesEngine.detect_arch()),
            "_os_version": context.get("_os_version", platform.release()),
        }
        # 透传 feature flags
        for k in ["is_demo_user", "has_custom_resolution",
                  "has_quick_plays_support", "is_quick_play_singleplayer",
                  "is_quick_play_multiplayer", "is_quick_play_realms"]:
            if k in context:
                eval_context[k] = context[k]

        allowed = False  # 默认拒绝
        for rule in rules:
            rule_allowed = True  # 这条规则是否匹配

            # 检查 os 条件
            if "os" in rule:
                if not LaunchRulesEngine.rule_os_matches(rule["os"], eval_context):
                    rule_allowed = False

            # 检查 features 条件（所有 feature 都必须满足）
            if "features" in rule and rule_allowed:
                for feat_name, feat_required in rule["features"].items():
                    actual = LaunchRulesEngine.feature_value(feat_name, eval_context)
                    if bool(feat_required) != actual:
                        rule_allowed = False
                        break

            # 检查 game_directory 条件
            if "game_directory" in rule and rule_allowed:
                # 这是极少用的规则，匹配游戏目录路径
                gd = rule["game_directory"]
                actual_gd = context.get("game_directory", "")
                if isinstance(gd, str) and gd not in actual_gd:
                    rule_allowed = False

            # 应用规则
            if rule_allowed:
                action = rule.get("action", "allow")
                if action == "allow":
                    allowed = True
                elif action == "disallow":
                    allowed = False

        return allowed

    @staticmethod
    def should_include_library(lib, context):
        """
        判断一个 library 是否应该被包含。
        返回 True/False。
        """
        rules = lib.get("rules")
        if not rules:
            return True  # 没有 rules 则默认包含
        return LaunchRulesEngine.evaluate_rules(rules, context)

    @staticmethod
    def should_include_native(lib, context):
        """
        判断一个 native library 是否应该被包含。
        同时检查 rules 和 natives 字段。
        """
        # 先检查 rules
        rules = lib.get("rules")
        if rules:
            if not LaunchRulesEngine.evaluate_rules(rules, context):
                return False

        # 检查 natives 是否有当前系统的条目
        natives = lib.get("natives", {})
        if natives:
            current_os = context.get("_os", LaunchRulesEngine.detect_os())
            if current_os not in natives:
                return False

        return True

    @staticmethod
    def get_native_classifier(lib, context):
        """
        获取当前系统对应的 native classifier 名称。
        处理 ${arch} 变量替换。
        """
        natives = lib.get("natives", {})
        if not natives:
            return None

        current_os = context.get("_os", LaunchRulesEngine.detect_os())
        classifier = natives.get(current_os)
        if not classifier:
            return None

        # 替换 ${arch} 变量
        arch = context.get("_arch", LaunchRulesEngine.detect_arch())
        classifier = classifier.replace("${arch}", arch)

        return classifier

    @staticmethod
    def resolve_argument(arg_entry, context):
        """
        解析一条 arguments.game 或 arguments.jvm 条目。
        支持:
          - 字符串参数（直接返回）
          - 带 rules 的字典参数
          - ${...} 变量替换
          - 嵌套列表展开
        """
        # 字符串直接返回（做变量替换）
        if isinstance(arg_entry, str):
            return [LaunchRulesEngine._substitute_vars(arg_entry, context)]

        # 字典形式（带 rules）
        if isinstance(arg_entry, dict):
            rules = arg_entry.get("rules")
            if rules:
                if not LaunchRulesEngine.evaluate_rules(rules, context):
                    return []  # 规则不允许，跳过

            value = arg_entry.get("value", "")
            if isinstance(value, list):
                return [LaunchRulesEngine._substitute_vars(v, context) for v in value]
            elif isinstance(value, str):
                return [LaunchRulesEngine._substitute_vars(value, context)]

        return []

    @staticmethod
    def _substitute_vars(text, context):
        """替换 Minecraft 参数中的 ${...} 变量"""
        import re as re_mod

        def replacer(m):
            var_name = m.group(1)
            # 从 context 中查找
            if var_name in context:
                val = context[var_name]
                if isinstance(val, (str, int, float)):
                    return str(val)
            # 特殊变量
            special = {
                "arch": LaunchRulesEngine.detect_arch(),
                "os_name": platform.system(),
                "os_version": platform.release(),
                "os_arch": platform.machine(),
            }
            if var_name in special:
                return special[var_name]
            # 找不到就保留原样
            return m.group(0)

        return re_mod.sub(r'\$\{(\w+)\}', replacer, text)


# ============================================================
# CurseForge 模组下载器
# ============================================================
class CurseForgeDownloader:
    """
    根据 CurseForge manifest.json 自动下载所有模组文件。
    使用 CurseForge API v1 通过文件 ID 获取下载 URL。
    """

    # CurseForge API 端点
    API_BASE = "https://api.curseforge.com/v1"
    # 备选: 通过 BMCLAPI 镜像加速
    BMCLAPI_CF = "https://bmclapi2.bangbang93.com/curseforge"

    @staticmethod
    def parse_manifest(manifest_path):
        """解析 CurseForge manifest.json"""
        with open(manifest_path, 'r') as f:
            return json.load(f)

    @staticmethod
    def get_download_url_via_bmclapi(file_id, project_id=None):
        """
        通过 BMCLAPI 镜像获取 CurseForge 文件下载 URL。
        这是最可靠的方式（无需 API Key）。
        """
        if project_id:
            return f"https://bmclapi2.bangbang93.com/curseforge/{project_id}/files/{file_id}/download"
        return f"https://bmclapi2.bangbang93.com/curseforge/files/{file_id}/download"

    @staticmethod
    def get_download_url_via_curseforge_api(file_id, api_key=None):
        """
        通过官方 CurseForge API 获取下载 URL。
        需要 API Key（免费注册 https://console.curseforge.com/）。
        """
        if not api_key:
            return None
        url = f"{CurseForgeDownloader.API_BASE}/mods/files/{file_id}/download-url"
        req = urllib.request.Request(url, headers={"x-api-key": api_key})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode())
                return data.get("data")
        except Exception as e:
            logger.debug(f"CurseForge API 查询失败: {e}")
            return None

    @staticmethod
    def download_mods(manifest, extract_dir, api_key=None, progress=True):
        """
        根据 manifest 下载所有模组文件。
        返回 (成功数, 失败列表)。
        """
        files = manifest.get("files", [])
        mods_dir = os.path.join(extract_dir, "mods")
        os.makedirs(mods_dir, exist_ok=True)

        if not files:
            logger.info("manifest 中没有需要下载的模组文件")
            return 0, []

        # 获取模组名称映射（用于显示）
        mod_names = {}
        overrides = manifest.get("overrides", "overrides")
        # 尝试从 manifest 的 minecraft.modLoaders 获取信息
        # 也尝试从 overrides/mods 目录读取已存在的模组

        # 尝试从 CurseForge API 获取模组名称映射
        if api_key:
            project_ids = list(set(f.get("projectID", 0) for f in files))
            try:
                url = f"{CurseForgeDownloader.API_BASE}/mods"
                req = urllib.request.Request(
                    url,
                    data=json.dumps({"modIds": project_ids}).encode(),
                    headers={"x-api-key": api_key, "Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.loads(r.read().decode())
                    for mod in data.get("data", []):
                        mod_names[mod["id"]] = mod.get("name", str(mod["id"]))
            except Exception as e:
                logger.debug(f"获取模组名称失败: {e}")

        # 如果没拿到名称，尝试从 overrides/mods 里的文件名推断
        override_mods = os.path.join(extract_dir, overrides, "mods")
        if os.path.isdir(override_mods):
            for f in os.listdir(override_mods):
                if f.endswith(".jar"):
                    # 尝试从文件名提取 projectID
                    # 格式通常不包含 ID，跳过
                    pass

        dl = DownloadEngine()
        success = 0
        failed = []
        total = len(files)

        for i, f in enumerate(files, 1):
            project_id = f.get("projectID", 0)
            file_id = f.get("fileID", 0)
            if not file_id:
                continue

            mod_name = mod_names.get(project_id, f"project_{project_id}")
            filename = f.get("fileName", f"{file_id}.jar")
            dest = os.path.join(mods_dir, filename)

            # 如果文件已存在且大小正常，跳过
            if os.path.exists(dest) and os.path.getsize(dest) > 1000:
                logger.debug(f"[{i}/{total}] 已存在: {filename}")
                success += 1
                continue

            # 尝试多个下载源
            urls = [
                CurseForgeDownloader.get_download_url_via_bmclapi(file_id, project_id),
                f"https://bmclapi2.bangbang93.com/curseforge/files/{file_id}/download",
            ]
            # 如果有 API Key，优先用官方 API
            api_url = CurseForgeDownloader.get_download_url_via_curseforge_api(file_id, api_key)
            if api_url:
                urls.insert(0, api_url)

            downloaded = False
            for url in urls:
                if progress:
                    logger.info(f"[{i}/{total}] 下载 {mod_name} ({filename})...")
                ok, msg = dl.download(url, dest, progress=False)
                if ok:
                    downloaded = True
                    success += 1
                    break
                logger.debug(f"源失败: {msg}")

            if not downloaded:
                failed.append({"projectID": project_id, "fileID": file_id, "reason": "all sources failed"})
                logger.warning(f"[{i}/{total}] 下载失败: {mod_name} (project={project_id}, file={file_id})")

        return success, failed

    @staticmethod
    def apply_overrides(extract_dir, instance_dir, manifest):
        """
        将 overrides 目录中的文件复制到实例目录。
        CurseForge 整合包通常包含 config/、scripts/、resourcepacks/ 等。
        """
        overrides_name = manifest.get("overrides", "overrides")
        src = os.path.join(extract_dir, overrides_name)
        if not os.path.isdir(src):
            logger.debug(f"没有 overrides 目录: {src}")
            return 0

        count = 0
        for root, dirs, files in os.walk(src):
            rel = os.path.relpath(root, src)
            dest_root = instance_dir if rel == "." else os.path.join(instance_dir, rel)
            os.makedirs(dest_root, exist_ok=True)
            for f in files:
                src_file = os.path.join(root, f)
                dest_file = os.path.join(dest_root, f)
                # 不覆盖已存在的文件（如刚下载的模组）
                if not os.path.exists(dest_file):
                    shutil.copy2(src_file, dest_file)
                    count += 1

        return count


# ============================================================
# Minecraft 版本下载与启动
# ============================================================
class GameLauncher:
    """Minecraft 版本下载与启动"""

    MANIFEST_URL = "https://launchermeta.mojang.com/mc/game/version_manifest.json"

    def __init__(self, state):
        self.state = state
        self.dl = DownloadEngine()

    def fetch_manifest(self, force=False):
        """获取版本清单（带缓存）"""
        cache = os.path.join(self.state.versions_dir, "_manifest.json")
        if not force and os.path.exists(cache):
            if time.time() - os.path.getmtime(cache) < 3600:
                with open(cache, 'r') as f:
                    return json.load(f)

        try:
            req = urllib.request.Request(self.MANIFEST_URL, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode())
            with open(cache, 'w') as f:
                json.dump(data, f)
            self.state.version_manifest = data
            return data
        except Exception as e:
            logger.error(f"获取版本清单失败: {e}")
            if os.path.exists(cache):
                with open(cache, 'r') as f:
                    return json.load(f)
            return None

    def get_version_info(self, version_id):
        """获取指定版本的详细信息"""
        manifest = self.fetch_manifest()
        if not manifest:
            return None
        for v in manifest.get("versions", []):
            if v["id"] == version_id:
                try:
                    req = urllib.request.Request(v["url"], headers={"Accept": "application/json"})
                    with urllib.request.urlopen(req, timeout=30) as r:
                        return json.loads(r.read().decode())
                except Exception as e:
                    logger.error(f"获取版本信息失败: {e}")
                    return None
        return None

    def is_version_installed(self, version_id):
        vdir = os.path.join(self.state.versions_dir, version_id)
        jar = os.path.join(vdir, version_id + ".jar")
        return os.path.isfile(jar)

    def download_version(self, version_id):
        """下载指定版本的全部文件"""
        vinfo = self.get_version_info(version_id)
        if not vinfo:
            return False, "未找到版本信息"

        vdir = os.path.join(self.state.versions_dir, version_id)
        os.makedirs(vdir, exist_ok=True)

        vjson = os.path.join(vdir, version_id + ".json")
        with open(vjson, 'w') as f:
            json.dump(vinfo, f, indent=2)

        client = vinfo.get("downloads", {}).get("client", {})
        jar_url = client.get("url", "")
        jar_sha1 = client.get("sha1", "")
        jar_path = os.path.join(vdir, version_id + ".jar")

        if jar_url:
            logger.info(f"正在下载 Minecraft {version_id} 客户端...")
            ok, msg = self.dl.download(jar_url, jar_path, sha1=jar_sha1, progress=True)
            if not ok:
                return False, f"客户端下载失败: {msg}"

        libraries = vinfo.get("libraries", [])
        total_libs = len(libraries)
        for i, lib in enumerate(libraries, 1):
            artifact = lib.get("downloads", {}).get("artifact", {})
            if not artifact:
                continue
            url = artifact.get("url", "")
            sha1_hash = artifact.get("sha1", "")
            path = artifact.get("path", "")
            if not url or not path:
                continue
            dest = os.path.join(self.state.libraries_dir, path.replace("/", os.sep))
            if os.path.exists(dest):
                ok, _ = self.dl.verify_file(dest, sha1=sha1_hash)
                if ok:
                    continue
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            logger.info(f"[{i}/{total_libs}] 下载 {path}...")
            ok, msg = self.dl.download(url, dest, sha1=sha1_hash, progress=False)
            if not ok:
                logger.warning(f"下载失败 {path}: {msg}")

        asset_index = vinfo.get("assetIndex", {})
        if asset_index:
            idx_url = asset_index.get("url", "")
            idx_sha1 = asset_index.get("sha1", "")
            idx_id = asset_index.get("id", "legacy")
            idx_path = os.path.join(self.state.assets_dir, "indexes", idx_id + ".json")
            if idx_url and not os.path.exists(idx_path):
                os.makedirs(os.path.dirname(idx_path), exist_ok=True)
                logger.info(f"正在下载资源索引 {idx_id}...")
                ok, msg = self.dl.download(idx_url, idx_path, sha1=idx_sha1, progress=False)
                if not ok:
                    logger.warning(f"资源索引下载失败: {msg}")

        logger.info(f"版本 {version_id} 安装完成")
        return True, "OK"

    def build_classpath(self, vinfo, version_id):
        """构建 JVM 类路径"""
        cp = []
        vdir = os.path.join(self.state.versions_dir, version_id)
        cp.append(os.path.join(vdir, version_id + ".jar"))
        for lib in vinfo.get("libraries", []):
            artifact = lib.get("downloads", {}).get("artifact", {})
            if not artifact:
                continue
            path = artifact.get("path", "")
            if not path:
                continue
            full = os.path.join(self.state.libraries_dir, path.replace("/", os.sep))
            if os.path.exists(full):
                cp.append(full)
        return cp

    def launch(self, version_id, save_dir=None, instance_name=None):
        """
        启动 Minecraft - 完整实现 Mojang 启动器规范。

        处理以下规范要素:
          - arguments.game / arguments.jvm (新格式)
          - minecraftArguments (旧格式兼容)
          - rules 评估 (allow/disallow)
          - features 条件 (is_demo_user, has_custom_resolution 等)
          - os 条件 (name, version 正则, arch)
          - ${variable} 替换 (全部规范变量)
          - libraries 按 rules 过滤
          - natives 按 os/arch 选择 + extract/exclude 规则
          - logging 配置
          - 版本继承 (inheritsFrom)
        """
        if not self.is_version_installed(version_id):
            logger.info(f"版本 {version_id} 未安装，正在下载...")
            ok, msg = self.download_version(version_id)
            if not ok:
                return False, f"安装失败: {msg}"

        # 加载版本信息（处理 inheritsFrom 链）
        vinfo = self._load_version_chain(version_id)
        if not vinfo:
            return False, "无法加载版本信息"

        env = self.state.get_env_manager()
        java_path = env.find_java(version_id)
        if java_path == "java":
            needed = env.recommended_java(version_id)
            logger.info(f"未找到 Java，尝试自动安装 Java {needed}...")
            ok, result = env.install_java(needed)
            if ok:
                java_path = result
            else:
                logger.warning(f"自动安装失败: {result}")

        # ---- 构建启动上下文 ----
        save_dir = save_dir or self.state.minecraft_dir
        natives_dir = os.path.join(self.state.versions_dir, version_id, "natives")
        os.makedirs(natives_dir, exist_ok=True)

        # 解压 natives
        self._extract_natives(vinfo, natives_dir)

        # 构建规则评估上下文
        context = {
            "_os": LaunchRulesEngine.detect_os(),
            "_arch": LaunchRulesEngine.detect_arch(),
            "_os_version": platform.release(),
            # features
            "is_demo_user": False,  # 正版用户始终 False
            "has_custom_resolution": False,  # 未设置自定义分辨率
            "has_quick_plays_support": False,
            "is_quick_play_singleplayer": False,
            "is_quick_play_multiplayer": False,
            "is_quick_play_realms": False,
            # 变量替换用
            "auth_player_name": self.state.username,
            "version_name": version_id,
            "game_directory": save_dir,
            "assets_root": self.state.assets_dir,
            "assets_index_name": vinfo.get("assetIndex", {}).get("id", "legacy"),
            "auth_uuid": self.state.uuid_str,
            "auth_access_token": self.state.access_token,
            "user_type": self.state.auth_type or "msa",
            "version_type": vinfo.get("type", "release"),
            "launcher_name": "starter",
            "launcher_version": "2.3",
            "natives_directory": natives_dir,
            "classpath_separator": os.pathsep,
            "library_directory": self.state.libraries_dir,
        }

        # ---- 构建 classpath（按 rules 过滤 libraries）----
        cp = self._build_classpath_full(vinfo, context)
        classpath = os.pathsep.join(cp)

        # ---- 构建 JVM 参数 ----
        jvm_args = self._build_jvm_args(vinfo, context, natives_dir, classpath)

        # ---- 构建游戏参数 ----
        game_args = self._build_game_args(vinfo, context)

        # ---- 主类 ----
        main_class = vinfo.get("mainClass", "net.minecraft.client.main.Main")

        # ---- 组装完整命令 ----
        # 加入 classpath（Mojang 规范要求 -cp 在 mainClass 之前）
        if classpath:
            cmd = [java_path] + jvm_args + ["-cp", classpath, main_class] + game_args
        else:
            cmd = [java_path] + jvm_args + [main_class] + game_args
        env_vars = os.environ.copy()
        java_home = os.path.dirname(os.path.dirname(java_path))
        env_vars["JAVA_HOME"] = java_home
        env_vars["PATH"] = os.path.dirname(java_path) + os.pathsep + env_vars.get("PATH", "")

        logger.info(f"正在启动 Minecraft {version_id}（用户: {self.state.username}）...")
        logger.debug(f"Java: {java_path}")
        logger.debug(f"主类: {main_class}")
        logger.debug(f"JVM 参数 ({len(jvm_args)}): {' '.join(jvm_args[:10])}{'...' if len(jvm_args)>10 else ''}")
        logger.debug(f"游戏参数 ({len(game_args)}): {' '.join(game_args[:10])}{'...' if len(game_args)>10 else ''}")
        logger.debug(f"Classpath: {len(cp)} 个条目")

        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=save_dir, env=env_vars, text=True, bufsize=1,
            )
            self.state.minecraft_process = proc
            self.state.game_running = True

            t_out = threading.Thread(target=self._monitor_output, args=(proc.stdout, "INFO"), daemon=True)
            t_err = threading.Thread(target=self._monitor_output, args=(proc.stderr, "ERROR"), daemon=True)
            t_out.start()
            t_err.start()

            t_wait = threading.Thread(target=self._wait_for_exit, args=(proc,), daemon=True)
            t_wait.start()

            return True, f"Minecraft {version_id} 已启动 (PID: {proc.pid})"
        except Exception as e:
            return False, f"启动失败: {e}"

    def _load_version_chain(self, version_id):
        """
        加载版本信息，处理 inheritsFrom 继承链。
        将父版本的 libraries、arguments 等合并到子版本。
        """
        visited = set()
        chain = []

        current_id = version_id
        while current_id and current_id not in visited:
            visited.add(current_id)
            vdir = os.path.join(self.state.versions_dir, current_id)
            vjson = os.path.join(vdir, current_id + ".json")
            if not os.path.exists(vjson):
                # 尝试从网络获取
                vinfo = self.get_version_info(current_id)
                if not vinfo:
                    if chain:
                        break
                    return None
            else:
                with open(vjson, 'r') as f:
                    vinfo = json.load(f)
            chain.append(vinfo)
            current_id = vinfo.get("inheritsFrom")

        if not chain:
            return None

        # 合并: 子版本优先，父版本补充
        merged = {}
        for v in reversed(chain):
            for k, vv in v.items():
                if k == "libraries":
                    # 合并 libraries（去重 by name）
                    existing = {lib.get("name", ""): lib for lib in merged.get("libraries", [])}
                    for lib in vv:
                        name = lib.get("name", "")
                        if name not in existing:
                            existing[name] = lib
                    merged["libraries"] = list(existing.values())
                elif k == "arguments":
                    # 合并 arguments（子版本在前）
                    if "arguments" not in merged:
                        merged["arguments"] = {"game": [], "jvm": []}
                    for arg_type in ("game", "jvm"):
                        child_args = merged["arguments"].get(arg_type, [])
                        parent_args = vv.get(arg_type, [])
                        # 子版本优先，但避免重复
                        seen = set()
                        merged_list = []
                        for a in child_args + parent_args:
                            key = json.dumps(a, sort_keys=True) if isinstance(a, dict) else str(a)
                            if key not in seen:
                                seen.add(key)
                                merged_list.append(a)
                        merged["arguments"][arg_type] = merged_list
                elif k == "rules":
                    # 顶层 rules 合并
                    existing_rules = merged.get("rules", [])
                    existing_rules.extend(vv)
                    merged["rules"] = existing_rules
                elif k == "inheritsFrom":
                    pass  # 不复制 inheritsFrom
                else:
                    if k not in merged:
                        merged[k] = vv

        return merged

    def _build_classpath_full(self, vinfo, context):
        """
        构建完整 classpath，按 rules 过滤 libraries。
        包含版本 jar 和所有符合条件的库。
        """
        cp = []
        version_id = vinfo.get("id", context.get("version_name", ""))
        vdir = os.path.join(self.state.versions_dir, version_id)
        version_jar = os.path.join(vdir, version_id + ".jar")
        if os.path.exists(version_jar):
            cp.append(version_jar)

        for lib in vinfo.get("libraries", []):
            # 用规则引擎判断
            if not LaunchRulesEngine.should_include_library(lib, context):
                continue
            artifact = lib.get("downloads", {}).get("artifact")
            if not artifact:
                # 有些库没有 downloads.artifact，尝试从 name 推导路径
                name = lib.get("name", "")
                if name:
                    path = self._maven_name_to_path(name)
                    full = os.path.join(self.state.libraries_dir, path)
                    if os.path.exists(full):
                        cp.append(full)
                continue
            path = artifact.get("path", "")
            if not path:
                continue
            full = os.path.join(self.state.libraries_dir, path.replace("/", os.sep))
            if os.path.exists(full):
                cp.append(full)

        return cp

    def _maven_name_to_path(self, name):
        """将 Maven 坐标 (group:artifact:version) 转为路径"""
        parts = name.split(":")
        if len(parts) >= 3:
            group, artifact, version = parts[0], parts[1], parts[2]
            # 处理 classifier
            if len(parts) >= 4:
                classifier = parts[3]
                filename = f"{artifact}-{version}-{classifier}.jar"
            else:
                filename = f"{artifact}-{version}.jar"
            return os.path.join(*group.split("."), artifact, version, filename).replace("/", os.sep)
        return ""

    def _extract_natives(self, vinfo, natives_dir):
        """解压所有符合条件的 native 库到 natives 目录"""
        context = {
            "_os": LaunchRulesEngine.detect_os(),
            "_arch": LaunchRulesEngine.detect_arch(),
            "_os_version": platform.release(),
        }

        for lib in vinfo.get("libraries", []):
            if not LaunchRulesEngine.should_include_native(lib, context):
                continue

            natives = lib.get("natives", {})
            if not natives:
                continue

            classifier = LaunchRulesEngine.get_native_classifier(lib, context)
            if not classifier:
                continue

            # 查找 native 下载信息
            # Mojang 格式: downloads 的 key 就是 classifier 字符串
            downloads = lib.get("downloads", {})
            native_artifact = None
            for k, v in downloads.items():
                if k == "artifact":
                    continue
                # key 本身就是 classifier（如 "lwjgl-glfw-natives-linux-x86_64"）
                if k == classifier:
                    native_artifact = v
                    break
                # 兼容：某些格式可能把 classifier 放在 value 里
                if isinstance(v, dict) and v.get("classifier") == classifier:
                    native_artifact = v
                    break

            # 也检查 classifiers 字段
            if not native_artifact:
                classifiers = lib.get("classifiers", {})
                if classifier in classifiers:
                    native_artifact = classifiers[classifier]
                # 尝试模糊匹配（处理版本号差异）
                else:
                    for ck, cv in classifiers.items():
                        if classifier.replace("-natives-", "-") in ck.replace("-natives-", "-"):
                            native_artifact = cv
                            break

            if not native_artifact:
                continue

            native_path = native_artifact.get("path", "")
            if not native_path:
                continue

            src = os.path.join(self.state.libraries_dir, native_path.replace("/", os.sep))
            if not os.path.exists(src):
                continue

            # 获取 extract 规则
            extract_info = lib.get("extract", {})
            exclude_patterns = extract_info.get("exclude", [])

            dest = natives_dir
            try:
                with zipfile.ZipFile(src, 'r') as z:
                    for member in z.namelist():
                        # 检查 exclude
                        excluded = False
                        for pat in exclude_patterns:
                            if pat in member:
                                excluded = True
                                break
                        if excluded:
                            continue
                        # 只解压实际文件（跳过目录）
                        if member.endswith("/"):
                            continue
                        z.extract(member, dest)
            except Exception as e:
                logger.debug(f"解压 native 失败 {src}: {e}")

    def _build_jvm_args(self, vinfo, context, natives_dir, classpath):
        """构建 JVM 参数（处理 arguments.jvm + rules）"""
        jvm_args = []

        # 基础参数
        jvm_args.append(f"-Djava.library.path={natives_dir}")
        jvm_args.append(f"-Dminecraft.launcher.brand={context['launcher_name']}")
        jvm_args.append(f"-Dminecraft.launcher.version={context['launcher_version']}")

        # 从版本 JSON 的 arguments.jvm 解析
        arguments = vinfo.get("arguments", {})
        jvm_rules = arguments.get("jvm", [])

        if jvm_rules:
            for entry in jvm_rules:
                resolved = LaunchRulesEngine.resolve_argument(entry, context)
                jvm_args.extend(resolved)
        else:
            # 旧版兼容：使用默认值
            jvm_args.extend([
                "-Xss1M",
                "-Dfml.ignoreInvalidMinecraftCertificates=true",
                "-Dfml.ignorePatchDiscrepancies=true",
            ])

        # 内存参数（如果用户设置了）
        if hasattr(self.state, 'memory_max'):
            jvm_args.append(f"-Xmx{self.state.memory_max}")
        else:
            jvm_args.append("-Xmx2G")

        if hasattr(self.state, 'memory_min'):
            jvm_args.append(f"-Xms{self.state.memory_min}")
        else:
            jvm_args.append("-Xms1G")

        # logging 配置
        logging_cfg = vinfo.get("logging", {})
        if logging_cfg:
            client_logging = logging_cfg.get("client", {})
            if client_logging:
                log_file = client_logging.get("file", {})
                log_path = log_file.get("id", "")
                if log_path:
                    log_dest = os.path.join(self.state.assets_dir, "log_configs", log_path)
                    if os.path.exists(log_dest):
                        arg_template = client_logging.get("argument", "")
                        if arg_template:
                            arg = arg_template.replace("${path}", log_dest)
                            jvm_args.append(arg)

        return jvm_args

    def _build_game_args(self, vinfo, context):
        """构建游戏参数（处理 arguments.game + rules + 变量替换）"""
        game_args = []

        arguments = vinfo.get("arguments", {})
        game_rules = arguments.get("game", [])

        if game_rules:
            for entry in game_rules:
                resolved = LaunchRulesEngine.resolve_argument(entry, context)
                game_args.extend(resolved)
        else:
            # 旧版兼容：minecraftArguments
            legacy = vinfo.get("minecraftArguments", "")
            if legacy:
                for token in legacy.split():
                    # 变量替换
                    for var_name in ["auth_player_name", "version_name", "game_directory",
                                     "assets_root", "assets_index_name", "auth_uuid",
                                     "auth_access_token", "user_type", "version_type"]:
                        placeholder = "${" + var_name + "}"
                        if placeholder in token:
                            token = token.replace(placeholder, str(context.get(var_name, "")))
                    game_args.append(token)

        return game_args

    def _monitor_output(self, stream, default_level):
        """监控游戏进程输出，按日志级别着色"""
        level_map = {
            "ERROR": "ERROR", "WARN": "WARNING", "INFO": "INFO",
            "DEBUG": "DEBUG", "FATAL": "CRITICAL",
        }
        try:
            for line in stream:
                line = line.strip()
                if not line:
                    continue
                upper = line.upper()
                level = default_level
                for kw, lv in level_map.items():
                    if kw in upper:
                        level = lv
                        break
                if level in ("ERROR", "CRITICAL"):
                    logger.error(line)
                elif level == "WARNING":
                    logger.warning(line)
                elif level == "DEBUG":
                    logger.debug(line)
                else:
                    logger.info(line)
        except Exception:
            pass

    def _wait_for_exit(self, proc):
        """等待游戏进程退出"""
        proc.wait()
        self.state.game_running = False
        if proc.returncode != 0:
            logger.error(f"{C.RED}游戏崩溃了！错误报告如下：{C.RESET}")
            logger.error(f"{C.RED}退出码: {proc.returncode}{C.RESET}")
            print("如果你要寻求帮助，请将上面信息以照片、截图或文本的方式完整发送给技术人员，否则对方就只能给你算一卦是什么原因了")
        else:
            logger.info("游戏正常退出")

    def stop_game(self):
        """停止正在运行的游戏"""
        if self.state.minecraft_process and self.state.game_running:
            try:
                self.state.minecraft_process.terminate()
                time.sleep(2)
                if self.state.game_running:
                    self.state.minecraft_process.kill()
                self.state.game_running = False
                return True, "游戏已停止"
            except Exception as e:
                return False, str(e)
        return False, "没有正在运行的游戏"


# ============================================================
# 整合包管理
# ============================================================
class ModpackManager:
    """处理各种格式的整合包导入导出"""

    @staticmethod
    def detect_format(path):
        """自动检测整合包格式"""
        if not os.path.exists(path):
            return None
        if os.path.isfile(path):
            if path.endswith(".mrpack"):
                return "modrinth"
            if path.endswith(".zip"):
                with zipfile.ZipFile(path, 'r') as z:
                    names = z.namelist()
                    if any(n.endswith("manifest.json") for n in names):
                        return "curseforge"
                    if any(n.endswith("mmc-pack.json") for n in names):
                        return "multimc"
        return None

    @staticmethod
    def import_modpack(path, state, instance_name=None):
        fmt = ModpackManager.detect_format(path)
        if not fmt:
            return False, "无法识别的整合包格式"
        if fmt == "modrinth":
            return ModpackManager._import_modrinth(path, state, instance_name)
        elif fmt == "curseforge":
            return ModpackManager._import_curseforge(path, state, instance_name)
        elif fmt == "multimc":
            return ModpackManager._import_multimc(path, state, instance_name)
        return False, "不支持的格式"

    @staticmethod
    def _import_modrinth(path, state, instance_name):
        extract_dir = os.path.join(state.instances_dir, instance_name or "modrinth_import")
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(path, 'r') as z:
            index_name = None
            for n in z.namelist():
                if n.endswith("modrinth.index.json"):
                    index_name = n
                    break
            if not index_name:
                return False, "未找到 modrinth.index.json"
            index = json.loads(z.read(index_name).decode())
            z.extractall(extract_dir)

        mods_dir = os.path.join(extract_dir, "mods")
        os.makedirs(mods_dir, exist_ok=True)
        deps = index.get("dependencies", {})
        files = index.get("files", [])
        dl = DownloadEngine()
        for f in files:
            fpath = f.get("path", "")
            dest = os.path.join(extract_dir, fpath.replace("/", os.sep))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            downloads = f.get("downloads", [])
            sha1 = f.get("hashes", {}).get("sha1", "")
            for url in downloads:
                ok, msg = dl.download(url, dest, sha1=sha1, progress=False)
                if ok:
                    break
            else:
                logger.warning(f"下载失败: {fpath}")

        mc_version = deps.get("minecraft", "")
        loader = [l for l in deps.keys() if l != "minecraft"]
        loader_name = loader[0] if loader else "原版"
        return True, f"已导入 Modrinth 整合包: MC {mc_version}, 加载器: {loader_name}"

    @staticmethod
    def _import_curseforge(path, state, instance_name):
        """
        导入 CurseForge 整合包并自动下载所有模组文件。

        流程:
          1. 解压 zip
          2. 解析 manifest.json 获取 MC 版本、加载器、文件列表
          3. 自动下载每个模组文件（通过 BMCLAPI 镜像）
          4. 应用 overrides（config/、scripts/、resourcepacks/ 等）
          5. 保存整合包元数据供后续使用
        """
        # 解压
        extract_dir = os.path.join(state.instances_dir, instance_name or "curseforge_import")
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(path, 'r') as z:
            z.extractall(extract_dir)
            manifest = None
            for n in z.namelist():
                if n.endswith("manifest.json"):
                    manifest = json.loads(z.read(n).decode())
                    break
        if not manifest:
            return False, "未找到 manifest.json"

        mc_version = manifest.get("minecraft", {}).get("version", "")
        loader_info = manifest.get("minecraft", {}).get("modLoaders", [])
        loader_name = loader_info[0].get("id", "原版") if loader_info else "原版"

        logger.info(f"检测到 CurseForge 整合包: MC {mc_version}, 加载器: {loader_name}")
        logger.info(f"模组文件数: {len(manifest.get('files', []))}")

        # 自动下载模组
        api_key = os.environ.get("CURSEFORGE_API_KEY", "")
        success, failed = CurseForgeDownloader.download_mods(
            manifest, extract_dir, api_key=api_key
        )
        total = len(manifest.get("files", []))
        logger.info(f"模组下载完成: 成功 {success}/{total}")
        if failed:
            logger.warning(f"  失败 {len(failed)} 个模组:")
            for f in failed[:5]:
                logger.warning(f"    projectID={f['projectID']}, fileID={f['fileID']}")
            if len(failed) > 5:
                logger.warning(f"    ... 还有 {len(failed)-5} 个")

        # 应用 overrides（config、scripts、resourcepacks 等）
        overrides_count = CurseForgeDownloader.apply_overrides(extract_dir, extract_dir, manifest)
        if overrides_count:
            logger.info(f"已应用 {overrides_count} 个 overrides 文件")

        # 保存元数据
        metadata = {
            "type": "curseforge",
            "mc_version": mc_version,
            "loader": loader_name,
            "files": manifest.get("files", []),
            "download_success": success,
            "download_failed": len(failed),
            "imported_at": time.time(),
        }
        with open(os.path.join(extract_dir, ".starter_meta.json"), 'w') as f:
            json.dump(metadata, f, indent=2)

        # 创建 instance.json
        instance_cfg = {
            "name": instance_name or "curseforge_import",
            "mc_version": mc_version,
            "loader": loader_name,
            "source": "curseforge",
            "jvm_args": "-Xmx2G -Xms1G",
            "memory": {"min": 1024, "max": 2048},
            "window": {"width": 854, "height": 480},
        }
        with open(os.path.join(extract_dir, "instance.json"), 'w') as f:
            json.dump(instance_cfg, f, indent=2)

        msg = f"CurseForge 整合包导入完成: MC {mc_version}, 加载器: {loader_name}, 模组: {success}/{total}"
        if failed:
            msg += f"（{len(failed)} 个模组下载失败，可重新导入重试）"
        return True, msg

    @staticmethod
    def _import_multimc(path, state, instance_name):
        extract_dir = os.path.join(state.instances_dir, instance_name or "multimc_import")
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(path, 'r') as z:
            z.extractall(extract_dir)
            for n in z.namelist():
                if n.endswith("mmc-pack.json"):
                    pack = json.loads(z.read(n).decode())
                    break
            else:
                return False, "未找到 mmc-pack.json"
        logger.info("MultiMC 实例导入完成")
        return True, "MultiMC 实例已导入"

    @staticmethod
    def export_modrinth(instance_dir, state):
        """将实例导出为 Modrinth .mrpack"""
        name = os.path.basename(instance_dir.rstrip(os.sep))
        output = os.path.join(state.instances_dir, name + ".mrpack")
        index = {
            "formatVersion": 1, "game": "minecraft",
            "versionId": "1.0", "name": name,
            "dependencies": {"minecraft": "1.20.1"}, "files": [],
        }
        mods_dir = os.path.join(instance_dir, "mods")
        if os.path.isdir(mods_dir):
            for f in os.listdir(mods_dir):
                if f.endswith(".jar"):
                    fpath = os.path.join(mods_dir, f)
                    h = hashlib.sha1()
                    with open(fpath, "rb") as fh:
                        while True:
                            c = fh.read(1024*1024)
                            if not c:
                                break
                            h.update(c)
                    rel = os.path.relpath(fpath, instance_dir).replace(os.sep, "/")
                    index["files"].append({"path": rel, "hashes": {"sha1": h.hexdigest()}, "downloads": []})
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr("modrinth.index.json", json.dumps(index, indent=2))
            if os.path.isdir(mods_dir):
                for f in os.listdir(mods_dir):
                    if f.endswith(".jar"):
                        z.write(os.path.join(mods_dir, f), f"mods/{f}")
        return True, output


# ============================================================
# 加载器版本解析器 - 实时获取各加载器可用版本
# ============================================================
class LoaderVersionResolver:
    """
    实时查询各模组加载器的可用版本。
    所有查询都有超时和缓存，失败时提供清晰的报错。
    支持: Fabric, Forge, Quilt, NeoForge, OptiFine, LiteLoader
    """

    # 缓存时间（秒）
    CACHE_TTL = 3600  # 1 小时

    def __init__(self, cache_dir=None):
        if cache_dir is None:
            cache_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "runtime", "version_cache"
            )
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)

    # ---- 缓存工具 ----

    def _cache_path(self, key):
        """获取缓存文件路径"""
        safe = re.sub(r'[^\w.-]', '_', key)
        return os.path.join(self.cache_dir, safe + ".json")

    def _cache_get(self, key):
        """读取缓存，过期返回 None"""
        path = self._cache_path(key)
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            if time.time() - data.get("cached_at", 0) > self.CACHE_TTL:
                return None
            return data.get("value")
        except Exception:
            return None

    def _cache_set(self, key, value):
        """写入缓存"""
        path = self._cache_path(key)
        data = {"cached_at": time.time(), "value": value}
        try:
            with open(path, 'w') as f:
                json.dump(data, f)
        except Exception:
            pass

    @staticmethod
    def _http_get_json(url, timeout=15):
        """发送 GET 请求并解析 JSON 响应"""
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())

    @staticmethod
    def _http_get_text(url, timeout=15):
        """发送 GET 请求并获取文本"""
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode()

    # ---- Fabric ----

    @staticmethod
    def _parse_maven_metadata_xml(xml_text):
        """解析 Maven maven-metadata.xml，返回版本列表"""
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml_text)
        versions = []
        for v in root.iter("version"):
            if v.text:
                versions.append(v.text)
        # 也尝试获取 latest/release
        latest = root.find("versioning/latest")
        release = root.find("versioning/release")
        info = {}
        if latest is not None and latest.text:
            info["latest"] = latest.text
        if release is not None and release.text:
            info["release"] = release.text
        return versions, info

    def get_fabric_versions(self, mc_version):
        """
        获取 Fabric 加载器版本列表（兼容指定 MC 版本）。
        返回: {"loader_versions": [...], "installer_versions": [...], "latest_loader": str, "latest_installer": str}
        """
        cache_key = f"fabric_versions_{mc_version}"
        cached = self._cache_get(cache_key)
        if cached:
            return cached

        result = {"loader_versions": [], "installer_versions": [], "latest_loader": "", "latest_installer": ""}

        # 查询加载器版本
        try:
            url = f"https://meta.fabricmc.net/v2/versions/loader/{mc_version}"
            data = self._http_get_json(url)
            for item in data:
                ver = item.get("version", "")
                if ver:
                    result["loader_versions"].append(ver)
            if result["loader_versions"]:
                result["latest_loader"] = result["loader_versions"][0]
        except Exception as e:
            logger.debug(f"Fabric loader 版本查询失败: {e}")

        # 查询安装器版本
        try:
            url = "https://maven.fabricmc.net/net/fabricmc/fabric-installer/maven-metadata.xml"
            xml_text = self._http_get_text(url)
            versions, info = self._parse_maven_metadata_xml(xml_text)
            result["installer_versions"] = versions
            result["latest_installer"] = info.get("release") or info.get("latest") or (versions[-1] if versions else "")
        except Exception as e:
            logger.debug(f"Fabric installer 版本查询失败: {e}")

        self._cache_set(cache_key, result)
        return result

    # ---- Forge ----

    def get_forge_versions(self, mc_version):
        """
        获取 Forge 版本列表（兼容指定 MC 版本）。
        返回: {"versions": [...], "recommended": str, "latest": str}
        """
        cache_key = f"forge_versions_{mc_version}"
        cached = self._cache_get(cache_key)
        if cached:
            return cached

        result = {"versions": [], "recommended": "", "latest": ""}

        # 方法 1: 通过 promotions_slim.json 获取推荐/最新版本
        try:
            promo_url = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
            promo = self._http_get_json(promo_url, timeout=20)
            promos = promo.get("promos", {})
            rec_key = f"{mc_version}-recommended"
            lat_key = f"{mc_version}-latest"
            if rec_key in promos:
                result["recommended"] = f"{mc_version}-{promos[rec_key]}"
            if lat_key in promos:
                result["latest"] = f"{mc_version}-{promos[lat_key]}"
        except Exception as e:
            logger.debug(f"Forge promotions 查询失败: {e}")

        # 方法 2: 直接查 Maven 元数据获取完整版本列表
        try:
            meta_url = f"https://files.minecraftforge.net/net/minecraftforge/forge/{mc_version}/maven-metadata.xml"
            xml_text = self._http_get_text(meta_url, timeout=20)
            versions, info = self._parse_maven_metadata_xml(xml_text)
            # 过滤出属于该 MC 版本的
            prefix = f"{mc_version}-"
            result["versions"] = [v for v in versions if v.startswith(prefix)]
            if not result["latest"] and result["versions"]:
                result["latest"] = result["versions"][-1]
            if not result["recommended"] and result["versions"]:
                result["recommended"] = result["versions"][-1]
        except Exception as e:
            logger.debug(f"Forge Maven 元数据查询失败: {e}")

        self._cache_set(cache_key, result)
        return result

    # ---- Quilt ----

    def get_quilt_versions(self, mc_version):
        """
        获取 Quilt 加载器版本列表。
        返回: {"loader_versions": [...], "installer_versions": [...], "latest_loader": str, "latest_installer": str}
        """
        cache_key = f"quilt_versions_{mc_version}"
        cached = self._cache_get(cache_key)
        if cached:
            return cached

        result = {"loader_versions": [], "installer_versions": [], "latest_loader": "", "latest_installer": ""}

        # 查询加载器版本
        try:
            url = f"https://meta.quiltmc.org/v3/versions/loader/{mc_version}"
            data = self._http_get_json(url)
            for item in data:
                ver = item.get("version", "")
                if ver:
                    result["loader_versions"].append(ver)
            if result["loader_versions"]:
                result["latest_loader"] = result["loader_versions"][0]
        except Exception as e:
            logger.debug(f"Quilt loader 版本查询失败: {e}")

        # 查询安装器版本
        try:
            url = "https://maven.quiltmc.org/repository/release/org/quiltmc/quilt-installer/maven-metadata.xml"
            xml_text = self._http_get_text(url)
            versions, info = self._parse_maven_metadata_xml(xml_text)
            result["installer_versions"] = versions
            result["latest_installer"] = info.get("release") or info.get("latest") or (versions[-1] if versions else "")
        except Exception as e:
            logger.debug(f"Quilt installer 版本查询失败: {e}")

        self._cache_set(cache_key, result)
        return result

    # ---- NeoForge ----

    def get_neoforge_versions(self, mc_version):
        """
        获取 NeoForge 版本列表。
        返回: {"versions": [...], "latest": str, "recommended": str}
        """
        cache_key = f"neoforge_versions_{mc_version}"
        cached = self._cache_get(cache_key)
        if cached:
            return cached

        result = {"versions": [], "latest": "", "recommended": ""}

        # 方法 1: 通过 promotions 获取
        try:
            promo_url = "https://maven.neoforged.net/releases/net/neoforged/neoforge/promotions_slim.json"
            promo = self._http_get_json(promo_url, timeout=20)
            promos = promo.get("promos", {})
            rec_key = f"{mc_version}-recommended"
            lat_key = f"{mc_version}-latest"
            if rec_key in promos:
                result["recommended"] = f"{mc_version}-{promos[rec_key]}"
            if lat_key in promos:
                result["latest"] = f"{mc_version}-{promos[lat_key]}"
        except Exception as e:
            logger.debug(f"NeoForge promotions 查询失败: {e}")

        # 方法 2: Maven 元数据
        try:
            meta_url = f"https://maven.neoforged.net/releases/net/neoforged/neoforge/{mc_version}/maven-metadata.xml"
            xml_text = self._http_get_text(meta_url, timeout=20)
            versions, info = self._parse_maven_metadata_xml(xml_text)
            prefix = f"{mc_version}-"
            result["versions"] = [v for v in versions if v.startswith(prefix)]
            if not result["latest"] and result["versions"]:
                result["latest"] = result["versions"][-1]
            if not result["recommended"] and result["versions"]:
                result["recommended"] = result["versions"][-1]
        except Exception as e:
            logger.debug(f"NeoForge Maven 元数据查询失败: {e}")

        self._cache_set(cache_key, result)
        return result

    # ---- OptiFine ----

    def get_optifine_versions(self, mc_version):
        """
        获取 OptiFine 版本列表。
        由于 OptiFine 没有公开 API，采用以下策略:
        1. 尝试从 BMCLAPI 镜像获取版本列表
        2. 失败时返回空列表
        返回: {"versions": [...], "latest": str}
        """
        cache_key = f"optifine_versions_{mc_version}"
        cached = self._cache_get(cache_key)
        if cached:
            return cached

        result = {"versions": [], "latest": ""}

        # BMCLAPI 提供 OptiFine 版本列表
        try:
            url = "https://bmclapi2.bangbang93.com/optifine/versionlist"
            data = self._http_get_json(url, timeout=20)
            # 格式: [{"name": "1.20.1_HD_U_I6", "mcversion": "1.20.1"}, ...]
            for item in data:
                if item.get("mcversion") == mc_version:
                    result["versions"].append(item.get("name", ""))
            # 按版本排序（粗略）
            result["versions"] = sorted(
                [v for v in result["versions"] if v],
                key=lambda x: x.split("_")[-1] if "_" in x else x,
                reverse=True
            )
            if result["versions"]:
                result["latest"] = result["versions"][0]
        except Exception as e:
            logger.debug(f"OptiFine 版本查询失败: {e}")

        # 备选: 尝试 OptiFine 官方（通常不可直接访问）
        if not result["versions"]:
            try:
                url = f"https://optifine.net/downloads"
                # 官方没有 JSON API，这里只做占位
            except Exception:
                pass

        self._cache_set(cache_key, result)
        return result

    # ---- LiteLoader ----

    def get_liteloader_versions(self, mc_version):
        """
        获取 LiteLoader 版本列表。
        返回: {"snapshots": [...], "latest": str}
        """
        cache_key = f"liteloader_versions_{mc_version}"
        cached = self._cache_get(cache_key)
        if cached:
            return cached

        result = {"snapshots": [], "latest": ""}

        try:
            url = f"http://dl.liteloader.com/api/versions/{mc_version}"
            data = self._http_get_json(url, timeout=20)
            versions = data.get("versions", {})
            for key, info in versions.items():
                snapshot = info.get("snapshot", "")
                if snapshot:
                    result["snapshots"].append({
                        "key": key,
                        "snapshot": snapshot,
                        "type": info.get("type", ""),
                        "minecraft": info.get("minecraft", mc_version),
                    })
            if result["snapshots"]:
                result["latest"] = result["snapshots"][-1]["snapshot"]
        except Exception as e:
            logger.debug(f"LiteLoader 版本查询失败: {e}")

        self._cache_set(cache_key, result)
        return result

    # ---- 统一查询入口 ----

    def get_all_loaders(self, mc_version):
        """
        一次性查询某 MC 版本下所有加载器的可用版本。
        返回字典: {loader_name: version_info}
        """
        return {
            "fabric": self.get_fabric_versions(mc_version),
            "forge": self.get_forge_versions(mc_version),
            "quilt": self.get_quilt_versions(mc_version),
            "neoforge": self.get_neoforge_versions(mc_version),
            "optifine": self.get_optifine_versions(mc_version),
            "liteloader": self.get_liteloader_versions(mc_version),
        }

    def clear_cache(self):
        """清除所有版本缓存"""
        if os.path.isdir(self.cache_dir):
            for f in os.listdir(self.cache_dir):
                if f.endswith(".json"):
                    try:
                        os.remove(os.path.join(self.cache_dir, f))
                    except Exception:
                        pass
            return True, f"已清除 {self.cache_dir} 下的缓存文件"
        return False, "缓存目录不存在"


# ============================================================
# 加载器安装器 - 真正实现各加载器的自动安装
# ============================================================
class LoaderInstaller:
    """
    各模组加载器的自动安装器。
    支持: Fabric, Forge, Quilt, NeoForge, LiteLoader, OptiFine
    """

    # ---- 公共工具方法 ----

    @staticmethod
    def _find_installer_jar(loader_name, mc_version):
        """在本地查找已下载的安装器 jar"""
        # 搜索启动器目录和 runtime 目录
        search_dirs = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime", "installers"),
            os.path.dirname(os.path.abspath(__file__)),
        ]
        keywords = {
            "fabric": "fabric-installer",
            "forge": f"forge-{mc_version}",
            "quilt": "quilt-installer",
            "neoforge": f"neoforge-{mc_version}",
            "optifine": f"OptiFine_{mc_version}",
            "liteloader": "liteloader",
        }
        kw = keywords.get(loader_name, loader_name)
        for d in search_dirs:
            if not os.path.isdir(d):
                continue
            for f in os.listdir(d):
                if kw.lower() in f.lower() and f.endswith(".jar"):
                    return os.path.join(d, f)
        return None

    @staticmethod
    def _download_file(url, dest, sha1=None, progress=True):
        """下载文件到指定位置"""
        os.makedirs(os.path.dirname(dest) if os.path.dirname(dest) else ".", exist_ok=True)
        dl = DownloadEngine()
        return dl.download(url, dest, sha1=sha1, progress=progress)

    @staticmethod
    def _run_installer(java_path, jar_path, args_list, cwd=None):
        """运行 Java 安装器"""
        cmd = [java_path, "-jar", jar_path] + args_list
        logger.info(f"运行: {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=cwd)
            if result.returncode == 0:
                logger.info("安装器执行成功")
                if result.stdout.strip():
                    logger.debug(result.stdout.strip()[:2000])
                return True, result.stdout
            else:
                logger.error(f"安装器失败 (退出码 {result.returncode})")
                if result.stderr.strip():
                    logger.error(result.stderr.strip()[:2000])
                return False, result.stderr
        except subprocess.TimeoutExpired:
            return False, "安装器执行超时（5分钟）"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def _ensure_installer_dir():
        """确保安装器目录存在"""
        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime", "installers")
        os.makedirs(d, exist_ok=True)
        return d

    # ---- Fabric 安装 ----

    @staticmethod
    def install_fabric(java_path, mc_version, game_dir, loader_version=None):
        """
        安装 Fabric 加载器。
        实时查询 Fabric Meta API 获取可用加载器版本。
        从 Maven 仓库下载官方安装器并执行。
        """
        logger.info(f"正在安装 Fabric 加载器 (MC {mc_version})...")

        # 实时查询可用版本
        resolver = LoaderVersionResolver()
        fabric_info = resolver.get_fabric_versions(mc_version)

        # 确定加载器版本
        if not loader_version:
            if fabric_info.get("latest_loader"):
                loader_version = fabric_info["latest_loader"]
                logger.info(f"自动选择最新 Fabric 加载器: {loader_version}")
            else:
                return False, f"无法获取 Fabric 加载器版本列表（MC {mc_version}）"

        # 显示可用版本信息
        loader_versions = fabric_info.get("loader_versions", [])
        if loader_versions:
            logger.info(f"可用 Fabric 加载器版本: {len(loader_versions)} 个")
            if len(loader_versions) > 1:
                logger.debug(f"  最新: {loader_versions[0]}, 最旧: {loader_versions[-1]}")

        # 查找或下载 Fabric 安装器
        installer_dir = LoaderInstaller._ensure_installer_dir()
        installer_path = None

        # 尝试查找本地安装器
        for f in os.listdir(installer_dir):
            if "fabric-installer" in f and f.endswith(".jar"):
                installer_path = os.path.join(installer_dir, f)
                logger.info(f"使用已存在的安装器: {f}")
                break

        # 下载最新安装器
        if not installer_path:
            installer_ver = fabric_info.get("latest_installer", "")
            if installer_ver:
                installer_url = f"https://maven.fabricmc.net/net/fabricmc/fabric-installer/{installer_ver}/fabric-installer-{installer_ver}.jar"
                installer_path = os.path.join(installer_dir, f"fabric-installer-{installer_ver}.jar")
            else:
                # 从 Maven 元数据获取
                meta_url = "https://maven.fabricmc.net/net/fabricmc/fabric-installer/maven-metadata.xml"
                try:
                    req = urllib.request.Request(meta_url)
                    with urllib.request.urlopen(req, timeout=30) as r:
                        meta_xml = r.read().decode()
                    import xml.etree.ElementTree as ET
                    root = ET.fromstring(meta_xml)
                    installer_ver = root.find("versioning/release").text
                    installer_url = f"https://maven.fabricmc.net/net/fabricmc/fabric-installer/{installer_ver}/fabric-installer-{installer_ver}.jar"
                    installer_path = os.path.join(installer_dir, f"fabric-installer-{installer_ver}.jar")
                except Exception as e:
                    return False, f"获取 Fabric 安装器信息失败: {e}"

            logger.info(f"下载 Fabric 安装器 v{installer_ver}...")
            ok, msg = LoaderInstaller._download_file(installer_url, installer_path, progress=True)
            if not ok:
                return False, f"下载安装器失败: {msg}"

        # 运行安装器
        args = [
            "client",
            "-dir", game_dir,
            "-mcversion", mc_version,
            "-loaderversion", loader_version,
        ]
        args += ["-downloadMinecraft"]  # 自动下载 MC

        ok, output = LoaderInstaller._run_installer(java_path, installer_path, args)
        if ok:
            return True, f"Fabric {loader_version} 已安装到 {game_dir}"
        return False, output

    # ---- Forge 安装 ----

    @staticmethod
    def install_forge(java_path, mc_version, game_dir):
        """
        安装 Forge 加载器。
        实时从 Forge 官方查询兼容的版本列表，自动选择推荐/最新版。
        """
        logger.info(f"正在安装 Forge 加载器 (MC {mc_version})...")

        # 实时查询可用版本
        resolver = LoaderVersionResolver()
        forge_info = resolver.get_forge_versions(mc_version)

        # 选择版本优先级: recommended > latest > 列表最后一个
        forge_ver = ""
        if forge_info.get("recommended"):
            forge_ver = forge_info["recommended"]
            logger.info(f"使用推荐版本: {forge_ver}")
        elif forge_info.get("latest"):
            forge_ver = forge_info["latest"]
            logger.info(f"使用最新版本: {forge_ver}")
        elif forge_info.get("versions"):
            forge_ver = forge_info["versions"][-1]
            logger.info(f"使用可用版本: {forge_ver}")

        if not forge_ver:
            return False, (
                f"未找到 MC {mc_version} 对应的 Forge 版本。\n"
                f"  可尝试:\n"
                f"    1. 检查网络连通性\n"
                f"    2. 手动从 https://files.minecraftforge.net/ 下载\n"
                f"    3. 使用其他加载器（fabric/quilt/neoforge）"
            )

        logger.info(f"Forge 版本: {forge_ver}")

        # 下载安装器
        installer_dir = LoaderInstaller._ensure_installer_dir()
        installer_name = f"forge-{forge_ver}-installer.jar"
        installer_path = os.path.join(installer_dir, installer_name)

        if not os.path.exists(installer_path):
            urls = [
                f"https://files.minecraftforge.net/net/minecraftforge/forge/{forge_ver}/forge-{forge_ver}-installer.jar",
                f"https://maven.minecraftforge.net/net/minecraftforge/forge/{forge_ver}/forge-{forge_ver}-installer.jar",
                f"https://bmclapi2.bangbang93.com/maven/net/minecraftforge/forge/{forge_ver}/forge-{forge_ver}-installer.jar",
            ]
            downloaded = False
            for url in urls:
                logger.info(f"下载 Forge 安装器: {url}")
                ok, msg = LoaderInstaller._download_file(url, installer_path, progress=True)
                if ok:
                    downloaded = True
                    break
                logger.warning(f"源失败: {msg}")

            if not downloaded:
                return False, f"下载 Forge 安装器失败（已尝试 {len(urls)} 个源）"

        # 运行安装器
        args = ["--installClient", game_dir]
        ok, output = LoaderInstaller._run_installer(java_path, installer_path, args)
        if ok:
            return True, f"Forge {forge_ver} 已安装到 {game_dir}"
        return False, output

    # ---- Quilt 安装 ----

    @staticmethod
    def install_quilt(java_path, mc_version, game_dir, loader_version=None):
        """
        安装 Quilt 加载器。
        实时查询 Quilt Meta API 获取可用加载器版本。
        从 Quilt Maven 下载安装器并执行。
        """
        logger.info(f"正在安装 Quilt 加载器 (MC {mc_version})...")

        # 实时查询可用版本
        resolver = LoaderVersionResolver()
        quilt_info = resolver.get_quilt_versions(mc_version)

        # 确定加载器版本
        if not loader_version:
            if quilt_info.get("latest_loader"):
                loader_version = quilt_info["latest_loader"]
                logger.info(f"自动选择最新 Quilt 加载器: {loader_version}")
            else:
                return False, f"无法获取 Quilt 加载器版本列表（MC {mc_version}）"

        # 显示可用版本信息
        loader_versions = quilt_info.get("loader_versions", [])
        if loader_versions:
            logger.info(f"可用 Quilt 加载器版本: {len(loader_versions)} 个")

        # 下载安装器
        installer_dir = LoaderInstaller._ensure_installer_dir()
        installer_path = None

        # 查找已有安装器
        for f in os.listdir(installer_dir):
            if "quilt-installer" in f and f.endswith(".jar"):
                installer_path = os.path.join(installer_dir, f)
                logger.info(f"使用已存在的安装器: {f}")
                break

        if not installer_path:
            installer_ver = quilt_info.get("latest_installer", "")
            if installer_ver:
                installer_url = f"https://maven.quiltmc.org/repository/release/org/quiltmc/quilt-installer/{installer_ver}/quilt-installer-{installer_ver}.jar"
                installer_path = os.path.join(installer_dir, f"quilt-installer-{installer_ver}.jar")
            else:
                # 从 Maven 元数据获取
                try:
                    import xml.etree.ElementTree as ET
                    meta_url = "https://maven.quiltmc.org/repository/release/org/quiltmc/quilt-installer/maven-metadata.xml"
                    req = urllib.request.Request(meta_url)
                    with urllib.request.urlopen(req, timeout=30) as r:
                        meta_xml = r.read().decode()
                    root = ET.fromstring(meta_xml)
                    installer_ver = root.find("versioning/release").text
                    installer_url = f"https://maven.quiltmc.org/repository/release/org/quiltmc/quilt-installer/{installer_ver}/quilt-installer-{installer_ver}.jar"
                    installer_path = os.path.join(installer_dir, f"quilt-installer-{installer_ver}.jar")
                except Exception as e:
                    return False, f"获取 Quilt 安装器信息失败: {e}"

            logger.info(f"下载 Quilt 安装器 v{installer_ver}...")
            ok, msg = LoaderInstaller._download_file(installer_url, installer_path, progress=True)
            if not ok:
                return False, f"下载 Quilt 安装器失败: {msg}"

        # 构建参数
        args = ["install", "client", mc_version, "--loader", loader_version]

        ok, output = LoaderInstaller._run_installer(java_path, installer_path, args, cwd=game_dir)
        if ok:
            return True, f"Quilt {loader_version} 已安装到 {game_dir}"
        return False, output

    # ---- NeoForge 安装 ----

    @staticmethod
    def install_neoforge(java_path, mc_version, game_dir):
        """
        安装 NeoForge 加载器（Forge 的社区分支）。
        实时从 NeoForged Maven 查询兼容版本。
        """
        logger.info(f"正在安装 NeoForge 加载器 (MC {mc_version})...")

        # 实时查询可用版本
        resolver = LoaderVersionResolver()
        nf_info = resolver.get_neoforge_versions(mc_version)

        # 选择版本优先级: recommended > latest > 列表最后一个
        nf_ver = ""
        if nf_info.get("recommended"):
            nf_ver = nf_info["recommended"]
            logger.info(f"使用推荐版本: {nf_ver}")
        elif nf_info.get("latest"):
            nf_ver = nf_info["latest"]
            logger.info(f"使用最新版本: {nf_ver}")
        elif nf_info.get("versions"):
            nf_ver = nf_info["versions"][-1]
            logger.info(f"使用可用版本: {nf_ver}")

        if not nf_ver:
            return False, (
                f"未找到 MC {mc_version} 对应的 NeoForge 版本。\n"
                f"  可尝试:\n"
                f"    1. 检查网络连通性\n"
                f"    2. 手动从 https://neoforged.net/ 下载\n"
                f"    3. 使用其他加载器（fabric/forge/quilt）"
            )

        logger.info(f"NeoForge 版本: {nf_ver}")

        # 下载安装器
        installer_dir = LoaderInstaller._ensure_installer_dir()
        installer_name = f"neoforge-{nf_ver}-installer.jar"
        installer_path = os.path.join(installer_dir, installer_name)

        if not os.path.exists(installer_path):
            urls = [
                f"https://maven.neoforged.net/releases/net/neoforged/neoforge/{nf_ver}/neoforge-{nf_ver}-installer.jar",
                f"https://bmclapi2.bangbang93.com/maven/net/neoforged/neoforge/{nf_ver}/neoforge-{nf_ver}-installer.jar",
            ]
            downloaded = False
            for url in urls:
                logger.info(f"下载 NeoForge 安装器...")
                ok, msg = LoaderInstaller._download_file(url, installer_path, progress=True)
                if ok:
                    downloaded = True
                    break
                logger.warning(f"源失败: {msg}")

            if not downloaded:
                return False, f"下载 NeoForge 安装器失败（已尝试 {len(urls)} 个源）"

        args = ["--installClient", game_dir]
        ok, output = LoaderInstaller._run_installer(java_path, installer_path, args)
        if ok:
            return True, f"NeoForge {nf_ver} 已安装到 {game_dir}"
        return False, output

    # ---- OptiFine 安装 ----

    @staticmethod
    def install_optifine(java_path, mc_version, game_dir):
        """
        安装 OptiFine。
        实时从 BMCLAPI 镜像查询可用版本列表。
        """
        logger.info(f"正在安装 OptiFine (MC {mc_version})...")

        # 实时查询可用版本
        resolver = LoaderVersionResolver()
        of_info = resolver.get_optifine_versions(mc_version)

        if not of_info.get("versions"):
            return False, (
                f"未找到 MC {mc_version} 对应的 OptiFine 版本。\n"
                f"  可尝试:\n"
                f"    1. 检查网络连通性\n"
                f"    2. 手动从 https://optifine.net/downloads 下载\n"
                f"    3. 使用其他加载器（fabric+钠/iris 等替代方案）"
            )

        # 选择最新版本
        of_name = of_info.get("latest") or of_info["versions"][0]
        logger.info(f"OptiFine 版本: {of_name}（共 {len(of_info['versions'])} 个可用版本）")

        installer_dir = LoaderInstaller._ensure_installer_dir()
        installer_path = os.path.join(installer_dir, f"{of_name}.jar")

        if not os.path.exists(installer_path):
            urls = [
                f"https://bmclapi2.bangbang93.com/optifine/{mc_version}/HD_U",
                f"https://bmclapi2.bangbang93.com/optifine/download/{of_name}",
                f"https://optifine.net/adloadx?f={of_name}.jar",
            ]
            downloaded = False
            for url in urls:
                logger.info(f"尝试下载 OptiFine: {of_name}")
                ok, msg = LoaderInstaller._download_file(url, installer_path, progress=True)
                if ok:
                    downloaded = True
                    break
                logger.warning(f"源失败: {msg}")

            if not downloaded:
                return False, f"下载 OptiFine 失败（已尝试 {len(urls)} 个源）"

        # OptiFine 安装器
        args = ["--install", game_dir]
        ok, output = LoaderInstaller._run_installer(java_path, installer_path, args)
        if ok:
            return True, f"OptiFine {of_name} 已安装到 {game_dir}"
        return False, output

    # ---- LiteLoader 安装 ----

    @staticmethod
    def install_liteloader(java_path, mc_version, game_dir):
        """
        安装 LiteLoader。
        实时查询 LiteLoader API 获取可用快照列表。
        """
        logger.info(f"正在安装 LiteLoader (MC {mc_version})...")

        # 实时查询可用版本
        resolver = LoaderVersionResolver()
        ll_info = resolver.get_liteloader_versions(mc_version)

        snapshots = ll_info.get("snapshots", [])
        if not snapshots:
            return False, (
                f"LiteLoader 不支持 MC {mc_version}，或未找到可用快照。\n"
                f"  可尝试:\n"
                f"    1. 检查网络连通性\n"
                f"    2. 访问 http://www.liteloader.com/download/ 手动下载"
            )

        # 选择最新快照
        latest = snapshots[-1]
        snapshot = latest["snapshot"]
        logger.info(f"LiteLoader 快照: {snapshot}（共 {len(snapshots)} 个可用）")
        logger.debug(f"  类型: {latest.get('type', 'unknown')}")

        # 下载安装器
        installer_dir = LoaderInstaller._ensure_installer_dir()
        installer_name = f"liteloader-{snapshot}.jar"
        installer_path = os.path.join(installer_dir, installer_name)

        if not os.path.exists(installer_path):
            urls = [
                f"http://dl.liteloader.com/download/{snapshot}/liteloader-{snapshot}.jar",
                f"https://bmclapi2.bangbang93.com/liteloader/download/{snapshot}/liteloader-{snapshot}.jar",
            ]
            downloaded = False
            for url in urls:
                logger.info(f"下载 LiteLoader...")
                ok, msg = LoaderInstaller._download_file(url, installer_path, progress=True)
                if ok:
                    downloaded = True
                    break
                logger.warning(f"源失败: {msg}")

            if not downloaded:
                return False, f"下载 LiteLoader 失败（已尝试 {len(urls)} 个源）"

        # LiteLoader 安装器
        args = ["--install", game_dir, "--mcversion", mc_version]
        ok, output = LoaderInstaller._run_installer(java_path, installer_path, args)
        if ok:
            return True, f"LiteLoader {snapshot} 已安装到 {game_dir}"
        return False, output

    # ---- 统一入口 ----

    @staticmethod
    def install(loader, java_path, mc_version, game_dir, loader_version=None):
        """
        统一安装入口。
        根据 loader 类型分发到对应的安装方法。
        支持可选参数 loader_version 指定具体加载器版本。
        """
        loader = loader.lower()

        # 确保目标目录存在
        os.makedirs(game_dir, exist_ok=True)

        if loader == "fabric":
            return LoaderInstaller.install_fabric(java_path, mc_version, game_dir, loader_version)
        elif loader == "forge":
            return LoaderInstaller.install_forge(java_path, mc_version, game_dir)
        elif loader == "quilt":
            return LoaderInstaller.install_quilt(java_path, mc_version, game_dir, loader_version)
        elif loader == "neoforge":
            return LoaderInstaller.install_neoforge(java_path, mc_version, game_dir)
        elif loader == "optifine":
            return LoaderInstaller.install_optifine(java_path, mc_version, game_dir)
        elif loader == "liteloader":
            return LoaderInstaller.install_liteloader(java_path, mc_version, game_dir)
        else:
            return False, f"不支持的加载器: {loader}。\n" \
                         f"可选: fabric, forge, quilt, neoforge, optifine, liteloader"


# ============================================================
# 命令行接口
# ============================================================
class CLI:
    """命令行交互处理器"""

    def __init__(self, state):
        self.state = state
        self.env = None
        self.launcher = None

    def _ensure_env(self):
        if self.env is None:
            self.env = self.state.get_env_manager()
        return self.env

    def _ensure_launcher(self):
        if self.launcher is None:
            self.launcher = GameLauncher(self.state)
        return self.launcher

    # ---- 认证相关 ----

    def cmd_lgn(self, args):
        """
        lgn - 登录
        流程:
          1. 输入用户名
          2. 询问登录方式（正版 / 离线）
          3. 如果该账号首次使用 → 设置本地密码（输两遍确认）
          4. 如果该账号已注册 → 输入本地密码验证
          5. 通过后执行对应登录流程
        """
        print(f"{C.BOLD}登录{C.RESET}")
        name = input("name: ").strip()
        if not name:
            print(f"{C.RED}用户名不能为空。{C.RESET}")
            return

        accounts_dir = self.state.accounts_dir
        is_new = not AccountStore.account_exists(name, accounts_dir)

        # ---- 本地密码处理 ----
        if is_new:
            # 新账号：询问是否设置密码
            print(f"{C.CYAN}这是新账号 '{name}'，是否设置启动器本地密码？{C.RESET}")
            set_pw = input("设置密码？(Y/n): ").strip().lower()
            if set_pw == 'n' or set_pw == 'no':
                # 不设置密码，直接创建无密码账号
                ok, msg = AccountStore.create_account(name, "dummy_pw", accounts_dir)
                # 写入标记：无密码
                path = AccountStore._account_path(name, accounts_dir)
                with open(path, 'r') as f:
                    d = json.load(f)
                d["has_password"] = False
                d.pop("salt", None)
                d.pop("hash", None)
                with open(path, 'w') as f:
                    json.dump(d, f, indent=2)
                print(f"{C.YELLOW}已创建无密码账号 '{name}'{C.RESET}")
            else:
                # 设置密码：输两遍
                while True:
                    pw1 = getpass.getpass("设置密码: ")
                    pw2 = getpass.getpass("再次输入密码: ")
                    if pw1 != pw2:
                        print(f"{C.RED}两次输入不一致，请重新输入。{C.RESET}")
                        continue
                    if not pw1:
                        print(f"{C.RED}密码不能为空。{C.RESET}")
                        continue
                    ok, msg = AccountStore.create_account(name, pw1, accounts_dir)
                    if ok:
                        print(f"{C.GREEN}{msg}{C.RESET}")
                        break
                    else:
                        print(f"{C.RED}{msg}{C.RESET}")
                        return
        else:
            # 已有账号：验证密码
            path = AccountStore._account_path(name, accounts_dir)
            with open(path, 'r') as f:
                acct_data = json.load(f)

            if acct_data.get("has_password", True):
                print(f"{C.CYAN}请输入 '{name}' 的本地密码:{C.RESET}")
                pw = getpass.getpass("password: ")
                ok, msg, _ = AccountStore.verify_password(name, pw, accounts_dir)
                if not ok:
                    print(f"{C.RED}{msg}{C.RESET}")
                    # 允许重试
                    for attempt in range(2):
                        pw = getpass.getpass(f"重试 (还剩 {2-attempt} 次): ")
                        ok, msg, _ = AccountStore.verify_password(name, pw, accounts_dir)
                        if ok:
                            print(f"{C.GREEN}密码正确{C.RESET}")
                            break
                        else:
                            print(f"{C.RED}{msg}{C.RESET}")
                    else:
                        print(f"{C.RED}密码错误次数过多，登录失败。{C.RESET}")
                        return
                else:
                    print(f"{C.GREEN}密码正确{C.RESET}")
            else:
                print(f"{C.YELLOW}该账号未设置密码，直接登录。{C.RESET}")

        # ---- 选择登录方式 ----
        login_type = _ask_login_type()
        if login_type is None:
            print(f"{C.YELLOW}已取消登录。{C.RESET}")
            return

        if login_type == 'msa':
            self._login_microsoft(name)
        else:
            self._offline_login(name)

    def _login_microsoft(self, name):
        """执行 Microsoft OAuth2 设备代码流登录"""
        print(f"\n{C.CYAN}正在向 Microsoft 申请设备代码...{C.RESET}")
        ok, msg, data = Auth.request_device_code()
        if not ok:
            print(f"{C.RED}获取设备代码失败: {msg}{C.RESET}")
            print(f"{C.YELLOW}回退到离线登录...{C.RESET}")
            self._offline_login(name)
            return

        print(f"\n{C.BOLD}请访问:{C.RESET} {C.BRIGHT_BLUE}{data.get('verification_uri', '')}{C.RESET}")
        print(f"{C.BOLD}输入代码:{C.RESET} {C.BRIGHT_GREEN}{data.get('user_code', '')}{C.RESET}")
        print(f"{C.DIM}等待认证完成（{data.get('expires_in', 900)}秒后超时）...{C.RESET}")

        device_code = data.get("device_code", "")
        interval = data.get("interval", 5)
        expires_in = data.get("expires_in", 900)

        ok, msg, tokens = Auth.poll_for_token(device_code, interval, expires_in)
        if not ok:
            print(f"{C.RED}认证失败: {msg}{C.RESET}")
            return

        try:
            xbl_token = tokens["access_token"]
            xbl_data = {
                "Properties": {
                    "AuthMethod": "RPS",
                    "SiteName": "user.auth.xboxlive.com",
                    "RpsTicket": f"d={xbl_token}"
                },
                "RelyingParty": "http://auth.xboxlive.com",
                "TokenType": "JWT"
            }
            xbl_resp = Auth._post_json(Auth.U_XBL, xbl_data)
            xbl_t = xbl_resp["Token"]
            uh = xbl_resp["DisplayClaims"]["xui"][0]["uhs"]

            xsts_data = {
                "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbl_t]},
                "RelyingParty": "rp://api.minecraftservices.com/",
                "TokenType": "JWT"
            }
            xsts_resp = Auth._post_json(Auth.U_XSTS, xsts_data)
            xsts_t = xsts_resp["Token"]

            mc_data = {"xtoken": f"XBL3.0 x={uh};{xsts_t}"}
            mc_resp = Auth._post_json(Auth.U_MC, mc_data)
            mc_token = mc_resp["access_token"]

            req = urllib.request.Request(
                Auth.U_PROF, headers={"Authorization": f"Bearer {mc_token}"})
            with urllib.request.urlopen(req, timeout=30) as r:
                profile = json.loads(r.read().decode())

            self.state.username = profile.get("name", name)
            self.state.uuid_str = profile.get("id", "")
            self.state.access_token = mc_token
            self.state.auth_type = "msa"
            self.state.ms_refresh_token = tokens.get("refresh_token", "")
            self.state.mc_expires_at = time.time() + 86400
            self.state.logged_in = True

            print(f"{C.BRIGHT_GREEN}已登录为 {self.state.username}（Microsoft 正版）{C.RESET}")
            if os.path.exists(self.state.auth_file):
                self._save_auth()
        except Exception as e:
            print(f"{C.RED}认证流程失败: {e}{C.RESET}")
            return

    def _offline_login(self, name):
        """离线模式登录"""
        self.state.username = name
        self.state.uuid_str = uuid.uuid3(uuid.NAMESPACE_DNS, f"offline:{name}").hex
        self.state.access_token = "offline"
        self.state.auth_type = "offline"
        self.state.logged_in = True
        print(f"{C.BRIGHT_GREEN}已登录为 {name}（离线模式）{C.RESET}")

    def _save_auth(self):
        data = {
            "username": self.state.username,
            "uuid": self.state.uuid_str,
            "access_token": self.state.access_token,
            "auth_type": self.state.auth_type,
            "ms_refresh_token": self.state.ms_refresh_token,
            "mc_expires_at": self.state.mc_expires_at,
        }
        with open(self.state.auth_file, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"{C.GREEN}登录信息已保存到 {self.state.auth_file}{C.RESET}")

    def cmd_lgt(self, args):
        """lgt - 注销"""
        old_user = self.state.username
        self.state.logged_in = False
        self.state.username = ""
        self.state.uuid_str = ""
        self.state.access_token = ""
        self.state.auth_type = ""
        self.state.ms_refresh_token = ""
        self.state.mc_expires_at = 0
        if old_user:
            print(f"{C.YELLOW}用户 '{old_user}' 已注销。{C.RESET}")
        else:
            print(f"{C.YELLOW}已注销。{C.RESET}")

    def cmd_stlgn(self, args):
        """
        stlgn - 保存登录信息（下次自动登录）
        如果账号有本地密码，自动登录时仍需验证。
        """
        if not self.state.logged_in:
            print(f"{C.RED}尚未登录，请先使用 'lgn' 命令登录。{C.RESET}")
            return
        self._save_auth()

    def cmd_csli(self, args):
        """csli - 取消自动登录"""
        if os.path.exists(self.state.auth_file):
            os.remove(self.state.auth_file)
            print(f"{C.GREEN}已取消自动登录。{C.RESET}")
        else:
            print(f"{C.YELLOW}自动登录未启用。{C.RESET}")

    def _load_auth(self):
        """
        启动时尝试自动登录。
        如果对应账号有本地密码，则提示输入密码验证后才能自动登录。
        """
        if not os.path.exists(self.state.auth_file):
            return False
        try:
            with open(self.state.auth_file, 'r') as f:
                data = json.load(f)
            username = data.get("username", "")
            auth_type = data.get("auth_type", "")
            self.state.username = username
            self.state.uuid_str = data.get("uuid", "")
            self.state.access_token = data.get("access_token", "")
            self.state.auth_type = auth_type
            self.state.ms_refresh_token = data.get("ms_refresh_token", "")
            self.state.mc_expires_at = data.get("mc_expires_at", 0)

            # 检查该账号是否有本地密码
            accounts_dir = self.state.accounts_dir
            if AccountStore.account_exists(username, accounts_dir):
                with open(AccountStore._account_path(username, accounts_dir), 'r') as f:
                    acct = json.load(f)
                if acct.get("has_password", False):
                    print(f"{C.CYAN}账号 '{username}' 已保存登录信息，请输入本地密码以自动登录:{C.RESET}")
                    for attempt in range(3):
                        pw = getpass.getpass(f"password (还剩 {3-attempt} 次): ")
                        ok, msg, _ = AccountStore.verify_password(username, pw, accounts_dir)
                        if ok:
                            print(f"{C.GREEN}密码正确，自动登录成功{C.RESET}")
                            break
                        else:
                            print(f"{C.RED}{msg}{C.RESET}")
                    else:
                        print(f"{C.RED}密码错误次数过多，取消自动登录。{C.RESET}")
                        self.state.logged_in = False
                        return False

            # 刷新过期的 MSA token
            if auth_type == "msa" and time.time() > self.state.mc_expires_at - 300:
                if self.state.ms_refresh_token:
                    ok, msg, r = Auth.refresh_token(self.state.ms_refresh_token)
                    if ok:
                        self.state.access_token = r["access_token"]
                        self.state.ms_refresh_token = r.get("refresh_token", self.state.ms_refresh_token)
                        self.state.mc_expires_at = time.time() + r.get("expires_in", 86400)

            self.state.logged_in = True
            print(f"{C.GREEN}已自动登录为 {username}{C.RESET}")
            return True
        except Exception as e:
            logger.debug(f"加载登录信息失败: {e}")
            return False

    def cmd_ch_pw(self, args):
        """
        ch_pw - 修改/关闭账号本地密码
        用法:
          ch_pw                    → 修改当前已登录账号的密码
          ch_pw <用户名>           → 修改指定账号的密码
          ch_pw <用户名> (新密码空) → 关闭该账号的密码
        逻辑:
          输入非空字符串 → 更改密码（需先验证旧密码）
          输入空字符串   → 关闭密码
        """
        accounts_dir = self.state.accounts_dir

        # 确定目标账号
        if args:
            target_user = args[0]
        elif self.state.logged_in:
            target_user = self.state.username
        else:
            print(f"{C.RED}未指定用户名且未登录。用法: ch_pw [用户名]{C.RESET}")
            return

        if not AccountStore.account_exists(target_user, accounts_dir):
            print(f"{C.RED}账号 '{target_user}' 不存在。{C.RESET}")
            return

        # 先验证旧密码（如果当前有密码设置）
        path = AccountStore._account_path(target_user, accounts_dir)
        with open(path, 'r') as f:
            acct = json.load(f)

        if acct.get("has_password", True):
            old_pw = getpass.getpass(f"请输入 '{target_user}' 的旧密码: ")
        else:
            old_pw = ""
            print(f"{C.YELLOW}该账号当前未设置密码。{C.RESET}")

        # 输入新密码
        print(f"{C.CYAN}请输入新密码（直接回车 = 关闭密码）:{C.RESET}")
        new_pw1 = getpass.getpass("新密码: ")
        if new_pw1:
            new_pw2 = getpass.getpass("再次输入新密码: ")
            if new_pw1 != new_pw2:
                print(f"{C.RED}两次输入不一致，操作取消。{C.RESET}")
                return

        ok, msg = AccountStore.change_password(target_user, old_pw, new_pw1, accounts_dir)
        if ok:
            if new_pw1:
                print(f"{C.GREEN}{msg}{C.RESET}")
            else:
                print(f"{C.YELLOW}{msg}{C.RESET}")
        else:
            print(f"{C.RED}{msg}{C.RESET}")

    # ---- 版本管理 ----

    def cmd_lsv(self, args):
        """lsv - 列出可用版本

        用法:
          lsv                 列出最近 50 个版本（默认，从缓存）
          lsv -5              从缓存列出最近 5 个版本
          lsv -10             从缓存列出最近 10 个版本
          lsv -100            从缓存列出最近 100 个版本
          lsv -a              列出全部版本（缓存）
          lsv -f              强制从网络获取并列出最近 50 个
          lsv -f -5           强制从网络获取并列出最近 5 个
          lsv -f -a           强制从网络获取并列出全部版本
          lsv --help          显示帮助信息

        参数说明:
          -N            数字 N 表示显示最近 N 个版本，例如 -5、-20、-100
          -a, --all     显示全部版本（与 -N 互斥，同时出现时 -N 优先）
          -f, --force   强制从网络重新获取版本清单（忽略缓存）
          --help        显示帮助

        参数顺序无关，-f 和 -N/-a 可任意排列组合。
        """
        # ---- 参数解析 ----
        force = False
        limit = 50          # 默认 50
        show_all = False
        explicit_limit = False  # 是否用户显式指定了 -N

        i = 0
        while i < len(args):
            a = args[i]
            if a == "-f" or a == "--force":
                force = True
            elif a == "-a" or a == "--all":
                show_all = True
            elif a == "--help" or a == "-h":
                print(self.cmd_lsv.__doc__)
                return
            elif a.startswith("-") and a[1:].isdigit():
                # -N 形式，例如 -5 表示最近 5 个
                limit = int(a[1:])
                explicit_limit = True
                show_all = False   # -N 优先生效，覆盖 -a
            elif a.startswith("--limit="):
                limit = int(a.split("=", 1)[1])
                explicit_limit = True
                show_all = False
            else:
                print(f"{C.RED}未知参数: {a}{C.RESET}")
                print(f"{C.DIM}用法: lsv [-f] [-a] [-N] [--limit=N] [--help]{C.RESET}")
                print(f"{C.DIM}示例: lsv -5  |  lsv -f -20  |  lsv -a  |  lsv -f -a{C.RESET}")
                return
            i += 1

        # 确定最终限制
        if show_all:
            final_limit = None   # 无限制
        else:
            final_limit = limit  # 使用默认 50 或用户指定的 -N

        # ---- 获取版本清单 ----
        launcher = self._ensure_launcher()
        manifest = launcher.fetch_manifest(force=force)

        if not manifest:
            print(f"{C.RED}获取版本清单失败。{C.RESET}")
            return

        # 按发布时间倒序排列
        versions = sorted(manifest.get("versions", []),
                         key=lambda v: v.get("releaseTime", ""), reverse=True)

        total = len(versions)

        # 应用数量限制
        if final_limit is None:
            display_versions = versions
            limit_info = f"全部 {total} 个"
        else:
            display_versions = versions[:final_limit]
            if final_limit >= total:
                limit_info = f"共 {total} 个"
            else:
                limit_info = f"最近 {final_limit} 个（共 {total} 个）"

        source = "网络" if force else "缓存"
        force_tag = f"{C.YELLOW}[强制刷新]{C.RESET} " if force else ""
        print(f"\n{force_tag}{C.BOLD}可用的 Minecraft 版本 ({limit_info}, 来源: {source}):{C.RESET}")
        print(f"{C.DIM}{'序号':<6} {'版本':<24} {'类型':<12} {'发布日期':<12} {'状态'}{C.RESET}")
        print(f"{C.DIM}{'-'*68}{C.RESET}")

        for idx, v in enumerate(display_versions, 1):
            vid = v.get("id", "")
            vtype = v.get("type", "")
            rtime = v.get("releaseTime", "")[:10]

            # 颜色规则：正式版绿色、快照版黄色、古早版灰色
            if vtype == "release":
                color = C.GREEN
            elif vtype == "snapshot":
                color = C.YELLOW
            elif "alpha" in vid.lower() or "beta" in vid.lower() \
                 or "rd-" in vid.lower() or "inf-" in vid.lower():
                color = C.GRAY
            else:
                color = C.WHITE

            installed = ""
            if launcher.is_version_installed(vid):
                installed = f"{C.BRIGHT_GREEN}[已下载]{C.RESET}"

            print(f"  {C.DIM}{idx:<4}{C.RESET} {color}{vid:<24}{C.RESET} "
                  f"{color}{vtype:<12}{C.RESET} {color}{rtime:<12}{C.RESET} {installed}")

        # 底部统计
        release_count = sum(1 for v in versions if v.get("type") == "release")
        snapshot_count = sum(1 for v in versions if v.get("type") == "snapshot")
        old_count = sum(1 for v in versions
                       if any(k in v.get("id", "").lower()
                              for k in ("alpha", "beta", "rd-", "inf-")))
        installed_count = sum(1 for v in versions
                             if launcher.is_version_installed(v.get("id", "")))

        print(f"\n{C.DIM}统计: {C.GREEN}正式版 {release_count}{C.DIM} | "
              f"{C.YELLOW}快照 {snapshot_count}{C.DIM} | "
              f"{C.GRAY}古早版 {old_count}{C.DIM} | "
              f"{C.BRIGHT_GREEN}已下载 {installed_count}{C.DIM}{C.RESET}")

        # 提示：如果显示被截断，提示用户
        if final_limit is not None and final_limit < total:
            print(f"{C.DIM}提示: 仅显示前 {final_limit} 个，使用 'lsv -a' 查看全部，"
                  f"或 'lsv -{min(total, final_limit*2)}' 查看更多。{C.RESET}")

    # ---- 文件操作 ----

    def cmd_ls(self, args):
        """ls - 列出文件"""
        target = self.state.current_dir
        if args:
            target = self._resolve_path(args[0])
        if not os.path.isdir(target):
            print(f"{C.RED}不是目录: {target}{C.RESET}")
            return
        items = sorted(os.listdir(target))
        for item in items:
            full = os.path.join(target, item)
            if os.path.isdir(full):
                print(f"{C.BLUE}{item}/{C.RESET}")
            else:
                sz = os.path.getsize(full)
                if item.endswith((".jar", ".zip")):
                    print(f"{C.PINK}{item}{C.RESET} ({sz/1024:.0f}KB)")
                elif item.endswith((".json", ".toml", ".cfg")):
                    print(f"{C.CYAN}{item}{C.RESET} ({sz/1024:.0f}KB)")
                elif item.endswith((".so", ".dll", ".dylib")):
                    print(f"{C.MAGENTA}{item}{C.RESET} ({sz/1024:.0f}KB)")
                else:
                    print(f"  {item} ({sz/1024:.0f}KB)")

    def cmd_cd(self, args):
        """cd - 切换目录"""
        if not args:
            self.state.current_dir = self.state.root_dir
            return
        target = self._resolve_path(args[0])
        if not os.path.isdir(target):
            print(f"{C.RED}不是目录: {args[0]}{C.RESET}")
            return
        self.state.current_dir = os.path.abspath(target)

    def cmd_rm(self, args):
        """rm - 删除"""
        if not args:
            print(f"{C.RED}用法: rm <路径>{C.RESET}")
            return
        target = self._resolve_path(args[0])
        if not os.path.exists(target):
            print(f"{C.RED}未找到: {args[0]}{C.RESET}")
            return
        if os.path.isdir(target):
            shutil.rmtree(target)
            print(f"{C.GREEN}已删除目录: {args[0]}{C.RESET}")
        else:
            os.remove(target)
            print(f"{C.GREEN}已删除文件: {args[0]}{C.RESET}")

    def cmd_mv(self, args):
        """mv - 移动/重命名"""
        if len(args) < 2:
            print(f"{C.RED}用法: mv <源> <目标>{C.RESET}")
            return
        src = self._resolve_path(args[0])
        dst = self._resolve_path(args[1])
        if not os.path.exists(src):
            print(f"{C.RED}未找到: {args[0]}{C.RESET}")
            return
        shutil.move(src, dst)
        print(f"{C.GREEN}已移动 {args[0]} -> {args[1]}{C.RESET}")

    def cmd_cp(self, args):
        """cp - 复制"""
        if len(args) < 2:
            print(f"{C.RED}用法: cp <源> <目标>{C.RESET}")
            return
        src = self._resolve_path(args[0])
        dst = self._resolve_path(args[1])
        if not os.path.exists(src):
            print(f"{C.RED}未找到: {args[0]}{C.RESET}")
            return
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        print(f"{C.GREEN}已复制 {args[0]} -> {args[1]}{C.RESET}")

    def cmd_mkdir(self, args):
        """mkdir - 创建目录"""
        if not args:
            print(f"{C.RED}用法: mkdir <路径>{C.RESET}")
            return
        target = self._resolve_path(args[0])
        os.makedirs(target, exist_ok=True)
        print(f"{C.GREEN}已创建: {args[0]}{C.RESET}")

    def cmd_touch(self, args):
        """touch - 创建空文件"""
        if not args:
            print(f"{C.RED}用法: touch <路径>{C.RESET}")
            return
        target = self._resolve_path(args[0])
        Path(target).touch()
        print(f"{C.GREEN}已创建: {args[0]}{C.RESET}")

    def cmd_pwd(self, args):
        """pwd - 显示当前目录"""
        print(self.state.get_cwd())

    def cmd_cat(self, args):
        """cat - 查看文件内容"""
        if not args:
            print(f"{C.RED}用法: cat <文件>{C.RESET}")
            return
        target = self._resolve_path(args[0])
        if not os.path.isfile(target):
            print(f"{C.RED}不是文件: {args[0]}{C.RESET}")
            return
        with open(target, 'r', errors='replace') as f:
            print(f.read()[:5000])

    def _resolve_path(self, p):
        if p.startswith("/"):
            rel = p[1:].replace("/", os.sep)
            return os.path.join(self.state.root_dir, rel)
        elif p == "..":
            return os.path.dirname(self.state.current_dir)
        elif p.startswith("../"):
            return os.path.abspath(os.path.join(self.state.current_dir, p))
        else:
            return os.path.join(self.state.current_dir, p)

    # ---- 游戏控制 ----

    def cmd_stp(self, args):
        """stp - 启动 Minecraft"""
        if not self.state.logged_in:
            print(f"{C.RED}请先使用 'lgn' 命令登录。{C.RESET}")
            return

        env = self._ensure_env()
        launcher = self._ensure_launcher()

        print(f"当前目录: {self.state.get_cwd()}")
        save_input = input("存档目录（留空使用默认）: ").strip()
        if save_input:
            save_dir = self._resolve_path(save_input)
            os.makedirs(save_dir, exist_ok=True)
        else:
            save_dir = self.state.minecraft_dir

        version = input("版本: ").strip()
        if not version:
            print(f"{C.RED}版本号不能为空。{C.RESET}")
            return

        if not launcher.is_version_installed(version):
            print(f"{C.YELLOW}版本 {version} 未下载，正在下载...{C.RESET}")
            ok, msg = launcher.download_version(version)
            if not ok:
                print(f"{C.RED}{msg}{C.RESET}")
                return

        ok, msg = launcher.launch(version, save_dir=save_dir)
        if ok:
            print(f"{C.BRIGHT_GREEN}{msg}{C.RESET}")
        else:
            print(f"{C.RED}{msg}{C.RESET}")

    def cmd_tif(self, args):
        """tif - 关闭游戏"""
        launcher = self._ensure_launcher()
        if self.state.game_running:
            ok, msg = launcher.stop_game()
            print(f"{C.GREEN}{msg}{C.RESET}")
        else:
            print(f"{C.YELLOW}没有正在运行的游戏。正在退出...{C.RESET}")
            sys.exit(0)

    def cmd_ext(self, args):
        """ext - 退出启动器"""
        launcher = self._ensure_launcher()
        if self.state.game_running:
            confirm = input(f"{C.YELLOW}游戏正在运行，确定停止并退出？(y/N): {C.RESET}").strip().lower()
            if confirm == 'y':
                launcher.stop_game()
        sys.exit(0)

    # ---- 环境管理 ----

    def cmd_env_check(self, args):
        """env_check - 检查环境"""
        env = self._ensure_env()
        mc_ver = args[0] if args else None
        loader = args[1] if len(args) > 1 else None
        report = env.full_check(mc_ver, loader)

        print(f"\n{C.BOLD}环境检查结果:{C.RESET}")
        for k, v in report.items():
            status = v["status"]
            detail = v["detail"]
            if status == "ok":
                sc = C.GREEN
            elif status == "partial":
                sc = C.YELLOW
            else:
                sc = C.RED
            print(f"  {k:<12} {sc}{status.upper():<10}{C.RESET} {detail}")

    def cmd_env_setup(self, args):
        """env_setup - 一键安装环境依赖"""
        env = self._ensure_env()
        mc_ver = args[0] if args else None
        loader = args[1] if len(args) > 1 else None

        needed = env.recommended_java(mc_ver, loader)
        javas = env.list_installed_javas()
        java_ok = any(
            re.search(r'(\d+)', j["version"]) and
            (int(re.search(r'(\d+)', j["version"]).group(1)) >= needed or
             ("1.8" in j["version"] and needed == 8))
            for j in javas
        )
        if not java_ok:
            print(f"{C.YELLOW}正在安装 Java {needed}...{C.RESET}")
            ok, result = env.install_java(needed)
            if ok:
                print(f"{C.GREEN}Java 安装成功: {result}{C.RESET}")
            else:
                print(f"{C.RED}Java 安装失败: {result}{C.RESET}")

        ok, p = env.check_git()
        if not ok:
            print(f"{C.YELLOW}正在安装 Git...{C.RESET}")
            ok, result = env.install_git()
            if ok:
                print(f"{C.GREEN}Git 安装成功: {result}{C.RESET}")
            else:
                print(f"{C.RED}Git 安装失败: {result}{C.RESET}")
        else:
            print(f"{C.GREEN}Git 已就绪: {p}{C.RESET}")

        ok, name, p = env.check_compiler()
        if not ok:
            print(f"{C.YELLOW}正在安装编译器...{C.RESET}")
            ok, result = env.install_compiler()
            if ok:
                print(f"{C.GREEN}编译器安装成功{C.RESET}")
            else:
                print(f"{C.RED}编译器安装失败: {result}{C.RESET}")
        else:
            print(f"{C.GREEN}编译器已就绪: {name} 位于 {p}{C.RESET}")

        missing = env.check_python_deps()
        if missing:
            print(f"{C.YELLOW}正在安装 Python 依赖: {missing}{C.RESET}")
            env.install_python_deps()
        else:
            print(f"{C.GREEN}Python 依赖已就绪{C.RESET}")

    def cmd_java_list(self, args):
        """java_list - 列出已安装的 Java"""
        env = self._ensure_env()
        javas = env.list_installed_javas()
        if not javas:
            print(f"{C.YELLOW}runtime/java/ 下未安装任何 Java 版本{C.RESET}")
            return
        print(f"\n{C.BOLD}已安装的 Java 版本:{C.RESET}")
        for i, j in enumerate(javas):
            current = " (当前使用)" if j["path"] == self.state.java_path else ""
            print(f"  [{i}] {j['name']} - {j['version']}{current}")

    def cmd_java_use(self, args):
        """java_use - 切换 Java"""
        env = self._ensure_env()
        if not args:
            print(f"{C.RED}用法: java_use <索引|路径|版本号>{C.RESET}")
            return
        javas = env.list_installed_javas()
        target = args[0]

        try:
            idx = int(target)
            if 0 <= idx < len(javas):
                self.state.java_path = javas[idx]["path"]
                print(f"{C.GREEN}已切换: {javas[idx]['version']}{C.RESET}")
                return
        except ValueError:
            pass

        for j in javas:
            if target in j["version"]:
                self.state.java_path = j["path"]
                print(f"{C.GREEN}已切换: {j['version']}{C.RESET}")
                return

        if os.path.isfile(target):
            self.state.java_path = target
            print(f"{C.GREEN}已切换: {target}{C.RESET}")
            return

        print(f"{C.RED}未找到 Java: {target}{C.RESET}")

    # ---- 模组管理 ----

    def cmd_insmod(self, args):
        """insmod - 安装模组"""
        if len(args) < 2:
            print(f"{C.RED}用法: insmod <存档目录> <模组文件>{C.RESET}")
            return
        save_dir = self._resolve_path(args[0])
        mod_file = self._resolve_path(args[1])

        if not os.path.isdir(save_dir):
            print(f"{C.RED}存档目录不存在: {args[0]}{C.RESET}")
            return
        if not os.path.isfile(mod_file) or not mod_file.endswith(".jar"):
            print(f"{C.RED}模组文件不存在或不是 .jar: {args[1]}{C.RESET}")
            return

        mods_dir = os.path.join(save_dir, "mods")
        os.makedirs(mods_dir, exist_ok=True)
        dest = os.path.join(mods_dir, os.path.basename(mod_file))
        shutil.copy2(mod_file, dest)

        mods = ModMetadata.parse_jar(dest)
        if mods:
            for m in mods:
                print(f"{C.GREEN}已安装: {m['name']} v{m['version']} ({m['type']}){C.RESET}")
        else:
            print(f"{C.GREEN}已安装: {os.path.basename(dest)}{C.RESET}")

    def cmd_rmmod(self, args):
        """rmmod - 删除模组"""
        if len(args) < 2:
            print(f"{C.RED}用法: rmmod <存档目录> <模组名>{C.RESET}")
            return
        save_dir = self._resolve_path(args[0])
        mod_name = args[1]
        mods_dir = os.path.join(save_dir, "mods")
        if not os.path.isdir(mods_dir):
            print(f"{C.RED}{args[0]} 中没有 mods 目录{C.RESET}")
            return
        for f in os.listdir(mods_dir):
            if mod_name.lower() in f.lower() and f.endswith(".jar"):
                os.remove(os.path.join(mods_dir, f))
                print(f"{C.GREEN}已删除模组: {f}{C.RESET}")
                return
        print(f"{C.RED}未找到模组: {mod_name}{C.RESET}")

    def cmd_lsmod(self, args):
        """lsmod - 列出模组"""
        target = self._resolve_path(args[0]) if args else self.state.current_dir
        mods_dir = os.path.join(target, "mods") if os.path.isdir(os.path.join(target, "mods")) else target
        if not os.path.isdir(mods_dir):
            print(f"{C.RED}没有 mods 目录: {mods_dir}{C.RESET}")
            return
        print(f"\n{C.BOLD}{mods_dir} 中的模组:{C.RESET}")
        for f in sorted(os.listdir(mods_dir)):
            if f.endswith(".jar"):
                fpath = os.path.join(mods_dir, f)
                sz = os.path.getsize(fpath) / 1024
                mods = ModMetadata.parse_jar(fpath)
                if mods and mods[0].get("name"):
                    m = mods[0]
                    print(f"  {C.PINK}{m['name']}{C.RESET} v{C.CYAN}{m['version']}{C.RESET} [{m['type']}] ({sz:.0f}KB)")
                else:
                    print(f"  {f} ({sz:.0f}KB)")

    def cmd_modinfo(self, args):
        """modinfo - 模组详情"""
        if not args:
            print(f"{C.RED}用法: modinfo <模组文件>{C.RESET}")
            return
        mod_file = self._resolve_path(args[0])
        mods = ModMetadata.parse_jar(mod_file)
        if not mods:
            print(f"{C.RED}未找到模组元数据: {args[0]}{C.RESET}")
            return
        for m in mods:
            print(f"\n{C.BOLD}{m['name']}{C.RESET}")
            print(f"  ID: {m['id']}")
            print(f"  版本: {m['version']}")
            print(f"  类型: {m['type']}")
            if m.get('depends'):
                print(f"  依赖: {m['depends']}")
            if m.get('conflicts'):
                print(f"  冲突: {m['conflicts']}")

    def cmd_modpack_install(self, args):
        """modpack_install - 导入整合包"""
        if not args:
            print(f"{C.RED}用法: modpack_install <文件> [实例名]{C.RESET}")
            return
        path = self._resolve_path(args[0])
        name = args[1] if len(args) > 1 else None
        ok, msg = ModpackManager.import_modpack(path, self.state, name)
        if ok:
            print(f"{C.GREEN}{msg}{C.RESET}")
        else:
            print(f"{C.RED}{msg}{C.RESET}")

    def cmd_modpack_export(self, args):
        """modpack_export - 导出整合包"""
        if not args:
            print(f"{C.RED}用法: modpack_export <实例目录>{C.RESET}")
            return
        instance = self._resolve_path(args[0])
        ok, result = ModpackManager.export_modrinth(instance, self.state)
        if ok:
            print(f"{C.GREEN}已导出到: {result}{C.RESET}")
        else:
            print(f"{C.RED}{result}{C.RESET}")

    def cmd_modpack_redownload(self, args):
        """
        modpack_redownload - 重新下载整合包中失败的模组
        用法: modpack_redownload <实例目录>
        """
        if not args:
            print(f"{C.RED}用法: modpack_redownload <实例目录>{C.RESET}")
            return
        instance = self._resolve_path(args[0])
        meta_path = os.path.join(instance, ".starter_meta.json")
        if not os.path.exists(meta_path):
            print(f"{C.RED}该目录没有整合包元数据，无法重新下载{C.RESET}")
            return
        with open(meta_path, 'r') as f:
            metadata = json.load(f)
        if metadata.get("type") != "curseforge":
            print(f"{C.RED}仅支持 CurseForge 整合包的重新下载{C.RESET}")
            return
        files = metadata.get("files", [])
        logger.info(f"重新下载 {len(files)} 个模组文件...")
        api_key = os.environ.get("CURSEFORGE_API_KEY", "")
        success, failed = CurseForgeDownloader.download_mods(
            metadata, instance, api_key=api_key
        )
        total = len(files)
        print(f"{C.GREEN}下载完成: {success}/{total}{C.RESET}")
        if failed:
            print(f"{C.YELLOW}仍有 {len(failed)} 个失败{C.RESET}")
            for f in failed[:3]:
                print(f"  projectID={f['projectID']}, fileID={f['fileID']}")

    # ---- 加载器安装（真正实现） ----

    def cmd_loader_install(self, args):
        """
        loader_install - 真正安装模组加载器。
        用法: loader_install <加载器> <MC版本> [加载器版本] [游戏目录]
        示例:
          loader_install fabric 1.20.1
          loader_install forge 1.20.1 1.20.1-47.2.0
          loader_install quilt 1.20.1 --dir /path/to/game
        """
        if len(args) < 2:
            print(f"{C.RED}用法: loader_install <加载器> <MC版本> [加载器版本] [游戏目录]{C.RESET}")
            print(f"  可选加载器: fabric, forge, quilt, neoforge, liteloader, optifine")
            print(f"  提示: 使用 'loader_list <MC版本>' 查看可用加载器版本")
            return

        loader = args[0].lower()
        mc_ver = args[1]

        # 解析可选参数：加载器版本和游戏目录
        loader_version = None
        game_dir = self.state.minecraft_dir
        for arg in args[2:]:
            if arg == "--dir" or arg.startswith("--dir="):
                continue
            elif arg.startswith("--"):
                continue  # 忽略其他未知参数
            elif os.path.isdir(self._resolve_path(arg)) or arg.startswith("/"):
                game_dir = self._resolve_path(arg)
            else:
                # 假设是版本号
                loader_version = arg

        # 处理 --dir xxx 形式
        if "--dir" in args:
            idx = args.index("--dir")
            if idx + 1 < len(args):
                game_dir = self._resolve_path(args[idx + 1])

        game_dir = self._resolve_path(game_dir) if not os.path.isabs(game_dir) else game_dir

        # 确保 Java 就绪
        env = self._ensure_env()
        needed = env.recommended_java(mc_ver, loader)
        java_path = env.find_java(mc_ver, loader)

        if java_path == "java":
            print(f"{C.YELLOW}未找到合适的 Java，正在安装 Java {needed}...{C.RESET}")
            ok, result = env.install_java(needed)
            if ok:
                java_path = result
                print(f"{C.GREEN}Java 安装成功: {result}{C.RESET}")
            else:
                print(f"{C.RED}Java 安装失败: {result}{C.RESET}")
                print(f"{C.YELLOW}尝试使用系统默认 Java 继续...{C.RESET}")
                java_path = "java"
        else:
            print(f"{C.GREEN}使用 Java: {java_path}{C.RESET}")

        # 确保 MC 版本已下载（加载器需要客户端 jar）
        launcher = self._ensure_launcher()
        if not launcher.is_version_installed(mc_ver):
            print(f"{C.YELLOW}MC {mc_ver} 未安装，正在下载...{C.RESET}")
            ok, msg = launcher.download_version(mc_ver)
            if not ok:
                print(f"{C.RED}MC 下载失败: {msg}{C.RESET}")
                return

        # 执行加载器安装
        print(f"\n{C.BOLD}开始安装 {loader} (MC {mc_ver})...{C.RESET}")
        if loader_version:
            print(f"  指定版本: {loader_version}")
        ok, msg = LoaderInstaller.install(loader, java_path, mc_ver, game_dir, loader_version)

        if ok:
            print(f"\n{C.BRIGHT_GREEN}{msg}{C.RESET}")
            print(f"{C.GREEN}加载器安装完成！可以使用 'stp' 启动游戏了。{C.RESET}")
        else:
            print(f"\n{C.RED}加载器安装失败:{C.RESET}")
            print(f"{C.RED}{msg}{C.RESET}")

            # 显示手动安装指引作为后备方案
            print(f"\n{C.YELLOW}--- 手动安装指引 ---{C.RESET}")
            if loader == "fabric":
                print(f"  1. 下载: https://fabricmc.net/use/")
                print(f"  2. 运行: java -jar fabric-installer.jar client -dir <游戏目录> -mcversion {mc_ver}")
            elif loader == "forge":
                print(f"  1. 下载: https://files.minecraftforge.net/")
                print(f"  2. 运行: java -jar forge-{mc_ver}-installer.jar --installClient")
            elif loader == "quilt":
                print(f"  1. 下载: https://quiltmc.org/en/install/")
                print(f"  2. 运行: java -jar quilt-installer.jar install client {mc_ver}")
            elif loader == "neoforge":
                print(f"  1. 下载: https://neoforged.net/")
                print(f"  2. 运行: java -jar neoforge-{mc_ver}-installer.jar --installClient")
            elif loader == "optifine":
                print(f"  1. 下载: https://optifine.net/downloads")
                print(f"  2. 运行: java -jar OptiFine_{mc_ver}.jar")
            elif loader == "liteloader":
                print(f"  1. 下载: http://www.liteloader.com/download/")
                print(f"  2. 按照安装器指引操作")

    def cmd_loader_list(self, args):
        """
        loader_list - 列出指定 MC 版本可用的加载器版本。
        用法: loader_list <MC版本> [加载器名称]
        示例:
          loader_list 1.20.1          → 列出所有加载器
          loader_list 1.20.1 fabric   → 只列 Fabric
          loader_list 1.20.1 --force  → 强制刷新缓存
        """
        if not args:
            print(f"{C.RED}用法: loader_list <MC版本> [加载器名称] [--force]{C.RESET}")
            return

        mc_ver = args[0]
        specific = None
        force = "--force" in args or "-f" in args

        for a in args[1:]:
            if not a.startswith("-"):
                specific = a.lower()

        resolver = LoaderVersionResolver()
        if force:
            resolver.clear_cache()
            print(f"{C.GRAY}(已清除缓存，强制刷新){C.RESET}")

        print(f"\n{C.BOLD}{C.BRIGHT_BLUE}查询 MC {mc_ver} 可用加载器版本...{C.RESET}")

        # Fabric
        if not specific or specific == "fabric":
            try:
                info = resolver.get_fabric_versions(mc_ver)
                print(f"\n  {C.BOLD}{C.CYAN}Fabric{C.RESET}")
                if info.get("latest_loader"):
                    print(f"    最新加载器: {C.GREEN}{info['latest_loader']}{C.RESET}")
                if info.get("latest_installer"):
                    print(f"    最新安装器: {C.YELLOW}{info['latest_installer']}{C.RESET}")
                vers = info.get("loader_versions", [])
                if vers:
                    print(f"    可用加载器版本 ({len(vers)}):")
                    for v in vers[:10]:
                        marker = f" {C.GREEN}← 最新{C.RESET}" if v == info["latest_loader"] else ""
                        print(f"      {v}{marker}")
                    if len(vers) > 10:
                        print(f"      ... 还有 {len(vers)-10} 个更早版本")
            except Exception as e:
                print(f"\n  {C.BOLD}{C.CYAN}Fabric{C.RESET}: {C.RED}查询失败: {e}{C.RESET}")

        # Forge
        if not specific or specific == "forge":
            try:
                info = resolver.get_forge_versions(mc_ver)
                print(f"\n  {C.BOLD}{C.ORANGE}Forge{C.RESET}")
                if info.get("recommended"):
                    print(f"    推荐版本: {C.GREEN}{info['recommended']}{C.RESET}")
                if info.get("latest") and info["latest"] != info.get("recommended"):
                    print(f"    最新版本: {C.YELLOW}{info['latest']}{C.RESET}")
                vers = info.get("versions", [])
                if vers:
                    print(f"    可用版本 ({len(vers)}):")
                    for v in vers[-10:]:
                        marker = f" {C.GREEN}← 最新{C.RESET}" if v == info.get("latest") else ""
                        print(f"      {v}{marker}")
                    if len(vers) > 10:
                        print(f"      ... 还有 {len(vers)-10} 个更早版本")
            except Exception as e:
                print(f"\n  {C.BOLD}{C.ORANGE}Forge{C.RESET}: {C.RED}查询失败: {e}{C.RESET}")

        # Quilt
        if not specific or specific == "quilt":
            try:
                info = resolver.get_quilt_versions(mc_ver)
                print(f"\n  {C.BOLD}{C.PINK}Quilt{C.RESET}")
                if info.get("latest_loader"):
                    print(f"    最新加载器: {C.GREEN}{info['latest_loader']}{C.RESET}")
                if info.get("latest_installer"):
                    print(f"    最新安装器: {C.YELLOW}{info['latest_installer']}{C.RESET}")
                vers = info.get("loader_versions", [])
                if vers:
                    print(f"    可用加载器版本 ({len(vers)}):")
                    for v in vers[:10]:
                        marker = f" {C.GREEN}← 最新{C.RESET}" if v == info["latest_loader"] else ""
                        print(f"      {v}{marker}")
                    if len(vers) > 10:
                        print(f"      ... 还有 {len(vers)-10} 个更早版本")
            except Exception as e:
                print(f"\n  {C.BOLD}{C.PINK}Quilt{C.RESET}: {C.RED}查询失败: {e}{C.RESET}")

        # NeoForge
        if not specific or specific == "neoforge":
            try:
                info = resolver.get_neoforge_versions(mc_ver)
                print(f"\n  {C.BOLD}{C.TEAL}NeoForge{C.RESET}")
                if info.get("recommended"):
                    print(f"    推荐版本: {C.GREEN}{info['recommended']}{C.RESET}")
                if info.get("latest") and info["latest"] != info.get("recommended"):
                    print(f"    最新版本: {C.YELLOW}{info['latest']}{C.RESET}")
                vers = info.get("versions", [])
                if vers:
                    print(f"    可用版本 ({len(vers)}):")
                    for v in vers[-10:]:
                        marker = f" {C.GREEN}← 最新{C.RESET}" if v == info.get("latest") else ""
                        print(f"      {v}{marker}")
                    if len(vers) > 10:
                        print(f"      ... 还有 {len(vers)-10} 个更早版本")
            except Exception as e:
                print(f"\n  {C.BOLD}{C.TEAL}NeoForge{C.RESET}: {C.RED}查询失败: {e}{C.RESET}")

        # OptiFine
        if not specific or specific in ("optifine", "optifine"):
            try:
                info = resolver.get_optifine_versions(mc_ver)
                print(f"\n  {C.BOLD}{C.BLUE}OptiFine{C.RESET}")
                vers = info.get("versions", [])
                if vers:
                    print(f"    可用版本 ({len(vers)}):")
                    for v in vers[:10]:
                        marker = f" {C.GREEN}← 最新{C.RESET}" if v == info.get("latest") else ""
                        print(f"      {v}{marker}")
                    if len(vers) > 10:
                        print(f"      ... 还有 {len(vers)-10} 个更早版本")
                else:
                    print(f"    {C.GRAY}未找到可用版本{C.RESET}")
            except Exception as e:
                print(f"\n  {C.BOLD}{C.BLUE}OptiFine{C.RESET}: {C.RED}查询失败: {e}{C.RESET}")

        # LiteLoader
        if not specific or specific == "liteloader":
            try:
                info = resolver.get_liteloader_versions(mc_ver)
                print(f"\n  {C.BOLD}{C.GRAY}LiteLoader{C.RESET}")
                snaps = info.get("snapshots", [])
                if snaps:
                    print(f"    可用快照 ({len(snaps)}):")
                    for s in snaps[-5:]:
                        marker = f" {C.GREEN}← 最新{C.RESET}" if s["snapshot"] == info.get("latest") else ""
                        print(f"      {s['snapshot']} ({s.get('type','')}){marker}")
                else:
                    print(f"    {C.GRAY}未找到可用快照{C.RESET}")
            except Exception as e:
                print(f"\n  {C.BOLD}{C.GRAY}LiteLoader{C.RESET}: {C.RED}查询失败: {e}{C.RESET}")

        print(f"\n{C.GRAY}提示: 版本信息缓存 1 小时，使用 --force 强制刷新{C.RESET}")
        print(f"{C.GRAY}安装: loader_install <加载器> {mc_ver} [具体版本]{C.RESET}")

    # ---- 实例管理 ----

    def cmd_instance_create(self, args):
        """instance_create - 创建实例"""
        if not args:
            print(f"{C.RED}用法: instance_create <名称> [MC版本]{C.RESET}")
            return
        name = args[0]
        inst_dir = os.path.join(self.state.instances_dir, name)
        if os.path.exists(inst_dir):
            print(f"{C.RED}实例已存在: {name}{C.RESET}")
            return
        os.makedirs(inst_dir, exist_ok=True)
        os.makedirs(os.path.join(inst_dir, "mods"), exist_ok=True)
        os.makedirs(os.path.join(inst_dir, "config"), exist_ok=True)
        config = {
            "name": name,
            "mc_version": args[1] if len(args) > 1 else "",
            "jvm_args": "-Xmx2G -Xms1G",
            "memory": {"min": 1024, "max": 2048},
            "window": {"width": 854, "height": 480},
            "java_version": "",
        }
        with open(os.path.join(inst_dir, "instance.json"), 'w') as f:
            json.dump(config, f, indent=2)
        print(f"{C.GREEN}已创建实例: {name}{C.RESET}")

    def cmd_instance_list(self, args):
        """instance_list - 列出实例"""
        if not os.path.isdir(self.state.instances_dir):
            print(f"{C.YELLOW}尚无实例目录{C.RESET}")
            return
        items = os.listdir(self.state.instances_dir)
        if not items:
            print(f"{C.YELLOW}尚未创建任何实例{C.RESET}")
            return
        print(f"\n{C.BOLD}游戏实例:{C.RESET}")
        for item in sorted(items):
            full = os.path.join(self.state.instances_dir, item)
            if os.path.isdir(full):
                cfg_path = os.path.join(full, "instance.json")
                mc_ver = ""
                if os.path.exists(cfg_path):
                    with open(cfg_path, 'r') as f:
                        cfg = json.load(f)
                    mc_ver = cfg.get("mc_version", "")
                print(f"  {C.BLUE}{item}/{C.RESET} (MC: {mc_ver or '未设置'})")

    def cmd_instance_delete(self, args):
        """instance_delete - 删除实例"""
        if not args:
            print(f"{C.RED}用法: instance_delete <名称>{C.RESET}")
            return
        inst_dir = os.path.join(self.state.instances_dir, args[0])
        if not os.path.isdir(inst_dir):
            print(f"{C.RED}实例不存在: {args[0]}{C.RESET}")
            return
        shutil.rmtree(inst_dir)
        print(f"{C.GREEN}已删除实例: {args[0]}{C.RESET}")

    def cmd_instance_config(self, args):
        """instance_config - 查看/编辑实例配置"""
        if not args:
            print(f"{C.RED}用法: instance_config <名称> [键=值 ...]{C.RESET}")
            print(f"  可配置项: mc_version, jvm_args, memory_min, memory_max, window_width, window_height")
            return
        inst_dir = os.path.join(self.state.instances_dir, args[0])
        cfg_path = os.path.join(inst_dir, "instance.json")
        if not os.path.exists(cfg_path):
            print(f"{C.RED}实例配置不存在: {args[0]}{C.RESET}")
            return
        with open(cfg_path, 'r') as f:
            cfg = json.load(f)
        if len(args) == 1:
            print(f"\n{C.BOLD}{args[0]} 的配置:{C.RESET}")
            print(json.dumps(cfg, indent=2, ensure_ascii=False))
            return
        for kv in args[1:]:
            if "=" not in kv:
                continue
            k, v = kv.split("=", 1)
            k = k.strip(); v = v.strip()
            if k == "mc_version": cfg["mc_version"] = v
            elif k == "jvm_args": cfg["jvm_args"] = v
            elif k == "memory_min": cfg.setdefault("memory", {})["min"] = int(v)
            elif k == "memory_max": cfg.setdefault("memory", {})["max"] = int(v)
            elif k == "window_width": cfg.setdefault("window", {})["width"] = int(v)
            elif k == "window_height": cfg.setdefault("window", {})["height"] = int(v)
        with open(cfg_path, 'w') as f:
            json.dump(cfg, f, indent=2)
        print(f"{C.GREEN}{args[0]} 的配置已更新{C.RESET}")

    # ---- 备份 ----

    def cmd_nrt(self, args):
        """nrt - 备份目录为 tar.gz"""
        if not args:
            print(f"{C.RED}用法: nrt <目录>{C.RESET}")
            return
        src = self._resolve_path(args[0])
        if not os.path.isdir(src):
            print(f"{C.RED}目录不存在: {args[0]}{C.RESET}")
            return
        name = os.path.basename(src.rstrip(os.sep))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = os.path.join(self.state.root_dir, f"{name}_backup_{timestamp}.tar.gz")
        logger.info(f"正在创建备份: {output}")
        with tarfile.open(output, "w:gz") as tar:
            tar.add(src, arcname=name)
        sz = os.path.getsize(output) / 1024 / 1024
        print(f"{C.GREEN}备份完成: {output} ({sz:.1f}MB){C.RESET}")

    # ---- 帮助 ----

    def cmd_help(self, args):
        """help - 显示帮助"""
        print(f"\n{C.BOLD}{C.BRIGHT_BLUE}Minecraft CLI 启动器 - 命令参考{C.RESET}\n")
        cmds = [
            ("认证", [
                ("lgn", "登录（先设本地密码，再选正版/离线）"),
                ("lgt", "注销当前登录"),
                ("stlgn", "保存登录信息（下次自动登录需验证密码）"),
                ("csli", "取消自动登录"),
                ("ch_pw [用户]", "修改密码（非空=改密码，空=关闭密码）"),
            ]),
            ("游戏控制", [
                ("stp", "启动 Minecraft（提示输入存档目录和版本）"),
                ("tif", "关闭正在运行的 Minecraft"),
                ("ext", "退出启动器（有游戏时先确认）"),
            ]),
            ("版本管理", [
                ("lsv [-f] [-a] [-N]", "列出可用版本（绿=正式版, 黄=快照, 灰=古早版, -N=最近N个, -a=全部, -f=强制刷新）"),
            ]),
            ("环境依赖", [
                ("env_check [MC版本] [加载器]", "检查 Java/Git/编译器/Python 依赖"),
                ("env_setup [MC版本] [加载器]", "自动安装所有缺失的依赖"),
                ("java_list", "列出已安装的 Java 版本"),
                ("java_use <索引|路径|版本>", "切换当前使用的 Java"),
            ]),
            ("模组管理", [
                ("insmod <目录> <文件>", "安装模组到指定存档/实例"),
                ("rmmod <目录> <名称>", "从存档/实例中删除模组"),
                ("lsmod [目录]", "列出已安装模组（显示元数据）"),
                ("modinfo <文件>", "显示模组详细信息"),
            ]),
            ("加载器", [
                ("loader_list <MC版本> [名称]", "查询可用的加载器版本（实时获取）"),
                ("loader_install <加载器> <MC版本> [版本] [目录]", "安装 Forge/Fabric/Quilt/NeoForge/OptiFine/LiteLoader"),
            ]),
            ("整合包", [
                ("modpack_install <文件> [名称]", "导入 CurseForge/Modrinth/MultiMC 整合包（自动下载模组）"),
                ("modpack_export <目录>", "将实例导出为 Modrinth .mrpack 格式"),
                ("modpack_redownload <目录>", "重新下载失败的模组文件"),
            ]),
            ("实例管理", [
                ("instance_create <名称> [MC版本]", "创建独立的游戏实例"),
                ("instance_list", "列出所有实例"),
                ("instance_delete <名称>", "删除实例"),
                ("instance_config <名称> [k=v]", "查看/编辑实例配置"),
            ]),
            ("文件操作", [
                ("ls [路径]", "列出文件（按类型着色显示）"),
                ("cd <路径>", "切换目录（支持 .. 和 / 开头路径）"),
                ("pwd", "显示当前目录"),
                ("rm <路径>", "删除文件或目录"),
                ("mv <源> <目标>", "移动/重命名"),
                ("cp <源> <目标>", "复制文件或目录"),
                ("mkdir <路径>", "创建目录"),
                ("touch <路径>", "创建空文件"),
                ("cat <文件>", "查看文件内容"),
            ]),
            ("其他", [
                ("nrt <目录>", "将目录备份为 .tar.gz 压缩包"),
                ("clear", "清屏"),
                ("help", "显示此帮助信息"),
            ]),
        ]
        for section, items in cmds:
            print(f"  {C.BOLD}{C.YELLOW}{section}{C.RESET}")
            for cmd, desc in items:
                print(f"    {C.GREEN}{cmd:<28}{C.RESET} {desc}")
            print()

    def cmd_clear(self, args):
        """clear - 清屏"""
        os.system('cls' if os.name == 'nt' else 'clear')

    # ---- 命令分发 ----

    def dispatch(self, line):
        """解析用户输入并分发到对应处理函数"""
        line = line.strip()
        if not line:
            return True
        parts = line.split()
        cmd = parts[0].lower()
        args = parts[1:]

        handlers = {
            "lgn": self.cmd_lgn, "lgt": self.cmd_lgt,
            "stlgn": self.cmd_stlgn, "csli": self.cmd_csli,
            "ch_pw": self.cmd_ch_pw,
            "stp": self.cmd_stp, "tif": self.cmd_tif, "ext": self.cmd_ext,
            "lsv": self.cmd_lsv,
            "ls": self.cmd_ls, "cd": self.cmd_cd, "rm": self.cmd_rm,
            "mv": self.cmd_mv, "cp": self.cmd_cp,
            "mkdir": self.cmd_mkdir, "touch": self.cmd_touch,
            "pwd": self.cmd_pwd, "cat": self.cmd_cat,
            "env_check": self.cmd_env_check, "env_setup": self.cmd_env_setup,
            "java_list": self.cmd_java_list, "java_use": self.cmd_java_use,
            "insmod": self.cmd_insmod, "rmmod": self.cmd_rmmod,
            "lsmod": self.cmd_lsmod, "modinfo": self.cmd_modinfo,
            "modpack_install": self.cmd_modpack_install,
            "modpack_export": self.cmd_modpack_export,
            "modpack_redownload": self.cmd_modpack_redownload,
            "loader_install": self.cmd_loader_install,
            "loader_list": self.cmd_loader_list,
            "instance_create": self.cmd_instance_create,
            "instance_list": self.cmd_instance_list,
            "instance_delete": self.cmd_instance_delete,
            "instance_config": self.cmd_instance_config,
            "nrt": self.cmd_nrt,
            "help": self.cmd_help, "clear": self.cmd_clear,
        }

        if cmd in handlers:
            try:
                handlers[cmd](args)
            except KeyboardInterrupt:
                print(f"\n{C.YELLOW}操作已中断。{C.RESET}")
            except Exception as e:
                logger.error(f"命令 '{cmd}' 执行失败: {e}")
            return True
        elif cmd in ("quit", "exit"):
            return False
        else:
            print(f"{C.RED}未知命令: {cmd}{C.RESET}  输入 'help' 查看命令列表。")
            return True


# ============================================================
# 主程序入口
# ============================================================
def print_banner(state):
    """打印启动横幅"""
    java_status = f"{C.GREEN}就绪{C.RESET}" if state.java_path != "java" else f"{C.RED}缺失{C.RESET}"
    # 显示账号密码保护状态
    pw_info = ""
    if state.username and AccountStore.account_exists(state.username, state.accounts_dir):
        path = AccountStore._account_path(state.username, state.accounts_dir)
        try:
            with open(path, 'r') as f:
                d = json.load(f)
            if d.get("has_password"):
                pw_info = f" {C.YELLOW}[密码保护]{C.RESET}"
            else:
                pw_info = f" {C.GRAY}[无密码]{C.RESET}"
        except Exception:
            pass
    print(f"""{C.BRIGHT_BLUE}{C.BOLD}Chen Minecraft Launcher 7 (CML7) ©2026 童顺\ncn19491001cn@yeah.net admin@amateurradio.org.cn\n感谢 BMCLAPI 为本启动器提供 CurseForge 的镜像源{C.RESET}
  Java: {java_status}  CWD: {C.CYAN}{state.get_cwd()}{C.RESET}{pw_info}
""")


def main():
    """主函数"""
    state = State()
    cli = CLI(state)
    cli._load_auth()
    print_banner(state)

    while True:
        try:
            prompt = f"{C.GREEN}{state.username or '游客'}{C.RESET}:{C.BLUE}{state.get_cwd()}{C.RESET}$ "
            line = input(prompt)
            if not cli.dispatch(line):
                break
        except KeyboardInterrupt:
            print(f"\n{C.YELLOW}请使用 'ext' 命令正常退出。{C.RESET}")
        except EOFError:
            print()
            break

    if state.game_running and state.minecraft_process:
        state.minecraft_process.terminate()
    print(f"{C.GREEN}再见！{C.RESET}")


if __name__ == "__main__":
    print("警告：代码第 161 行有重要信息，使用本工具即表示你已阅读并理解此警告。将其阅读并理解后可将代码第4587行注释或删除，以消除此警告")
    main()
