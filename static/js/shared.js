/** Shared utilities for Media Compressor UI. */

export const $ = (id) => document.getElementById(id);

export function fmtBytes(n) {
  if (!Number.isFinite(n)) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${i === 0 ? v.toFixed(0) : v.toFixed(2)} ${units[i]}`;
}

export function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

export function parseErrorDetail(rawText) {
  try {
    const j = JSON.parse(rawText);
    const d = j && j.detail;
    if (typeof d === "string") return d;
    if (d && typeof d === "object") {
      const base = String(d.message || d.msg || "Ошибка запроса");
      if (d.stderr_tail) {
        return `${base}\n\n${String(d.stderr_tail).slice(0, 1200)}`;
      }
      return base;
    }
  } catch (_) {
    /* ignore */
  }
  return rawText || "Неизвестная ошибка";
}

const STORAGE_KEY = "media-compressor-prefs";

export function loadPrefs() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
  } catch (_) {
    return {};
  }
}

export function savePrefs(patch) {
  try {
    const cur = loadPrefs();
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...cur, ...patch }));
  } catch (_) {
    /* ignore */
  }
}

/** Upload phase occupies 0…UPLOAD_WEIGHT% of the total bar. */
export const UPLOAD_WEIGHT = 35;

export function formatEta(sec) {
  if (!Number.isFinite(sec) || sec <= 0) return "почти готово";
  if (sec < 8) return "ещё несколько секунд";
  if (sec < 60) return `~${Math.round(sec)} с`;
  const m = Math.ceil(sec / 60);
  return m === 1 ? "~1 мин" : `~${m} мин`;
}

/** Rough processing time estimate (seconds) from file size. */
export function estimateProcessingSec(bytes, kind, { fileCount = 1, preset } = {}) {
  const mb = Math.max(0.05, bytes / (1024 * 1024));
  const slowPresets = new Set(["slow", "slower", "veryslow"]);
  const presetMul = slowPresets.has(preset) ? 2.2 : 1;

  if (kind === "video") return Math.max(4, mb * 6 * presetMul);
  if (kind === "audio") return Math.max(2, mb * 1.5);
  if (kind === "image-batch") return Math.max(2, mb * 0.25 * Math.sqrt(fileCount));
  if (kind === "image") return Math.max(1, mb * 0.4);
  if (kind === "inpaint") return Math.max(1, mb * 0.6);
  return Math.max(3, mb * 2);
}

export function phaseWithEta(message, etaSec) {
  const base = message || "Обработка…";
  if (etaSec == null || !Number.isFinite(etaSec)) return base;
  return `${base} · ${formatEta(etaSec)}`;
}

export function setCombinedProgress(setProgress, { uploadRatio, jobPercent, indeterminate = false }) {
  if (uploadRatio != null && uploadRatio < 1) {
    setProgress(uploadRatio * UPLOAD_WEIGHT, false);
    return;
  }
  if (indeterminate || jobPercent == null || jobPercent <= 0) {
    setProgress(UPLOAD_WEIGHT, true);
    return;
  }
  const tail = (100 - UPLOAD_WEIGHT) * (Math.min(100, jobPercent) / 100);
  setProgress(UPLOAD_WEIGHT + tail, false);
}

export function startProcessingCountdown(phaseEl, estimateSec, message = "Обработка") {
  const start = performance.now();
  const totalMs = Math.max(2000, estimateSec * 1000);
  const tick = () => {
    const elapsed = performance.now() - start;
    const remaining = Math.max(0, (totalMs - elapsed) / 1000);
    phaseEl.textContent = phaseWithEta(message, remaining);
  };
  tick();
  return setInterval(tick, 400);
}

export function jobEtaSec(job, fallbackEstimateSec) {
  if (job?.eta_sec != null && job.eta_sec > 0) return job.eta_sec;
  if (job?.percent > 0 && job?.elapsed_sec > 0) {
    return (job.elapsed_sec * (100 - job.percent)) / job.percent;
  }
  return fallbackEstimateSec;
}

export function showToast(message, kind = "info") {
  let root = document.getElementById("toast-root");
  if (!root) {
    root = document.createElement("div");
    root.id = "toast-root";
    root.className = "toast-root";
    root.setAttribute("aria-live", "polite");
    document.body.appendChild(root);
  }
  const el = document.createElement("div");
  el.className = `toast toast--${kind}`;
  el.textContent = message;
  root.appendChild(el);
  requestAnimationFrame(() => el.classList.add("toast--show"));
  setTimeout(() => {
    el.classList.remove("toast--show");
    setTimeout(() => el.remove(), 300);
  }, 4500);
}

export function assignFilesToInput(input, files) {
  const dt = new DataTransfer();
  for (const f of files) dt.items.add(f);
  input.files = dt.files;
}

export function createStatusHelpers(statusEl) {
  function setStatus(kind, html) {
    statusEl.classList.remove("status--ok", "status--err");
    if (kind === "ok") statusEl.classList.add("status--ok");
    if (kind === "err") statusEl.classList.add("status--err");
    statusEl.innerHTML = html;
    statusEl.classList.remove("is-hidden");
  }
  function hideStatus() {
    statusEl.classList.add("is-hidden");
    statusEl.innerHTML = "";
  }
  return { setStatus, hideStatus };
}

export function createProgressHelpers(progressEl, progressBar, phaseEl, cancelBtn) {
  let activeAbort = null;
  let pollTimer = null;

  function setProgress(pct, indeterminate = false) {
    progressEl.classList.toggle("progress--indeterminate", indeterminate);
    const clamped = Math.max(0, Math.min(100, pct));
    progressBar.style.width = indeterminate ? "100%" : `${clamped}%`;
    progressEl.setAttribute("aria-valuenow", String(Math.round(clamped)));
  }

  function showProgress(show) {
    progressEl.classList.toggle("is-hidden", !show);
    phaseEl.classList.toggle("is-hidden", !show);
    if (cancelBtn) cancelBtn.classList.toggle("is-hidden", !show);
    if (!show) {
      setProgress(0);
      phaseEl.textContent = "";
      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
      activeAbort = null;
    }
  }

  function setAbortController(ac) {
    activeAbort = ac;
  }

  function cancel() {
    if (activeAbort) activeAbort.abort();
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  if (cancelBtn) {
    cancelBtn.addEventListener("click", () => {
      cancel();
      phaseEl.textContent = "Отмена…";
    });
  }

  function startJobPoll(jobId, onProgress) {
    pollTimer = setInterval(async () => {
      try {
        const res = await fetch(`/jobs/${jobId}/progress`);
        if (!res.ok) return;
        const j = await res.json();
        onProgress(j);
        if (j.done && j.phase === "cancelled") {
          clearInterval(pollTimer);
          pollTimer = null;
          throw new Error("Отменено");
        }
      } catch (_) {
        /* ignore transient */
      }
    }, 500);
    return pollTimer;
  }

  return { setProgress, showProgress, setAbortController, cancel, startJobPoll };
}

export function populateSelect(selectEl, items, { valueKey = "id", labelKey = "label", hintKey = "hint" } = {}) {
  if (!selectEl || !items) return;
  const cur = selectEl.value;
  selectEl.innerHTML = items
    .map((item) => {
      const label = item[labelKey] || item[valueKey];
      const hint = item[hintKey] ? ` — ${item[hintKey]}` : "";
      return `<option value="${escapeHtml(String(item[valueKey]))}">${escapeHtml(label + hint)}</option>`;
    })
    .join("");
  if (cur && [...selectEl.options].some((o) => o.value === cur)) {
    selectEl.value = cur;
  }
}

export function parseFilenameFromResponse(xhr) {
  const cd = xhr.getResponseHeader("Content-Disposition") || "";
  const m = cd.match(/filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i);
  let filename = "download.bin";
  try {
    filename = decodeURIComponent((m && (m[1] || m[2])) || filename);
  } catch (_) {
    /* keep */
  }
  return filename;
}

export function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function showResultCard(cardEl, { inputBytes, outputBytes, elapsedSec, previewHtml, filename }) {
  if (!cardEl) return;
  const ratio = outputBytes / inputBytes;
  const savings = (1 - ratio) * 100;
  const timeStr = elapsedSec != null ? `${elapsedSec.toFixed(1)} с` : "—";
  cardEl.innerHTML =
    `<div class="result-card__head"><strong>Результат</strong>` +
    `<span class="result-card__time mono">${escapeHtml(timeStr)}</span></div>` +
    `<div class="result-card__stats">` +
    `<span>Было: <b class="mono">${escapeHtml(fmtBytes(inputBytes))}</b></span>` +
    `<span>→</span>` +
    `<span>Стало: <b class="mono">${escapeHtml(fmtBytes(outputBytes))}</b></span>` +
    `<span class="result-card__savings">${savings >= 0 ? "−" : "+"}${Math.abs(savings).toFixed(1)}%</span>` +
    `</div>` +
    (previewHtml || "") +
    `<div class="result-card__actions">` +
    `<button type="button" class="btn btn--primary btn--sm result-download">Скачать${filename ? `: ${escapeHtml(filename)}` : ""}</button>` +
    `</div>`;
  cardEl.classList.remove("is-hidden");
  cardEl._resultBlob = null;
  cardEl._resultFilename = filename;
  return cardEl;
}

export function bindResultDownload(cardEl, blob, filename) {
  if (!cardEl) return;
  cardEl._resultBlob = blob;
  cardEl._resultFilename = filename;
  const btn = cardEl.querySelector(".result-download");
  if (btn) {
    btn.addEventListener("click", () => {
      if (cardEl._resultBlob) triggerDownload(cardEl._resultBlob, cardEl._resultFilename || "download.bin");
    });
  }
}

export function postBlob(url, formData, { onUploadProgress, onUploadComplete, signal } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.responseType = "blob";
    if (signal) {
      signal.addEventListener("abort", () => xhr.abort());
    }
    xhr.upload.onprogress = onUploadProgress || (() => {});
    xhr.upload.onload = onUploadComplete || (() => {});
    xhr.onload = () => {
      const blob = xhr.response;
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve({ blob, xhr });
        return;
      }
      const reader = new FileReader();
      reader.onload = () => reject(new Error(parseErrorDetail(String(reader.result || ""))));
      reader.onerror = () => reject(new Error(`HTTP ${xhr.status}`));
      reader.readAsText(blob);
    };
    xhr.onerror = () => reject(new Error("Сеть: не удалось выполнить запрос."));
    xhr.onabort = () => reject(new Error("Отменено"));
    xhr.send(formData);
  });
}

export function postJsonWithUpload(url, formData, { onUploadProgress, signal } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.responseType = "text";
    if (signal) {
      signal.addEventListener("abort", () => xhr.abort());
    }
    xhr.upload.onprogress = onUploadProgress || (() => {});
    xhr.onload = () => {
      const text = xhr.responseText || "";
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(text));
        } catch (_) {
          reject(new Error("Некорректный ответ сервера"));
        }
        return;
      }
      reject(new Error(parseErrorDetail(text)));
    };
    xhr.onerror = () => reject(new Error("Сеть: не удалось выполнить запрос."));
    xhr.onabort = () => reject(new Error("Отменено"));
    xhr.send(formData);
  });
}

export async function postJson(url, formData, { signal } = {}) {
  const res = await fetch(url, { method: "POST", body: formData, signal });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(parseErrorDetail(text));
  }
  return res.json();
}

export async function fetchJobResult(jobId, signal) {
  const res = await fetch(`/jobs/${jobId}/result`, { signal });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(parseErrorDetail(text));
  }
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") || "";
  const m = cd.match(/filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i);
  let filename = "download.bin";
  try {
    filename = decodeURIComponent((m && (m[1] || m[2])) || filename);
  } catch (_) {
    /* keep */
  }
  return { blob, filename };
}

export async function cancelJob(jobId) {
  try {
    await fetch(`/jobs/${jobId}`, { method: "DELETE" });
  } catch (_) {
    /* ignore */
  }
}

export function setupDropzone(dropzone, inputEl, onFiles) {
  ["dragenter", "dragover"].forEach((ev) => {
    dropzone.addEventListener(ev, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add("dropzone--drag");
    });
  });
  ["dragleave", "drop"].forEach((ev) => {
    dropzone.addEventListener(ev, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove("dropzone--drag");
    });
  });
  dropzone.addEventListener("drop", (e) => {
    const dt = e.dataTransfer;
    if (!dt || !dt.files || !dt.files.length) return;
    if (inputEl && dt.files.length === 1) assignFilesToInput(inputEl, dt.files);
    onFiles(dt.files);
  });
  dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      inputEl.click();
    }
  });
}

export function restoreFormFields(formEl, prefsKey, fieldMap) {
  const prefs = loadPrefs();
  const saved = prefs[prefsKey];
  if (!saved || !formEl) return;
  for (const [id, key] of Object.entries(fieldMap)) {
    const el = $(id);
    if (!el || saved[key] === undefined) continue;
    if (el.type === "checkbox") el.checked = !!saved[key];
    else el.value = saved[key];
  }
}

export function persistFormFields(prefsKey, fieldMap) {
  const data = {};
  for (const [id, key] of Object.entries(fieldMap)) {
    const el = $(id);
    if (!el) continue;
    data[key] = el.type === "checkbox" ? el.checked : el.value;
  }
  savePrefs({ [prefsKey]: data });
}
