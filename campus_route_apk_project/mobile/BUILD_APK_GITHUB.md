# 生成 Android APK（两种方式）

> 本工具的开发机是 Windows，没有 JDK / Android SDK / WSL / Docker，
> 因此**无法在这台机器上直接产出 APK**。APK 工程与构建脚本已备好，按下面任一方式即可拿到可安装的 APK。

## 方式 A：GitHub Actions（推荐，不用装任何环境，约 10 分钟）

1. 登录 GitHub，新建一个仓库（Private 也可以）。
2. 把 `campus_route_apk_project.zip` 解压后的**全部内容**上传到仓库根目录，
   确认仓库根目录如下：
   ```
   .github/workflows/build-apk.yml
   campus_profile.json
   core/
   assets/
   mobile/            (main.py + buildozer.spec + build_apk.sh)
   ```
   传法二选一：
   - 网页版：仓库页面 → Add file → Upload files，把解压后的文件夹内容拖进去，Commit。
   - 命令行：
     ```bash
     cd campus_route_apk_project
     git init && git add . && git commit -m "apk project"
     git branch -M main
     git remote add origin https://github.com/<你的用户名>/<仓库名>.git
     git push -u origin main
     ```
3. 打开仓库 → **Actions** 标签 → 左侧选 `Build Android APK` → **Run workflow**。
4. 等待 8~15 分钟（首次要下载 Android SDK/NDK，比较久）。
5. 运行完成后，在本次运行页面底部 **Artifacts** 下载 `campusroute-debug-apk`，
   解压得到 `campusroute-1.0-*-debug.apk`。
6. 把 APK 传到手机安装（需要允许「未知来源/安装未知应用」）。

> debug 签名可以直接安装使用；如果要上架应用商店，再配置自己的 keystore 做 release 签名。

## 方式 B：本地 Linux / WSL 构建

需要 JDK17 + buildozer（Windows 原生不行，WSL/Linux 可以）：

```bash
sudo apt update
sudo apt install -y openjdk-17-jdk git zip unzip autoconf libtool pkg-config \
  zlib1g-dev libncurses5-dev libncursesw5-dev libffi-dev libssl-dev libltdl-dev cmake
pip install buildozer cython

cd campus_route_apk_project
bash mobile/build_apk.sh
# 产物：mobile/.build/bin/*.apk
```

首次构建会下载 Android SDK/NDK（约 1~2 GB）。

## 装好后怎么用

1. 打开 App，点「打开截图」，从手机相册/下载目录选 App 的打卡点截图（建议 5 个点位都在画面内）。
2. 选地标 → 点「点选地标」→ 在图上点该地标位置；重复 ≥2 个（建议 3 个）。
3. 点「识别打卡点」；若 1 号点显示成 ✓ 或被遮挡，用「补点」在图上点该点。
4. 点「计算可选路程」→ 选里程 → 选绕点圈数 → 「生成路线」。
5. 产物保存在 `/sdcard/Download/campus_route/`（.route.json + 预览图），
   把 `.route.json` 放到跑步 App 的路线目录即可。

## 常见问题

- **构建失败**：把 Actions 的日志发我，我来改（Kivy/Buildozer 对 Python、numpy 版本较敏感，
  首次构建常需要调一两轮 `buildozer.spec`）。
- **不想折腾构建**：可以先用「手机浏览器版」（Termux 里 `bash android/install_termux.sh`），
  功能完全一样，只是入口是浏览器页面。
- **手机安装被拦**：设置里允许「安装未知应用」；部分厂商 ROM 需关闭纯净模式。
