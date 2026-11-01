# Z MINECRAFT LAUNCHER

基于 **Python + PyQt5** 的第三方 Minecraft 启动器，界面全部使用 Qt 原生控件自绘（无任何 WebView / HTML 嵌入）。

## 功能

- **账号**：微软正版登录（设备码 OAuth 流程）、离线账号并存，支持多账号切换
  - **账号列表**：侧边栏直接列出所有账号，点击即切换，无需重复登录
  - **手动刷新**：一键刷新当前账号的令牌与角色资料（皮肤/披风），解决登录后同步延迟
  - **第三方登录服务器**：支持 Yggdrasil / authlib-injector 规范的服务器（LittleSkin、MCCAG 等），用户名密码登录，启动时自动注入 authlib-injector
- **版本**：拉取 Mojang 版本清单，一键安装原版；支持官方 / BMCLAPI / MCBBS 三种镜像源
- **下载**：实时显示阶段、总下载量、已下载量、速度与百分比；多线程并发（1-32 可调，默认 16）+ 大文件分段并行 + SHA1 校验 + 断点续传
- **容错**：镜像节点不稳定时自动重试并降级到官方源；连续失败会熔断该镜像，全程只提示一次
- **代理**：支持跟随系统 / 不使用 / 自定义代理地址
- **实例**：多实例隔离（独立游戏目录）、一键启动、内存与 JVM 参数自定义
- **模组**：内置 Modrinth 浏览器，可搜索并安装模组 / 资源包 / 光影到指定实例
- **界面**：无边框自绘窗口 + 自定义标题栏，暗色 / 亮色双主题

## 运行

```bash
pip install -r requirements.txt
python main.py
```

需要 Python 3.8+ 与 PyQt5。

## 目录结构

```
main.py            入口（崩溃日志、异常兜底）
app.py             数据中枢：账号、实例、启动流程、主题
core/              核心逻辑（与 UI 完全解耦，可独立测试）
  config.py        配置与镜像源 URL 重写
  http.py          HTTP 层：连接池、重试、镜像降级、熔断、代理
  auth.py          微软设备码登录 / XBL / XSTS 令牌交换 / 令牌刷新 / Yggdrasil 认证
  account.py       账号刷新统一入口、过期判断、显示名
  manifest.py      版本清单
  version.py       版本继承合并、库/资源收集、启动命令拼接
  download.py      并发/分段下载、SHA1 校验、断点续传、进度汇总
  installer.py     版本安装流程
  modrinth.py      Modrinth 搜索与文件解析
  launcher.py      启动游戏进程并回传日志
  java.py          Java 运行时探测
  extract.py       原生库解压
  instances.py     实例增删改查
ui/                界面层（PyQt5 控件 + QSS 样式）
  main_window.py   主窗口与导航
  instances_page.py / version_page.py / mod_page.py / settings_page.py
  login_dialog.py  登录对话框
  account_dialog.py 账号管理（列表/切换/刷新/第三方服务器）
  authlib.py       authlib-injector 下载与注入（第三方登录服务器）
  toast.py         轻提示
  widgets.py       公共组件（标题栏、进度面板）
  worker.py        后台线程与信号桥
  styles.py        双主题 QSS
```

## 数据目录

配置、账号、版本、实例统一存放在：

- Windows：`%APPDATA%\.mclauncherpy`
- Linux / macOS：`~/.mclauncherpy`

## 说明

- 微软登录使用的客户端 ID 来自 Prism Launcher 的公开注册应用，可在「设置」中替换为自己的 Azure 应用 ID。
- 启动前请确保已在「设置」中选择正确的 Java 版本。
- **下载加速**：「设置 → 下载并发数」控制全局同时连接数（1-32，默认 16）；勾选「大文件分段并行下载」后，超过 4MB 的文件会拆成最多 8 段同时下载（单文件实测提速约 1.5 倍）。若下载源不支持 Range 请求会自动退回普通流式下载。
- **镜像容错**：BMCLAPI / MCBBS 会把请求 302 到多个第三方节点，部分节点常年断连。启动器会对瞬时错误（连接重置、SSL 失败、超时）做指数退避重试，仍失败则自动改用官方源；同一镜像连续失败 3 次会触发熔断，后续任务直接走官方源，不再逐个文件去撞坏节点。下载失败时会列出具体失败文件与中文原因，而不是抛原始异常。
- **代理**：「设置 → 网络代理」可选跟随系统（默认）、不使用代理或填写自定义地址（如 `http://127.0.0.1:7890`）。更换代理后所有连接池会自动重建。
- **第三方登录服务器**：在「账号管理 → 第三方服务器」标签页填入服务器地址（如 `https://littleskin.cn/api/yggdrasil`）与用户名密码登录。首次启动第三方账号时会自动下载 authlib-injector（约 340KB，存到数据目录），并以 `-javaagent` 方式注入。也可在「设置 → 第三方登录服务器」预填地址，登录时会自动记入下拉列表。

## License

MIT
