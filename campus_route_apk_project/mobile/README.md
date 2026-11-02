# 手机版（安卓）

三条路线，按需要选：

| 方案 | 是否需要构建 | 说明 |
|---|---|---|
| **Termux + 手机浏览器**（已可直接用） | 否 | 手机装 Termux → `bash android/install_termux.sh` → 浏览器打开 `http://127.0.0.1:8765`，功能和电脑版完全一样 |
| **真 APK（Kivy/Buildozer）**（本目录） | 是（Linux/WSL/CI） | 一个可安装的 App，截图/点地标/识别/补点/选里程/绕点圈数/生成 JSON 全在手机上完成 |
| PWA / Pyodide 网页 | 需改造 | 以后可选：把 Python 核心跑进浏览器，完全离线、可加到桌面 |

> 说明：本工具的开发环境没有 Android SDK/JDK，**无法在这里直接产出签名 APK**；
> 但 APK 工程和构建脚本都已备好，按下面步骤即可产出（GitHub Actions 最省事）。

## 方式一：Termux 网页版（最快）

```bash
# 手机装好 Termux 后，把 campus_route_tool 整个目录拷到手机（如 ~/campus_route_tool）
cd ~/campus_route_tool
bash android/install_termux.sh
# 然后手机浏览器访问 http://127.0.0.1:8765
```

功能：上传截图 → 点 2 个地标 → 识别打卡点（不足用手动补点）→ 计算可选路程 → 选绕点圈数 → 生成路线并下载 `.route.json`。

## 方式二：打包 APK（Kivy + Buildozer）

### 本地构建（WSL / Linux，推荐 Ubuntu）

```bash
# 依赖：JDK17、buildozer、cython
sudo apt install -y openjdk-17-jdk git zip unzip autoconf libtool pkg-config \
  zlib1g-dev libncurses5-dev libncursesw5-dev libffi-dev libssl-dev libltdl-dev
pip install buildozer cython

# 在工具根目录执行（会组装 mobile/.build 并打包）
bash mobile/build_apk.sh

# 产物：mobile/.build/bin/*.apk（debug 签名，可直接安装）
```

> 首次构建会下载 Android SDK/NDK（约 1~2 GB），耗时较长；arm64 手机会自动匹配。

### GitHub Actions 构建（无需本地环境）

1. 把 `campus_route_tool/` 作为仓库根提交到 GitHub；
2. 把 `mobile/build-apk.yml` 复制到 `.github/workflows/build-apk.yml`；
3. 推送后在 Actions 里手动运行 `Build Android APK`，完成后下载 `campusroute-debug-apk` 工件；
4. 手机安装 APK（允许“未知来源”）。

## APK 版功能

与桌面版共用同一套 `core/`、`assets/`、`campus_profile.json`：

- 打开 App 截图（`/sdcard/Download` 等目录）
- 选择地标并点选（≥2 个，建议 3 个做残差校验）
- 识别 5 个打卡点；被遮挡/显示成 ✓ 的点用「补点」手动点
- 计算可选路程（自动 / 2~5.5 km），选择里程
- 绕点圈数 0/1/2（在打卡点附近反复经过，防止打不上卡）
- 生成 `.route.json`（70~200 点、打卡点精确节点）和预览图
- 输出目录：`/sdcard/Download/campus_route/`

## 注意

- 首次打开需授予存储权限（用于读截图、写路线文件）。
- Kivy 版界面较朴素，但所有规划逻辑与电脑版一致；建议先在 Termux 网页版确认效果，再把 APK 当日常工具。
- 若截图被 App 悬浮窗遮挡，先在手机上把悬浮窗关掉再截图。
