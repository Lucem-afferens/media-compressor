import {
  $,
  fmtBytes,
  escapeHtml,
  assignFilesToInput,
  createStatusHelpers,
  createProgressHelpers,
  showResultCard,
  bindResultDownload,
  postJsonWithUpload,
  fetchJobResult,
  cancelJob,
  setupDropzone,
  restoreFormFields,
  persistFormFields,
  estimateProcessingSec,
  setCombinedProgress,
  phaseWithEta,
  jobEtaSec,
} from "./shared.js";
import { settings } from "./settings.js";

const VIDEO_FIELDS = {
  codec: "codec",
  preset: "preset",
  audio: "audio",
  scale: "scale",
  crf: "crf",
};

const VIDEO_PRESET_HINTS = {
  balance: "Баланс качества и размера — подходит для большинства роликов.",
  messenger: "Меньший файл и 720p — удобно для Telegram, WhatsApp и почты.",
  max: "Максимальное сжатие (H.265, 1080p) — дольше кодируется, файл легче.",
};

function updateVideoPresetHint(p) {
  const el = $("video-preset-hint");
  if (el) el.textContent = VIDEO_PRESET_HINTS[p] || "";
}

function applyVideoPreset(p) {
  const crfValEl = $("crfVal");
  if (p === "messenger") {
    $("codec").value = "h264";
    $("preset").value = "veryfast";
    $("crf").value = "28";
    if (crfValEl) crfValEl.textContent = "28";
    $("scale").value = "720";
    $("audio").value = "96";
  } else if (p === "balance") {
    $("codec").value = "h264";
    $("preset").value = "medium";
    $("crf").value = "23";
    if (crfValEl) crfValEl.textContent = "23";
    $("scale").value = "none";
    $("audio").value = "128";
  } else if (p === "max") {
    $("codec").value = "h265";
    $("preset").value = "slow";
    $("crf").value = "30";
    if (crfValEl) crfValEl.textContent = "30";
    $("scale").value = "1080";
    $("audio").value = "128";
  }
  document.querySelectorAll("[data-video-preset]").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.videoPreset === p);
  });
  updateVideoPresetHint(p);
}

