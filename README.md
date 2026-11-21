# YT / Bilibili → GIF Studio

本機 YouTube & Bilibili 片段轉 GIF 製作工具：貼上影片網址並標明時間軸，即可只下載需要的片段，透過 FFmpeg 調色盤最佳化產出高畫質可下載 GIF。

## 功能特色

- **雙平台支援**：
  - **YouTube**：一般影片、`youtu.be` 短網址、`Shorts`、`Live` 與 `?t=` 時間戳記連結，並支援內嵌播放器邊播邊抓起訖點與區間循環預覽。
  - **Bilibili**：`bilibili.com/video/BV...`、`av...`、分 P `?p=`、`b23.tv` 短網址、裸 `BV` 號，以及直接貼上 B 站 App 分享文字自動擷取連結，並支援內嵌預覽。
- **彈性時間軸標定**：
  - 互動雙滑桿、`-0.5s / +0.5s` 微調、快速秒數按鈕，以及快速區間貼上（如 `0:15 - 0:22` 或 `1:05~1:12`）。
- **只下載指定片段**：透過 `yt-dlp` 精準擷取指定區間，不必下載整部影片。
- **FFmpeg 調色盤最佳化**：支援自訂解析度寬度（320p–720p）、FPS（8–20）、畫質壓縮（高畫質 256 色 / 均衡 / 輕量小檔）、播放速度（0.5x–2x）與播放模式（一般循環 / 倒放 / 來回循環 Boomerang）。
- **單一獨立 EXE 打包**：可一鍵打包成內含 Python、網頁介面、`yt-dlp` 與精簡版 `ffmpeg.exe` 的單一 Windows `.exe`，對方電腦免安裝任何環境即可執行。

## 開發與執行方式

### 1. 安裝套件

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

> 若系統尚未安裝 `ffmpeg`，可再加裝 `imageio-ffmpeg`（程式會自動使用內附的 `ffmpeg`）。

### 2. 啟動網頁介面

雙擊 `start.bat`，或於終端機執行：

```powershell
.\.venv\Scripts\python.exe server.py
```

啟動後會自動開啟瀏覽器並連至 `http://127.0.0.1:8765`。

### 3. 命令列（CLI）直接產出

```powershell
.\.venv\Scripts\python.exe gif_engine.py "https://www.youtube.com/watch?v=影片ID" "0:15" "0:22" --width 480 --fps 12
.\.venv\Scripts\python.exe gif_engine.py "https://www.bilibili.com/video/BV1hryaz6E1u/" "0:05" "0:08" --width 480 --fps 12
```

產出的 GIF 檔案預設會儲存在 `outputs/` 資料夾中。

## 打包成單一獨立 Windows EXE

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller imageio-ffmpeg
.\.venv\Scripts\python.exe build_exe.py
```

打包完成後會產出 `dist/YT-to-GIF-Studio.exe`（約 59 MB），可直接分享給他人雙擊使用，不需安裝 Python、FFmpeg 或 yt-dlp。
