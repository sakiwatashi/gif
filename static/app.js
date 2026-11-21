(() => {
  "use strict";

  // State
  const state = {
    url: "",
    platform: null, // "youtube" | "bilibili"
    videoId: null,
    title: "",
    duration: 60,
    startSec: 0,
    endSec: 5,
    width: 480,
    fps: 12,
    quality: "high",
    speed: 1.0,
    mode: "normal",
    isGenerating: false,
    loopPreview: false,
    ytApiReady: false,
    player: null,
    playerReady: false,
    pendingVideoId: null,
    pollTimer: null,
    playerTickTimer: null,
  };

  // DOM Elements
  const $ = (id) => document.getElementById(id);
  const urlForm = $("urlForm");
  const urlInput = $("urlInput");
  const clearUrlBtn = $("clearUrlBtn");
  const loadVideoBtn = $("loadVideoBtn");
  const urlStatus = $("urlStatus");

  const playerPlaceholder = $("playerPlaceholder");
  const ytPlayerMount = $("ytPlayerMount");
  const biliPlayerMount = $("biliPlayerMount");
  const platformBadge = $("platformBadge");
  const videoMetaRow = $("videoMetaRow");
  const videoTitle = $("videoTitle");
  const videoUploader = $("videoUploader");
  const videoDurationBadge = $("videoDurationBadge");
  const ytSyncControls = $("ytSyncControls");
  const biliSyncHint = $("biliSyncHint");
  const currentTimeDisplay = $("currentTimeDisplay");
  const setStartFromPlayerBtn = $("setStartFromPlayerBtn");
  const setEndFromPlayerBtn = $("setEndFromPlayerBtn");
  const previewLoopBtn = $("previewLoopBtn");

  const startRange = $("startRange");
  const endRange = $("endRange");
  const rangeHighlight = $("rangeHighlight");
  const clipLengthPill = $("clipLengthPill");
  const tickStart = $("tickStart");
  const tickMid = $("tickMid");
  const tickEnd = $("tickEnd");

  const quickRangeInput = $("quickRangeInput");
  const applyQuickRangeBtn = $("applyQuickRangeBtn");
  const startInput = $("startInput");
  const endInput = $("endInput");
  const generateBtn = $("generateBtn");
  const progressPanel = $("progressPanel");
  const progressMessage = $("progressMessage");
  const progressPercent = $("progressPercent");
  const progressBarFill = $("progressBarFill");
  const errorBanner = $("errorBanner");

  const resultSection = $("resultSection");
  const resultGifImg = $("resultGifImg");
  const resultTitle = $("resultTitle");
  const resultMetaBadges = $("resultMetaBadges");
  const resultFilename = $("resultFilename");
  const openGifNewTab = $("openGifNewTab");
  const downloadGifBtn = $("downloadGifBtn");
  const downloadGifBtnBig = $("downloadGifBtnBig");

  const historyGrid = $("historyGrid");
  const refreshHistoryBtn = $("refreshHistoryBtn");

  // ---------- URL Parsing (YouTube + Bilibili) ----------

  function extractEmbeddedUrl(input) {
    const raw = (input || "").trim();
    const m = raw.match(/https?:\/\/[^\s<>"'\]）】]+/i);
    if (m) return m[0].replace(/[.,;!?，。；！？]+$/, "");
    return raw;
  }

  function parseVideoInput(input) {
    const raw = extractEmbeddedUrl(input);
    if (!raw) return null;

    // Bare Bilibili BV / av ID
    if (/^BV[0-9A-Za-z]{10}$/.test(raw)) {
      return {
        platform: "bilibili",
        videoId: raw,
        page: 1,
        embedUrl: `https://player.bilibili.com/player.html?bvid=${raw}&page=1&high_quality=1&autoplay=0`,
      };
    }
    if (/^av\d+$/i.test(raw)) {
      const aid = raw.slice(2);
      return {
        platform: "bilibili",
        videoId: raw.toLowerCase(),
        page: 1,
        embedUrl: `https://player.bilibili.com/player.html?aid=${aid}&page=1&high_quality=1&autoplay=0`,
      };
    }

    // Bare YouTube 11-char ID
    if (/^[A-Za-z0-9_-]{11}$/.test(raw)) {
      return { platform: "youtube", videoId: raw, page: 1, embedUrl: null };
    }

    try {
      const normalized = /^https?:\/\//i.test(raw) ? raw : "https://" + raw;
      const u = new URL(normalized);
      const host = u.hostname.toLowerCase();
      const bareHost = host.replace(/^(www\.|m\.)/i, "");

      // Bilibili short link b23.tv
      if (bareHost === "b23.tv") {
        const code = u.pathname.replace(/^\/+/, "").split("/")[0];
        if (code) {
          return { platform: "bilibili", videoId: code, page: 1, embedUrl: null };
        }
      }

      // Bilibili main / mobile
      if (bareHost === "bilibili.com" || bareHost.endsWith(".bilibili.com")) {
        const page = Math.max(1, parseInt(u.searchParams.get("p") || "1", 10) || 1);
        const bvMatch = u.pathname.match(/\/(BV[0-9A-Za-z]{10})/);
        if (bvMatch) {
          const bvid = bvMatch[1];
          return {
            platform: "bilibili",
            videoId: bvid,
            page,
            embedUrl: `https://player.bilibili.com/player.html?bvid=${bvid}&page=${page}&high_quality=1&autoplay=0`,
          };
        }
        const avMatch = u.pathname.match(/\/(av\d+)/i);
        if (avMatch) {
          const avid = avMatch[1].toLowerCase();
          return {
            platform: "bilibili",
            videoId: avid,
            page,
            embedUrl: `https://player.bilibili.com/player.html?aid=${avid.slice(2)}&page=${page}&high_quality=1&autoplay=0`,
          };
        }
        const epMatch = u.pathname.match(/\/bangumi\/play\/((?:ep|ss)\d+)/i);
        if (epMatch) {
          return { platform: "bilibili", videoId: epMatch[1].toLowerCase(), page: 1, embedUrl: null };
        }
        const qBvid = u.searchParams.get("bvid");
        if (qBvid && /^BV[0-9A-Za-z]{10}$/.test(qBvid)) {
          return {
            platform: "bilibili",
            videoId: qBvid,
            page,
            embedUrl: `https://player.bilibili.com/player.html?bvid=${qBvid}&page=${page}&high_quality=1&autoplay=0`,
          };
        }
      }

      // YouTube
      if (bareHost === "youtu.be") {
        const id = u.pathname.replace(/^\/+/, "").split("/")[0];
        if (/^[A-Za-z0-9_-]{11}$/.test(id)) {
          return { platform: "youtube", videoId: id, page: 1, embedUrl: null };
        }
      }
      if (["youtube.com", "youtube-nocookie.com", "music.youtube.com"].includes(bareHost)) {
        if (u.pathname === "/watch") {
          const id = u.searchParams.get("v");
          if (id && /^[A-Za-z0-9_-]{11}$/.test(id)) {
            return { platform: "youtube", videoId: id, page: 1, embedUrl: null };
          }
        }
        const parts = u.pathname.split("/").filter(Boolean);
        if (parts.length >= 2 && ["shorts", "embed", "live", "v"].includes(parts[0])) {
          if (/^[A-Za-z0-9_-]{11}$/.test(parts[1])) {
            return { platform: "youtube", videoId: parts[1], page: 1, embedUrl: null };
          }
        }
      }
    } catch {
      return null;
    }
    return null;
  }

  function extractStartFromUrl(input) {
    try {
      const raw = extractEmbeddedUrl(input);
      const normalized = /^https?:\/\//i.test(raw) ? raw : "https://" + raw;
      const u = new URL(normalized);
      const t = u.searchParams.get("t") || u.searchParams.get("start");
      if (!t) return null;
      return parseTimestamp(t);
    } catch {
      return null;
    }
  }

  function parseTimestamp(str) {
    if (typeof str === "number" && !Number.isNaN(str)) return Math.max(0, str);
    let text = String(str || "").trim();
    if (!text) return null;
    text = text.replace(/：/g, ":").replace(/[．。]/g, ".");

    const hmsMatch = text.match(/^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s?)?$/i);
    if (hmsMatch && /[hms]/i.test(text) && (hmsMatch[1] || hmsMatch[2] || hmsMatch[3])) {
      const h = parseFloat(hmsMatch[1] || 0);
      const m = parseFloat(hmsMatch[2] || 0);
      const s = parseFloat(hmsMatch[3] || 0);
      return Math.max(0, Math.round((h * 3600 + m * 60 + s) * 10) / 10);
    }

    const parts = text.split(":");
    if (parts.some((p) => p === "" || Number.isNaN(Number(p)))) return null;
    let sec = 0;
    if (parts.length === 1) {
      sec = parseFloat(parts[0]);
    } else if (parts.length === 2) {
      sec = parseInt(parts[0], 10) * 60 + parseFloat(parts[1]);
    } else if (parts.length === 3) {
      sec = parseInt(parts[0], 10) * 3600 + parseInt(parts[1], 10) * 60 + parseFloat(parts[2]);
    } else {
      return null;
    }
    if (Number.isNaN(sec) || sec < 0) return null;
    return Math.round(sec * 10) / 10;
  }

  function formatTimestamp(sec, alwaysTenths = false) {
    const safe = Math.max(0, Number(sec) || 0);
    const total = Math.floor(safe);
    const tenths = Math.round((safe - total) * 10);
    let carry = 0;
    let t = tenths;
    if (t >= 10) {
      t = 0;
      carry = 1;
    }
    const adj = total + carry;
    const h = Math.floor(adj / 3600);
    const m = Math.floor((adj % 3600) / 60);
    const s = adj % 60;
    const pad = (n) => String(n).padStart(2, "0");
    const frac = alwaysTenths || t > 0 ? `.${t}` : "";
    if (h > 0) return `${pad(h)}:${pad(m)}:${pad(s)}${frac}`;
    return `${pad(m)}:${pad(s)}${frac}`;
  }

  function formatBytes(bytes) {
    if (!bytes) return "0 B";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  }

  function showUrlStatus(msg, type = "") {
    if (!msg) {
      urlStatus.classList.add("hidden");
      return;
    }
    urlStatus.textContent = msg;
    urlStatus.className = `status-line ${type}`;
    urlStatus.classList.remove("hidden");
  }

  function showError(msg) {
    if (!msg) {
      errorBanner.classList.add("hidden");
      return;
    }
    errorBanner.textContent = msg;
    errorBanner.classList.remove("hidden");
  }

  function setPlatformUI(platform) {
    state.platform = platform;
    if (platform === "bilibili") {
      platformBadge.textContent = "Bilibili";
      platformBadge.className = "pill pill-bilibili";
      ytSyncControls.classList.add("hidden");
      biliSyncHint.classList.remove("hidden");
      state.loopPreview = false;
      previewLoopBtn.classList.remove("active-loop");
      previewLoopBtn.textContent = "↻ 預覽此片段";
    } else if (platform === "youtube") {
      platformBadge.textContent = "YouTube";
      platformBadge.className = "pill pill-youtube";
      biliSyncHint.classList.add("hidden");
      ytSyncControls.classList.remove("hidden");
    } else {
      platformBadge.classList.add("hidden");
    }
  }

  // ---------- Timeline Sync ----------

  function syncTimelineUI(skipInputs = false) {
    const maxDur = Math.max(10, state.duration || 60);
    startRange.max = String(maxDur);
    endRange.max = String(maxDur);

    state.startSec = Math.max(0, Math.min(state.startSec, maxDur - 0.5));
    state.endSec = Math.max(state.startSec + 0.2, Math.min(state.endSec, maxDur));

    startRange.value = String(state.startSec);
    endRange.value = String(state.endSec);

    if (!skipInputs) {
      startInput.value = formatTimestamp(state.startSec);
      endInput.value = formatTimestamp(state.endSec);
    }

    const leftPct = (state.startSec / maxDur) * 100;
    const rightPct = (state.endSec / maxDur) * 100;
    rangeHighlight.style.left = `${leftPct}%`;
    rangeHighlight.style.width = `${Math.max(0.5, rightPct - leftPct)}%`;

    const len = Math.max(0, state.endSec - state.startSec);
    clipLengthPill.textContent = `片段長度 ${len.toFixed(1)} 秒`;
    clipLengthPill.style.borderColor = len > 60 ? "rgba(248, 113, 113, 0.7)" : "";

    tickStart.textContent = formatTimestamp(0);
    tickMid.textContent = formatTimestamp(maxDur / 2);
    tickEnd.textContent = formatTimestamp(maxDur);
  }

  // ---------- Players (YouTube IFrame API & Bilibili Embed) ----------

  window.onYouTubeIframeAPIReady = () => {
    state.ytApiReady = true;
    if (state.pendingVideoId && state.platform === "youtube") {
      mountOrLoadYouTubePlayer(state.pendingVideoId);
      state.pendingVideoId = null;
    }
  };

  function mountOrLoadYouTubePlayer(videoId) {
    playerPlaceholder.classList.add("hidden");
    biliPlayerMount.classList.add("hidden");
    biliPlayerMount.innerHTML = "";
    ytPlayerMount.classList.remove("hidden");

    if (!state.ytApiReady || !window.YT || !window.YT.Player) {
      state.pendingVideoId = videoId;
      return;
    }

    if (state.player && state.playerReady) {
      state.player.cueVideoById(videoId);
      return;
    }

    ytPlayerMount.innerHTML = `<div id="ytPlayerInner"></div>`;
    state.player = new window.YT.Player("ytPlayerInner", {
      videoId,
      width: "100%",
      height: "100%",
      playerVars: {
        rel: 0,
        modestbranding: 1,
        playsinline: 1,
      },
      events: {
        onReady: () => {
          state.playerReady = true;
          setStartFromPlayerBtn.disabled = false;
          setEndFromPlayerBtn.disabled = false;
          previewLoopBtn.disabled = false;
          const d = state.player.getDuration ? state.player.getDuration() : 0;
          if (d > 0 && state.duration === 60) {
            state.duration = d;
            videoDurationBadge.textContent = `總長度 ${formatTimestamp(d)}`;
            videoDurationBadge.classList.remove("hidden");
            syncTimelineUI();
          }
          startPlayerTick();
        },
      },
    });
  }

  function mountBilibiliPlayer(embedUrl) {
    if (state.player && state.playerReady && state.player.pauseVideo) {
      try {
        state.player.pauseVideo();
      } catch {}
    }
    ytPlayerMount.classList.add("hidden");
    if (!embedUrl) {
      biliPlayerMount.classList.add("hidden");
      playerPlaceholder.classList.remove("hidden");
      return;
    }
    playerPlaceholder.classList.add("hidden");
    biliPlayerMount.classList.remove("hidden");
    biliPlayerMount.innerHTML = `
      <iframe
        src="${escapeHtml(embedUrl)}"
        scrolling="no"
        frameborder="0"
        allowfullscreen="true"
        sandbox="allow-top-navigation-by-user-activation allow-same-origin allow-forms allow-scripts"
        referrerpolicy="no-referrer"
      ></iframe>
    `;
  }

  function startPlayerTick() {
    if (state.playerTickTimer) clearInterval(state.playerTickTimer);
    state.playerTickTimer = setInterval(() => {
      if (state.platform !== "youtube" || !state.player || !state.playerReady || !state.player.getCurrentTime) return;
      const cur = state.player.getCurrentTime();
      currentTimeDisplay.textContent = formatTimestamp(cur, true);

      if (state.loopPreview) {
        if (cur >= state.endSec || cur < state.startSec - 0.5) {
          state.player.seekTo(state.startSec, true);
        }
      }
    }, 100);
  }

  // ---------- Load Video ----------

  async function loadVideo(rawUrl) {
    const trimmed = (rawUrl || "").trim();
    if (!trimmed) {
      showUrlStatus("請先貼上 YouTube 或 Bilibili 影片網址。", "error");
      return;
    }

    const parsed = parseVideoInput(trimmed);
    if (!parsed) {
      showUrlStatus("無法辨識網址，請貼上 YouTube（youtube.com / youtu.be）或 Bilibili（bilibili.com / b23.tv / BV號）連結。", "error");
      return;
    }

    state.url = trimmed;
    state.videoId = parsed.videoId;
    setPlatformUI(parsed.platform);
    showError("");

    if (parsed.platform === "youtube") {
      mountOrLoadYouTubePlayer(parsed.videoId);
    } else {
      mountBilibiliPlayer(parsed.embedUrl);
    }

    const urlStart = extractStartFromUrl(trimmed);
    if (urlStart !== null && urlStart >= 0) {
      state.startSec = urlStart;
      state.endSec = urlStart + 5;
      syncTimelineUI();
    }

    loadVideoBtn.disabled = true;
    loadVideoBtn.querySelector(".btn-label").textContent = "載入中...";
    const siteName = parsed.platform === "bilibili" ? "Bilibili" : "YouTube";
    showUrlStatus(`正在從 ${siteName} 讀取影片標題與總長度...`);

    try {
      const resp = await fetch("/api/info", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: trimmed }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.detail || "讀取影片資訊失敗");
      }

      state.title = data.title || "";
      state.duration = Math.max(1, Number(data.duration) || 60);
      if (data.platform) setPlatformUI(data.platform);
      if (data.platform === "bilibili" && data.embed_url && !parsed.embedUrl) {
        mountBilibiliPlayer(data.embed_url);
      }

      videoTitle.textContent = data.title || `${siteName} (${parsed.videoId})`;
      videoUploader.textContent = data.uploader ? `UP主 / 頻道：${data.uploader}` : "";
      videoMetaRow.classList.remove("hidden");

      videoDurationBadge.textContent = `總長度 ${formatTimestamp(state.duration)}`;
      videoDurationBadge.classList.remove("hidden");

      if (urlStart !== null && urlStart < state.duration) {
        state.startSec = urlStart;
        state.endSec = Math.min(state.duration, urlStart + 5);
      } else {
        state.startSec = 0;
        state.endSec = Math.min(state.duration, 5);
      }
      syncTimelineUI();

      if (state.platform === "bilibili") {
        showUrlStatus("Bilibili 影片已載入！可在播放器確認畫面，並透過拉桿或右側欄位標定時間軸。", "success");
      } else {
        showUrlStatus("YouTube 影片已載入！可直接邊播邊點「設為起點 / 設為終點」，或在右側輸入時間軸。", "success");
      }
    } catch (err) {
      showUrlStatus(`讀取影片詳細資訊失敗：${err.message}`, "error");
    } finally {
      loadVideoBtn.disabled = false;
      loadVideoBtn.querySelector(".btn-label").textContent = "載入影片";
    }
  }

  // ---------- Generate GIF ----------

  async function startGeneration() {
    showError("");
    const rawUrl = urlInput.value.trim();
    if (!rawUrl || !parseVideoInput(rawUrl)) {
      showError("請先貼上有效的 YouTube 或 Bilibili 影片網址。");
      urlInput.focus();
      return;
    }

    const parsedStart = parseTimestamp(startInput.value);
    const parsedEnd = parseTimestamp(endInput.value);
    if (parsedStart === null || parsedEnd === null) {
      showError("時間格式不正確，請使用例如 00:15、1:23.5 或純秒數 95。");
      return;
    }
    if (parsedEnd <= parsedStart) {
      showError("結束時間必須大於開始時間。");
      return;
    }
    if (parsedEnd - parsedStart > 60) {
      showError("單次片段長度上限為 60 秒，建議控制在 2~15 秒效果最好。");
      return;
    }

    state.startSec = parsedStart;
    state.endSec = parsedEnd;
    syncTimelineUI();

    state.isGenerating = true;
    generateBtn.disabled = true;
    generateBtn.querySelector(".btn-label").textContent = "製作中，請稍候...";
    progressPanel.classList.remove("hidden");
    updateProgress(5, "正在送出製作任務...");

    try {
      const resp = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: rawUrl,
          start: parsedStart,
          end: parsedEnd,
          width: state.width,
          fps: state.fps,
          speed: state.speed,
          quality: state.quality,
          mode: state.mode,
          video_title: state.title || null,
        }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.detail || "無法建立製作任務");
      }
      pollJob(data.job_id);
    } catch (err) {
      finishGenerationWithError(err.message);
    }
  }

  function updateProgress(pct, message) {
    progressBarFill.style.width = `${Math.max(0, Math.min(100, pct))}%`;
    progressPercent.textContent = `${Math.round(pct)}%`;
    progressMessage.textContent = message || "處理中...";
  }

  function pollJob(jobId) {
    if (state.pollTimer) clearInterval(state.pollTimer);
    state.pollTimer = setInterval(async () => {
      try {
        const resp = await fetch(`/api/jobs/${jobId}`);
        const job = await resp.json();
        if (!resp.ok) {
          throw new Error(job.detail || "查詢進度失敗");
        }
        updateProgress(job.progress || 0, job.message);

        if (job.status === "done") {
          clearInterval(state.pollTimer);
          state.pollTimer = null;
          state.isGenerating = false;
          generateBtn.disabled = false;
          generateBtn.querySelector(".btn-label").textContent = "開始製作 GIF";
          showResult(job.result);
          loadHistory();
        } else if (job.status === "error") {
          clearInterval(state.pollTimer);
          state.pollTimer = null;
          finishGenerationWithError(job.error || job.message || "轉檔失敗");
        }
      } catch (err) {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
        finishGenerationWithError(err.message);
      }
    }, 450);
  }

  function finishGenerationWithError(msg) {
    state.isGenerating = false;
    generateBtn.disabled = false;
    generateBtn.querySelector(".btn-label").textContent = "開始製作 GIF";
    progressPanel.classList.add("hidden");
    showError(msg);
  }

  function showResult(item) {
    if (!item) return;
    const cacheBust = `${item.gif_url}?t=${Date.now()}`;
    resultGifImg.src = cacheBust;
    resultTitle.textContent = item.title || item.filename;
    resultFilename.textContent = item.filename;

    openGifNewTab.href = item.gif_url;
    downloadGifBtn.href = item.download_url;
    downloadGifBtn.setAttribute("download", item.filename);
    downloadGifBtnBig.href = item.download_url;
    downloadGifBtnBig.setAttribute("download", item.filename);

    const platformTag =
      item.platform === "bilibili" ? "Bilibili" : item.platform === "youtube" ? "YouTube" : null;

    const badges = [
      platformTag,
      item.width && item.height ? `${item.width} × ${item.height}` : null,
      item.duration ? `長度 ${item.duration}s` : null,
      item.fps ? `${item.fps} FPS` : null,
      `檔案大小 ${formatBytes(item.file_size)}`,
      item.end_time > item.start_time
        ? `片段 ${formatTimestamp(item.start_time)} ~ ${formatTimestamp(item.end_time)}`
        : null,
    ].filter(Boolean);

    resultMetaBadges.innerHTML = badges
      .map((b) => {
        const cls =
          b === "Bilibili" ? "pill pill-bilibili" : b === "YouTube" ? "pill pill-youtube" : "pill";
        return `<span class="${cls}">${escapeHtml(b)}</span>`;
      })
      .join("");

    resultSection.classList.remove("hidden");
    resultSection.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  // ---------- History ----------

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function loadHistory() {
    try {
      const resp = await fetch("/api/history");
      const items = await resp.json();
      if (!Array.isArray(items) || items.length === 0) {
        historyGrid.innerHTML = `<p class="muted empty-history">尚未產出任何 GIF，貼上 YouTube 或 Bilibili 網址試試看吧！</p>`;
        return;
      }

      historyGrid.innerHTML = items
        .map((item) => {
          const rangeLabel =
            item.end_time > item.start_time
              ? `${formatTimestamp(item.start_time)} ~ ${formatTimestamp(item.end_time)}`
              : "";
          return `
            <article class="history-item">
              <img class="history-thumb" src="${item.gif_url}" alt="${escapeHtml(item.title)}" loading="lazy" data-preview='${escapeHtml(JSON.stringify(item))}' />
              <div class="history-body">
                <div class="history-title" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</div>
                <div class="history-meta mono">
                  <span>${escapeHtml(rangeLabel || `${item.width}x${item.height}`)}</span>
                  <span>${formatBytes(item.file_size)}</span>
                </div>
                <div class="history-actions">
                  <a class="btn btn-secondary btn-sm" href="${item.download_url}" download="${escapeHtml(item.filename)}">⬇ 下載</a>
                  <button type="button" class="btn-danger-ghost" data-delete="${escapeHtml(item.filename)}" title="刪除">刪除</button>
                </div>
              </div>
            </article>
          `;
        })
        .join("");

      historyGrid.querySelectorAll(".history-thumb").forEach((img) => {
        img.addEventListener("click", () => {
          try {
            const item = JSON.parse(img.getAttribute("data-preview"));
            showResult(item);
          } catch {}
        });
      });

      historyGrid.querySelectorAll("[data-delete]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const fname = btn.getAttribute("data-delete");
          if (!confirm(`確定要刪除 ${fname} 嗎？`)) return;
          await fetch(`/api/files/${encodeURIComponent(fname)}`, { method: "DELETE" });
          loadHistory();
        });
      });
    } catch {
      // Ignore silent history refresh failure
    }
  }

  // ---------- Event Listeners ----------

  urlForm.addEventListener("submit", (e) => {
    e.preventDefault();
    loadVideo(urlInput.value);
  });

  urlInput.addEventListener("input", () => {
    clearUrlBtn.classList.toggle("hidden", !urlInput.value);
  });

  urlInput.addEventListener("paste", () => {
    setTimeout(() => {
      const val = urlInput.value.trim();
      clearUrlBtn.classList.toggle("hidden", !val);
      if (parseVideoInput(val)) {
        loadVideo(val);
      }
    }, 30);
  });

  clearUrlBtn.addEventListener("click", () => {
    urlInput.value = "";
    clearUrlBtn.classList.add("hidden");
    showUrlStatus("");
    urlInput.focus();
  });

  // Dual range sliders
  startRange.addEventListener("input", () => {
    const val = parseFloat(startRange.value);
    state.startSec = Math.min(val, state.endSec - 0.5);
    syncTimelineUI();
    if (state.platform === "youtube" && state.player && state.playerReady) {
      state.player.seekTo(state.startSec, true);
    }
  });

  endRange.addEventListener("input", () => {
    const val = parseFloat(endRange.value);
    state.endSec = Math.max(val, state.startSec + 0.5);
    syncTimelineUI();
  });

  // Manual time inputs
  startInput.addEventListener("change", () => {
    const v = parseTimestamp(startInput.value);
    if (v !== null) {
      state.startSec = v;
      if (state.endSec <= state.startSec) {
        state.endSec = Math.min(state.duration, state.startSec + 5);
      }
      syncTimelineUI();
      if (state.platform === "youtube" && state.player && state.playerReady) {
        state.player.seekTo(state.startSec, true);
      }
    }
  });

  endInput.addEventListener("change", () => {
    const v = parseTimestamp(endInput.value);
    if (v !== null) {
      state.endSec = v;
      if (state.endSec <= state.startSec) {
        state.startSec = Math.max(0, state.endSec - 3);
      }
      syncTimelineUI();
    }
  });

  // Quick range paste (e.g. "0:15 - 0:22", "1:05~1:12", "15 到 22")
  function applyQuickRange() {
    const text = quickRangeInput.value.trim();
    if (!text) return;
    const parts = text.split(/\s*(?:-|~|～|到|至|to|—|–)\s*/i).filter(Boolean);
    if (parts.length !== 2) {
      showError("快速區間格式請輸入例如 0:15 - 0:22 或 1:05~1:12");
      return;
    }
    const s = parseTimestamp(parts[0]);
    const e = parseTimestamp(parts[1]);
    if (s === null || e === null || e <= s) {
      showError("無法解析時間區間，請確認結束時間大於開始時間。");
      return;
    }
    showError("");
    state.startSec = s;
    state.endSec = e;
    if (e > state.duration) state.duration = e;
    syncTimelineUI();
    if (state.platform === "youtube" && state.player && state.playerReady) {
      state.player.seekTo(state.startSec, true);
    }
  }

  applyQuickRangeBtn.addEventListener("click", applyQuickRange);
  quickRangeInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      applyQuickRange();
    }
  });

  // Nudge buttons
  document.querySelectorAll(".nudge-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.dataset.target;
      const delta = parseFloat(btn.dataset.delta);
      if (target === "start") {
        state.startSec = Math.max(0, Math.round((state.startSec + delta) * 10) / 10);
        if (state.startSec >= state.endSec - 0.2) {
          state.endSec = state.startSec + 0.5;
        }
        if (state.platform === "youtube" && state.player && state.playerReady) {
          state.player.seekTo(state.startSec, true);
        }
      } else {
        state.endSec = Math.max(state.startSec + 0.2, Math.round((state.endSec + delta) * 10) / 10);
      }
      syncTimelineUI();
    });
  });

  // Quick duration chips
  document.querySelectorAll(".chip-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const len = parseFloat(btn.dataset.len);
      state.endSec = Math.min(state.duration, Math.round((state.startSec + len) * 10) / 10);
      syncTimelineUI();
    });
  });

  // YouTube player sync buttons
  setStartFromPlayerBtn.addEventListener("click", () => {
    if (state.platform !== "youtube" || !state.player || !state.playerReady) return;
    const cur = Math.round(state.player.getCurrentTime() * 10) / 10;
    state.startSec = cur;
    if (state.endSec <= state.startSec + 0.2) {
      state.endSec = Math.min(state.duration, cur + 5);
    }
    syncTimelineUI();
  });

  setEndFromPlayerBtn.addEventListener("click", () => {
    if (state.platform !== "youtube" || !state.player || !state.playerReady) return;
    const cur = Math.round(state.player.getCurrentTime() * 10) / 10;
    if (cur <= state.startSec + 0.2) {
      state.startSec = Math.max(0, cur - 3);
    }
    state.endSec = cur;
    syncTimelineUI();
  });

  previewLoopBtn.addEventListener("click", () => {
    if (state.platform !== "youtube" || !state.player || !state.playerReady) return;
    state.loopPreview = !state.loopPreview;
    previewLoopBtn.classList.toggle("active-loop", state.loopPreview);
    previewLoopBtn.textContent = state.loopPreview ? "■ 停止片段循環" : "↻ 預覽此片段";
    if (state.loopPreview) {
      state.player.seekTo(state.startSec, true);
      state.player.playVideo();
    } else {
      state.player.pauseVideo();
    }
  });

  // Segmented controls
  document.querySelectorAll(".segmented").forEach((group) => {
    const key = group.dataset.setting;
    group.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => {
        group.querySelectorAll("button").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        const val = btn.dataset.value;
        if (key === "width" || key === "fps") {
          state[key] = parseInt(val, 10);
        } else if (key === "speed") {
          state[key] = parseFloat(val);
        } else {
          state[key] = val;
        }
      });
    });
  });

  generateBtn.addEventListener("click", startGeneration);
  refreshHistoryBtn.addEventListener("click", loadHistory);

  // Initial setup
  syncTimelineUI();
  loadHistory();
})();
