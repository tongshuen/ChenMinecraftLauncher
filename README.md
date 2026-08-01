# ChenMinecraftLauncher
一个新兴的Minecraft启动器
# Chen Minecraft Launcher 8 (CML8)

©2026 童顺  
cn19491001cn@yeah.net | admin@amateurradio.org.cn

CML8 是一个功能完备的 Minecraft 启动器，采用 Python 编写，支持正版 Microsoft 登录、离线模式、多版本管理、模组加载器自动安装、整合包导入导出以及丰富的命令行交互。

---

## ✨ 主要特性

- **双模式认证**  
  - Microsoft OAuth2 设备代码流（正版登录）  
  - 离线模式（生成离线 UUID）  
  - 本地密码保护（PBKDF2 加密存储，可单独为每个账号设置密码）

- **游戏版本管理**  
  - 从 Mojang 官方清单获取所有正式版、快照、古早版  
  - 自动下载客户端、资源索引和库文件  
  - 支持版本继承（`inheritsFrom`）和完整的规则引擎（`rules` / `features` / `os` / `arch`）

- **模组加载器自动安装**  
  - 支持 **Fabric**、**Forge**、**Quilt**、**NeoForge**、**OptiFine**、**LiteLoader**  
  - 实时从官方源查询可用版本列表（含缓存）  
  - 自动下载安装器并执行，无需手动操作

- **整合包支持**  
  - 导入 **CurseForge**（`.zip`，自动下载所有模组文件，支持 BMCLAPI 镜像）  
  - 导入 **Modrinth**（`.mrpack`）  
  - 导入 **MultiMC**（`.zip`）  
  - 导出为 Modrinth 格式（`.mrpack`）  
  - 支持重新下载失败的模组文件

- **模组元数据解析**  
  - 从 `.jar` 中提取 Fabric / Quilt / Forge / LiteLoader 的元数据（名称、ID、版本、依赖、冲突）  
  - 依赖冲突检测和循环依赖报告

- **环境自检与自动配置**  
  - 自动检测并安装 **Java**（从 Adoptium Temurin 下载）  
  - 安装 **Git**（Windows 下提供 MinGit）  
  - 安装 **C/C++ 编译器**（Linux 下通过包管理器）

---
#相对于上一个版本，更新了什么
##安全更新
限制了部分敏感文件的权限。由于权限模型差异，此更新对 Unix 系系统有效，对 DOS 系系统基本无效。
---
# Chen Minecraft Launcher 7 (CML7)

©2026 童顺  
cn19491001cn@yeah.net | admin@amateurradio.org.cn

CML7 是一个功能完备的 Minecraft 启动器，采用 Python 编写，支持正版 Microsoft 登录、离线模式、多版本管理、模组加载器自动安装、整合包导入导出以及丰富的命令行交互。

---

## ✨ 主要特性

- **双模式认证**  
  - Microsoft OAuth2 设备代码流（正版登录）  
  - 离线模式（生成离线 UUID）  
  - 本地密码保护（PBKDF2 加密存储，可单独为每个账号设置密码）

- **游戏版本管理**  
  - 从 Mojang 官方清单获取所有正式版、快照、古早版  
  - 自动下载客户端、资源索引和库文件  
  - 支持版本继承（`inheritsFrom`）和完整的规则引擎（`rules` / `features` / `os` / `arch`）

- **模组加载器自动安装**  
  - 支持 **Fabric**、**Forge**、**Quilt**、**NeoForge**、**OptiFine**、**LiteLoader**  
  - 实时从官方源查询可用版本列表（含缓存）  
  - 自动下载安装器并执行，无需手动操作

- **整合包支持**  
  - 导入 **CurseForge**（`.zip`，自动下载所有模组文件，支持 BMCLAPI 镜像）  
  - 导入 **Modrinth**（`.mrpack`）  
  - 导入 **MultiMC**（`.zip`）  
  - 导出为 Modrinth 格式（`.mrpack`）  
  - 支持重新下载失败的模组文件

- **模组元数据解析**  
  - 从 `.jar` 中提取 Fabric / Quilt / Forge / LiteLoader 的元数据（名称、ID、版本、依赖、冲突）  
  - 依赖冲突检测和循环依赖报告

