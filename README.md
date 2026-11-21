# YT / Bilibili → GIF Studio

貼上 **YouTube** 或 **Bilibili** 影片網址並標明時間軸，即可快速擷取指定片段，透過 FFmpeg 調色盤最佳化產出高畫質、可直接下載的 GIF 動圖！

## 下載 Windows 免安裝執行檔（推薦）

不需要安裝 Python、FFmpeg 或任何環境，下載單一 `.exe` 雙擊即可使用：

- **最新版 Release 頁面**：[前往 GitHub Releases 下載](https://github.com/sakiwatashi/gif/releases/latest)
- **直接下載執行檔**：[YT-Bili-GIF-Studio.exe](https://github.com/sakiwatashi/gif/releases/latest/download/YT-Bili-GIF-Studio.exe)（Windows 64-bit，約 59 MB）

### 使用步驟
1. 下載並雙擊執行 `YT-Bili-GIF-Studio.exe`。
   > 若 Windows 跳出「Windows 已保護您的電腦（SmartScreen）」提示，點選 **「其他資訊」→「仍要執行」** 即可。
2. 程式會自動啟動本機服務並開啟預設瀏覽器進入操作介面。
3. 貼上 **YouTube** 或 **Bilibili** 網址，設定開始與結束時間軸（或直接輸入如 `0:15 - 0:22`），點擊 **「開始製作 GIF」**。
4. 完成後可直接在網頁預覽並點 **「下載 GIF」**，檔案也會同步保存在執行檔同層的 `outputs/` 資料夾中。
5. 使用完畢直接關閉黑色狀態視窗即可結束程式。

---

## 功能特色

- **雙平台原生支援**：
  - **YouTube**：一般影片、`youtu.be` 短網址、`Shorts`、`Live`、`?t=` 時間戳記連結；內嵌播放器支援邊播邊抓 **`[ 設為起點`** / **`設為終點 ]`** 與 **`↻ 預覽此片段`** 循環檢查。
  - **Bilibili**：`bilibili.com/video/BV...`、`av...`、分 P `?p=`、`b23.tv` 短網址、裸 `BV` 號，以及直接貼上 B 站 App 分享文字自動擷取網址；支援官方內嵌播放器預覽。
- **多種時間軸標定方式**：互動雙滑桿、`-0.5s / +0.5s` 微調、快速秒數按鈕（3s / 5s / 8s / 10s / 15s）、快速區間貼上（`0:15 - 0:22`、`1:05~1:12`）。
- **只下載指定片段**：透過 `yt-dlp` 精準截取選取區間，不必浪費時間下載整部影片。
- **高畫質 GIF 轉檔參數**：使用 FFmpeg `palettegen + paletteuse` 調色盤最佳化，可自訂：
  - 解析度寬度：`320p` / `480p` / `640p` / `720p`
  - 幀率（FPS）：`8` / `10` / `12` / `15` / `20`
  - 畫質與檔案大小：`高畫質 (256色)` / `均衡 (128色)` / `輕量小檔 (64色)`
  - 播放速度：`0.5x` ~ `2x`
  - 播放模式：`一般循環` / `倒放` / `來回循環 (Boomerang)`

---

## 從原始碼執行 / 自行打包

### 1. 安裝相依套件

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

> 若電腦未安裝系統版 `ffmpeg`，可再安裝 `imageio-ffmpeg`（程式會自動使用內附的 `ffmpeg`）。

### 2. 啟動網頁介面

雙擊 `start.bat`，或執行：

```powershell
.\.venv\Scripts\python.exe server.py
```

### 3. 命令列（CLI）直接轉檔

```powershell
.\.venv\Scripts\python.exe gif_engine.py "https://www.youtube.com/watch?v=影片ID" "0:15" "0:22" --width 480 --fps 12
.\.venv\Scripts\python.exe gif_engine.py "https://www.bilibili.com/video/BV1hryaz6E1u/" "0:05" "0:08" --width 480 --fps 12
```

### 4. 重新打包單一獨立 EXE

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller imageio-ffmpeg
.\.venv\Scripts\python.exe build_exe.py
```

打包完成後會產出 `dist/YT-Bili-GIF-Studio.exe`。