export function initVideo() {
  const dropzone = $("dropzone");
  const fileEl = $("file");
  const formEl = $("form");
  const statusEl = $("status");
  const submitEl = $("submit");
  const resetEl = $("reset");
  const crfEl = $("crf");
  const crfValEl = $("crfVal");
  const kpiEl = $("kpi");
  const kpiNameEl = $("kpiName");
  const kpiSizeEl = $("kpiSize");
  const previewWrap = $("preview-wrap");
  const previewEl = $("preview");
  const progressEl = $("progress");
  const progressBar = $("progressBar");
  const phaseEl = $("phase");
  const cancelBtn = $("video-cancel");
  const resultEl = $("video-result");

  if (!dropzone || !fileEl || !formEl) return;

  const { setStatus, hideStatus } = createStatusHelpers(statusEl);
  const { setProgress, showProgress, setAbortController, startJobPoll } = createProgressHelpers(
    progressEl,
    progressBar,
    phaseEl,
    cancelBtn,
  );

  let previewObjectUrl = null;

  restoreFormFields(formEl, "video", VIDEO_FIELDS);
  if (crfValEl && crfEl) crfValEl.textContent = crfEl.value;
  applyVideoPreset("balance");

  function clearPreview() {
    if (previewObjectUrl) {
      URL.revokeObjectURL(previewObjectUrl);
      previewObjectUrl = null;
    }
    previewEl.removeAttribute("src");
    previewWrap.classList.add("is-hidden");
  }

  function attachPreview(file) {
    clearPreview();
    if (!file || !file.type.startsWith("video/")) return;
    previewObjectUrl = URL.createObjectURL(file);
    previewEl.src = previewObjectUrl;
    previewWrap.classList.remove("is-hidden");
  }

  function onFileChosen(file) {
    if (!file) {
      kpiEl.classList.add("is-hidden");
      hideStatus();
      clearPreview();
      if (resultEl) resultEl.classList.add("is-hidden");
      return;
    }
    kpiEl.classList.remove("is-hidden");
    kpiNameEl.textContent = file.name;
    kpiSizeEl.textContent = fmtBytes(file.size);
    attachPreview(file);

    if (file.size > settings.max_upload_bytes) {
      setStatus("err", `<strong>Слишком большой файл.</strong> Лимит ${escapeHtml(settings.max_upload_human)}.`);
      submitEl.disabled = true;
      return;
    }
    submitEl.disabled = settings.ffmpeg_available === false;
    hideStatus();
  }

  crfEl?.addEventListener("input", () => {
    crfValEl.textContent = crfEl.value;
    crfEl.setAttribute("aria-valuetext", crfEl.value);
  });

  fileEl.addEventListener("change", () => onFileChosen(fileEl.files?.[0] || null));

  setupDropzone(dropzone, fileEl, (files) => {
    if (files[0]) {
      assignFilesToInput(fileEl, files);
      onFileChosen(files[0]);
    }
  });

  document.querySelectorAll("[data-video-preset]").forEach((btn) => {
    btn.addEventListener("click", () => applyVideoPreset(btn.dataset.videoPreset));
  });

  resetEl.addEventListener("click", () => {
    formEl.reset();
    kpiEl.classList.add("is-hidden");
    hideStatus();
    showProgress(false);
    clearPreview();
    fileEl.value = "";
    if (resultEl) resultEl.classList.add("is-hidden");
    submitEl.disabled = settings.ffmpeg_available === false;
    applyVideoPreset("balance");
  });

  async function postCompressAsync(file, signal) {
    const preset = $("preset").value;
    const est = estimateProcessingSec(file.size, "video", { preset });
    const qs = new URLSearchParams({
      codec: $("codec").value,
      preset,
      crf: crfEl.value,
      audio_bitrate_k: $("audio").value,
      scale: $("scale").value,
      async_mode: "true",
    });
    const fd = new FormData();
    fd.append("file", file, file.name);
    const startTime = performance.now();

    const { job_id } = await postJsonWithUpload(`/compress?${qs}`, fd, {
      signal,
      onUploadProgress: (e) => {
        if (!e.lengthComputable) {
          phaseEl.textContent = "Загрузка…";
          return;
        }
        const ratio = e.loaded / e.total;
        setCombinedProgress(setProgress, { uploadRatio: ratio });
        phaseEl.textContent = phaseWithEta(
          `Загрузка ${Math.round(ratio * 100)}%`,
          est * (1 - ratio) + est * 0.15,
        );
      },
    });

    return new Promise((resolve, reject) => {
      const poll = startJobPoll(job_id, (j) => {
        setCombinedProgress(setProgress, {
          jobPercent: j.percent,
          indeterminate: !j.percent,
        });
        phaseEl.textContent = phaseWithEta(j.message || "Кодирование", jobEtaSec(j, est));
        if (j.done) {
          clearInterval(poll);
          if (j.phase === "error") reject(new Error(j.error || "Ошибка кодирования"));
          else if (j.phase === "cancelled") reject(new Error("Отменено"));
          else
            fetchJobResult(job_id, signal)
              .then((r) => resolve({ ...r, elapsedSec: (performance.now() - startTime) / 1000 }))
              .catch(reject);
        }
      });
      signal.addEventListener("abort", () => {
        clearInterval(poll);
        cancelJob(job_id);
      });
    });
  }

  formEl.addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = fileEl.files?.[0];
    if (!f) {
      setStatus("err", "<strong>Выберите видеофайл.</strong>");
      return;
    }
    if (f.size > settings.max_upload_bytes) {
      setStatus("err", `<strong>Слишком большой файл.</strong> Лимит ${escapeHtml(settings.max_upload_human)}.`);
      return;
    }

    persistFormFields("video", VIDEO_FIELDS);
    const ac = new AbortController();
    setAbortController(ac);

    submitEl.disabled = true;
    resetEl.disabled = true;
    submitEl.setAttribute("aria-busy", "true");
    showProgress(true);
    setProgress(4);
    phaseEl.textContent = "Загрузка…";
    hideStatus();
    if (resultEl) resultEl.classList.add("is-hidden");

    try {
      const { blob, filename, elapsedSec } = await postCompressAsync(f, ac.signal);
      setProgress(100);
      const outUrl = URL.createObjectURL(blob);
      const previewHtml =
        `<div class="result-preview"><video class="preview result-preview__media" controls playsinline src="${outUrl}"></video></div>`;
      showResultCard(resultEl, { inputBytes: f.size, outputBytes: blob.size, elapsedSec, previewHtml, filename });
      bindResultDownload(resultEl, blob, filename);
      const savings = (1 - blob.size / f.size) * 100;
      setStatus("ok", `<strong>Готово.</strong> Минус ${savings.toFixed(0)}% — скачайте ниже.`);
    } catch (err) {
      const msg = err?.message || "";
      const cancelled = msg === "Отменено" || err?.name === "AbortError";
      setStatus(cancelled ? null : "err", cancelled ? "<strong>Отменено.</strong>" : `<strong>Ошибка.</strong> ${escapeHtml(msg)}`);
    } finally {
      submitEl.disabled = settings.ffmpeg_available === false;
      resetEl.disabled = false;
      submitEl.removeAttribute("aria-busy");
      showProgress(false);
    }
  });
}