- **环境自检与自动配置**  
  - 自动检测并安装 **Java**（从 Adoptium Temurin 下载）  
  - 安装 **Git**（Windows 下提供 MinGit）  
  - 安装 **C/C++ 编译器**（Linux 下通过包管理器）  
  - 安装 Python 依赖（如 `requests`, `toml`, `zstandard`）

- **游戏实例管理**  
  - 独立的实例目录（每个实例拥有自己的 `mods`、`config`、`saves`）  
  - 可配置内存、JVM 参数、窗口大小

- **多格式备份**  
  - 一键将任意目录打包为 `.tar.gz`

- **美观的命令行界面**  
  - 彩色输出，日志分级着色  
  - 文件列表按类型着色（目录、JAR、JSON、库文件等）  
  - 进度条显示下载和校验过程

---

## 🚀 安装与运行

### 环境要求
- Python 3.8 或更高版本（仅依赖标准库，但推荐安装 `requests`、`toml`、`zstandard` 以增强功能）
- 网络连接（用于下载游戏文件、加载器和 Java）

### 快速开始
1. 下载 `ChenMinecraftLauncher7.py` 到本地目录。
2. 打开终端（Windows 下可使用 PowerShell 或 CMD）。
3. 运行：
   ```bash
   python ChenMinecraftLauncher7.py
   ```

4. 首次启动会自动创建必要的目录结构（.minecraft、runtime、instances 等）。
5. 使用内置命令进行登录、下载和启动。

注意：若需使用正版登录，请先替换代码中的 CLIENT_ID（第 161 行）为您自己在 Azure Portal 注册的应用程序 ID，否则可能违反 Microsoft 政策并导致账号风险。

---

##🔧 配置与目录结构

启动器在运行目录下创建以下文件夹：

```
.
├── .minecraft/          # 默认游戏目录（versions, libraries, assets, saves）
├── runtime/             # 运行时组件
│   ├── java/            # 自动安装的 Java 版本
│   ├── installers/      # 下载的加载器安装器 JAR
│   └── version_cache/   # 加载器版本列表缓存
├── config/              # 启动器配置
│   ├── auth.json        # 保存的登录信息（自动登录）
│   └── accounts/        # 本地账号密码存储（每个账号一个 JSON 文件）
├── instances/           # 独立游戏实例（每个实例一个子目录）
└── versions/            # （.minecraft/versions 的符号链接，实际上在 .minecraft 内）
```

---

##📖 命令参考

CML7 提供丰富的命令行交互，所有命令均在启动器提示符下输入（用户名:当前目录$）。

###认证相关

命令 说明
lgn 登录：输入用户名，设置/验证本地密码，选择 Microsoft 正版或离线模式
lgt 注销当前用户
stlgn 保存登录信息（下次启动自动登录，若账号有密码则需验证）
csli 取消自动登录
ch_pw [用户名] 修改或关闭本地密码（空密码 = 关闭密码保护）

###游戏控制

命令 说明
stp 启动游戏（会提示输入存档目录和版本号）
tif 强制终止正在运行的游戏
ext 退出启动器（若游戏运行中会询问是否停止）

###版本管理

命令 说明
lsv [-f] [-a] [-N] 列出可用版本（-f 强制刷新，-a 显示全部，-N 显示最近 N 个）

###环境管理

命令 说明
env_check [MC版本] [加载器] 检查 Java、Git、编译器、Python 依赖状态
env_setup [MC版本] [加载器] 自动安装缺失的组件
java_list 列出已安装的 Java 版本
java_use <索引\|路径\|版本> 切换当前使用的 Java

###模组管理

命令 说明
insmod <目录> <模组.jar> 安装模组到指定游戏目录或实例
rmmod <目录> <模组名> 从指定目录删除模组（模糊匹配）
lsmod [目录] 列出已安装模组及其元数据
modinfo <模组.jar> 显示模组的详细信息（ID、版本、依赖、冲突）

###加载器安装

命令 说明
loader_list <MC版本> [加载器名] 查询指定 MC 版本可用的加载器版本列表
loader_install <加载器> <MC版本> [版本号] [游戏目录] 安装指定的加载器（支持 fabric/forge/quilt/neoforge/optifine/liteloader）

