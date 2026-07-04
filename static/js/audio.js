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

const AUDIO_FIELDS = {
  "aud-output": "output",
  "aud-bitrate-mode": "bitrateMode",
  "aud-bitrate-k": "bitrateK",
  "aud-vbr-quality": "vbrQuality",
  "aud-sample-rate": "sampleRate",
};

export function initAudio() {
  const dropzone = $("aud-dropzone");
  const fileEl = $("aud-file");
  const formEl = $("aud-form");
  const statusEl = $("aud-status");
  const submitEl = $("aud-submit");
  const resetEl = $("aud-reset");
  const kpiEl = $("aud-kpi");
  const kpiNameEl = $("aud-kpiName");
  const kpiSizeEl = $("aud-kpiSize");
  const previewWrap = $("aud-preview-wrap");
  const previewAudio = $("aud-preview-audio");
  const previewVideo = $("aud-preview-video");
  const progressEl = $("aud-progress");
  const progressBar = $("aud-progressBar");
  const phaseEl = $("aud-phase");
  const cancelBtn = $("aud-cancel");
  const resultEl = $("aud-result");
  const outSel = $("aud-output");
  const modeWrap = $("aud-bitrate-mode-wrap");
  const bitrateWrap = $("aud-bitrate-k-wrap");
  const vbrWrap = $("aud-vbr-wrap");
  const vbrEl = $("aud-vbr-quality");
  const vbrLabel = $("aud-vbr-label");

  if (!dropzone || !fileEl || !formEl) return;

  const { setStatus, hideStatus } = createStatusHelpers(statusEl);
  const { setProgress, showProgress, setAbortController, startJobPoll } = createProgressHelpers(
    progressEl,
    progressBar,
    phaseEl,
    cancelBtn,
  );

  let previewObjectUrl = null;

  restoreFormFields(formEl, "audio", AUDIO_FIELDS);
  if (vbrLabel && vbrEl) vbrLabel.textContent = vbrEl.value;

  function syncAudUi() {
    const o = outSel.value;
    const isMp3 = o === "mp3";
    const isFlac = o === "flac";
    modeWrap.classList.toggle("is-hidden", !isMp3);
    vbrWrap.classList.toggle("is-hidden", !isMp3 || $("aud-bitrate-mode").value !== "vbr");
    const vbr = isMp3 && $("aud-bitrate-mode").value === "vbr";
    bitrateWrap.classList.toggle("is-hidden", vbr || isFlac);
  }

  function markAudPreset(activeId) {
    ["aud-preset-mp4mp3", "aud-preset-podcast", "aud-preset-flac"].forEach((id) => {
      $(id)?.classList.toggle("is-active", id === activeId);
    });
  }

  outSel.addEventListener("change", syncAudUi);
  $("aud-bitrate-mode").addEventListener("change", syncAudUi);
  vbrEl.addEventListener("input", () => {
    vbrLabel.textContent = vbrEl.value;
  });
  syncAudUi();

  function clearPreview() {
    if (previewObjectUrl) {
      URL.revokeObjectURL(previewObjectUrl);
      previewObjectUrl = null;
    }
    previewAudio.removeAttribute("src");
    previewVideo.removeAttribute("src");
    previewAudio.classList.remove("is-hidden");
    previewVideo.classList.add("is-hidden");
    previewWrap.classList.add("is-hidden");
  }

  function attachPreview(file) {
    clearPreview();
    if (!file) return;
    previewObjectUrl = URL.createObjectURL(file);
    if (file.type.startsWith("video/")) {
      previewAudio.classList.add("is-hidden");
      previewVideo.classList.remove("is-hidden");
      previewVideo.src = previewObjectUrl;
    } else {
      previewVideo.classList.add("is-hidden");
      previewAudio.classList.remove("is-hidden");
      previewAudio.src = previewObjectUrl;
    }
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
      setStatus("err", `<strong>Слишком большой файл.</strong> Лимит: <span class="mono">${escapeHtml(settings.max_upload_human)}</span>.`);
      submitEl.disabled = true;
      return;
    }
    submitEl.disabled = settings.audio_optimization.available === false;
    hideStatus();
  }

  fileEl.addEventListener("change", () => onFileChosen(fileEl.files?.[0] || null));
  setupDropzone(dropzone, fileEl, (files) => {
    if (files[0]) {
      assignFilesToInput(fileEl, files);
      onFileChosen(files[0]);
    }
  });

  function applyPreset(p) {
    if (p === "mp4mp3") {
      outSel.value = "mp3";
      $("aud-bitrate-mode").value = "cbr";
      $("aud-bitrate-k").value = "192";
      $("aud-mono").checked = false;
      $("aud-sample-rate").value = "0";
      $("aud-normalize").checked = false;
      markAudPreset("aud-preset-mp4mp3");
    } else if (p === "podcast") {
      outSel.value = "opus";
      $("aud-bitrate-k").value = "96";
      $("aud-mono").checked = true;
      $("aud-sample-rate").value = "48000";
      $("aud-normalize").checked = true;
      markAudPreset("aud-preset-podcast");
    } else if (p === "flac") {
      outSel.value = "flac";
      $("aud-mono").checked = false;
      $("aud-sample-rate").value = "0";
      $("aud-normalize").checked = false;
      markAudPreset("aud-preset-flac");
    }
    syncAudUi();
  }

  $("aud-preset-mp4mp3")?.addEventListener("click", () => applyPreset("mp4mp3"));
  $("aud-preset-podcast")?.addEventListener("click", () => applyPreset("podcast"));
  $("aud-preset-flac")?.addEventListener("click", () => applyPreset("flac"));
  applyPreset("mp4mp3");

  resetEl.addEventListener("click", () => {
    formEl.reset();
    $("aud-strip").checked = true;
    vbrLabel.textContent = vbrEl.value;
    kpiEl.classList.add("is-hidden");
    hideStatus();
    showProgress(false);
    clearPreview();
    fileEl.value = "";
    if (resultEl) resultEl.classList.add("is-hidden");
    syncAudUi();
    applyPreset("mp4mp3");
    submitEl.disabled = settings.audio_optimization.available === false;
  });

  async function postAudioAsync(file, signal) {
    const est = estimateProcessingSec(file.size, "audio");
    const qs = new URLSearchParams({
      output: outSel.value,
      bitrate_mode: $("aud-bitrate-mode").value,
      bitrate_k: $("aud-bitrate-k").value,
      vbr_quality: vbrEl.value,
      mono: $("aud-mono").checked ? "true" : "false",
      sample_rate: $("aud-sample-rate").value,
      normalize: $("aud-normalize").checked ? "true" : "false",
      strip_metadata: $("aud-strip").checked ? "true" : "false",
      async_mode: "true",
    });
    const fd = new FormData();
    fd.append("file", file, file.name);
    const startTime = performance.now();

    const { job_id } = await postJsonWithUpload(`/optimize-audio?${qs}`, fd, {
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
          if (j.phase === "error") {
            reject(new Error(j.error || "Ошибка"));
            return;
          }
          if (j.phase === "cancelled") {
            reject(new Error("Отменено"));
            return;
          }
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
      setStatus("err", "<strong>Выберите файл.</strong>");
      return;
    }
    if (f.size > settings.max_upload_bytes) {
      setStatus("err", `<strong>Слишком большой файл.</strong> Лимит: <span class="mono">${escapeHtml(settings.max_upload_human)}</span>.`);
      return;
    }

    persistFormFields("audio", AUDIO_FIELDS);
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
      const { blob, filename, elapsedSec } = await postAudioAsync(f, ac.signal);
      setProgress(100);

      const outUrl = URL.createObjectURL(blob);
      const isAudio = blob.type.startsWith("audio/");
      const previewHtml = isAudio
        ? `<div class="result-preview"><audio class="preview preview--aud result-preview__media" controls src="${outUrl}"></audio></div>`
        : `<div class="result-preview"><p class="result-preview__label">Файл готов к скачиванию</p></div>`;

      showResultCard(resultEl, { inputBytes: f.size, outputBytes: blob.size, elapsedSec, previewHtml, filename });
      bindResultDownload(resultEl, blob, filename);
      setStatus("ok", `<strong>Готово.</strong> Скачайте результат ниже.`);
    } catch (err) {
      const msg = err?.message || "";
      const cancelled = msg === "Отменено" || err?.name === "AbortError";
      if (!cancelled) {
        setStatus("err", `<strong>Ошибка.</strong> <span class="mono">${escapeHtml(msg || "Ошибка")}</span>`);
      } else {
        setStatus(null, "<strong>Отменено.</strong>");
      }
    } finally {
      submitEl.disabled = settings.audio_optimization.available === false;
      resetEl.disabled = false;
      submitEl.removeAttribute("aria-busy");
      showProgress(false);
    }
  });
}