###整合包操作

命令 说明
modpack_install <文件> [实例名] 导入整合包（自动识别 CurseForge/Modrinth/MultiMC 格式）
modpack_export <实例目录> 将实例导出为 Modrinth 格式（.mrpack）
modpack_redownload <实例目录> 重新下载整合包中之前失败的模组文件

###实例管理

命令 说明
instance_create <名称> [MC版本] 创建新的游戏实例
instance_list 列出所有已创建的实例
instance_delete <名称> 删除指定实例
instance_config <名称> [键=值 ...] 查看或修改实例配置（如 mc_version、memory_min 等）

###文件操作（类似 Shell）

命令 说明
ls [路径] 列出目录内容（按文件类型着色）
cd <路径> 切换当前工作目录（支持 .. 和以 / 开头的绝对路径）
pwd 显示当前工作目录
rm <路径> 删除文件或目录
mv <源> <目标> 移动或重命名
cp <源> <目标> 复制文件或目录
mkdir <路径> 创建目录
touch <路径> 创建空文件
cat <文件> 查看文件内容（最多 5000 字符）

###其他

命令 说明
nrt <目录> 将指定目录打包为 .tar.gz 备份
clear 清屏
help 显示完整命令帮助

---

##📝 使用示例

1. 首次登录并启动游戏

```
$ lgn
name: Steve
这是新账号 'Steve'，是否设置启动器本地密码？
设置密码？(Y/n): y
设置密码: ********
再次输入密码: ********
账号 'Steve' 已创建并设好密码
登录方式: [1] Microsoft 正版  [2] 离线模式  [q] 取消: 2
已登录为 Steve（离线模式）
$ stp
存档目录（留空使用默认）: 
版本: 1.20.1
版本 1.20.1 未下载，正在下载...
[=====] 100.0% (完成)
正在启动 Minecraft 1.20.1（用户: Steve）...
Minecraft 1.20.1 已启动 (PID: 12345)
```

2. 安装 Fabric 并启动

```
$ loader_list 1.20.1 fabric
  Fabric
    最新加载器: 0.15.11
    可用加载器版本 (10):
      0.15.11 ← 最新
      ...
$ loader_install fabric 1.20.1
...
安装成功！
$ stp
版本: fabric-loader-0.15.11-1.20.1   # 输入自动生成的 Fabric 版本 ID
```

3. 导入 CurseForge 整合包

```
$ modpack_install ~/Downloads/MyPack.zip MyPack
检测到 CurseForge 整合包: MC 1.20.1, 加载器: forge-47.2.0
模组文件数: 45
下载中...
模组下载完成: 成功 45/45
已应用 32 个 overrides 文件
CurseForge 整合包导入完成: MC 1.20.1, 加载器: forge-47.2.0, 模组: 45/45
```

---

#⚠️ 重要注意事项

1. 正版登录 Client ID
      代码第 161 行的 CLIENT_ID 是示例测试 ID，不得用于商业或生产环境。
      您必须在 Azure Portal 免费注册自己的应用程序，获取专属 Client ID 并替换，否则可能违反微软政策并导致账号封禁。
      替换后，请同时删除或注释第 4587 行的警告打印语句。
2. 网络依赖
      首次运行需要下载游戏文件、加载器安装器和 Java 运行时，请确保网络畅通。
3. 本地密码
      本地密码仅用于保护启动器本地账号，与 Microsoft 账户密码无关。若忘记密码，可手动删除 config/accounts/用户名.json 文件重置。同理，攻击者也可以删除文件以获得你的账户登录权限。
4. 自动 Java 安装
      自动安装的 Java 存放在 runtime/java/ 下，不会影响系统全局 Java。可通过 java_use 命令切换。
5. 整合包下载
      CurseForge 整合包模组下载优先使用 BMCLAPI 镜像，无需 API Key。若需更稳定，可在环境变量中设置 CURSEFORGE_API_KEY（需在 CurseForge 官网申请）。

---

本项目由童顺（cn19491001cn@yeah.net）开发。
使用本软件即表示您已阅读并理解上述所有警告和条款。
