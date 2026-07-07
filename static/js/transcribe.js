import {
  $,
  fmtBytes,
  escapeHtml,
  assignFilesToInput,
  createStatusHelpers,
  createProgressHelpers,
  bindResultDownload,
  postJsonWithUpload,
  fetchJobResult,
  fetchJobTranscript,
  showTranscriptResult,
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

const TR_FIELDS = {
  "tr-mode": "mode",
  "tr-language": "language",
  "tr-artist": "artist",
  "tr-title": "title",
};

export function initTranscribe() {
  const dropzone = $("tr-dropzone");
  const fileEl = $("tr-file");
  const formEl = $("tr-form");
  const statusEl = $("tr-status");
  const submitEl = $("tr-submit");
  const resetEl = $("tr-reset");
  const kpiEl = $("tr-kpi");
  const kpiNameEl = $("tr-kpiName");
  const kpiSizeEl = $("tr-kpiSize");
  const previewWrap = $("tr-preview-wrap");
  const previewAudio = $("tr-preview-audio");
  const previewVideo = $("tr-preview-video");
  const progressEl = $("tr-progress");
  const progressBar = $("tr-progressBar");
  const phaseEl = $("tr-phase");
  const cancelBtn = $("tr-cancel");
  const resultEl = $("tr-result");
  const geniusWrap = $("tr-genius-wrap");

  if (!dropzone || !fileEl || !formEl) return;

  const { setStatus, hideStatus } = createStatusHelpers(statusEl);
  const { setProgress, showProgress, setAbortController, startJobPoll } = createProgressHelpers(
    progressEl,
    progressBar,
    phaseEl,
    cancelBtn,
  );

  let previewObjectUrl = null;

  restoreFormFields(formEl, "transcribe", TR_FIELDS);

  function syncGeniusFields() {
    const mode = $("tr-mode")?.value;
    if (geniusWrap) geniusWrap.classList.toggle("is-hidden", mode !== "song");
  }

  $("tr-mode")?.addEventListener("change", syncGeniusFields);
  syncGeniusFields();

  function clearPreview() {
    if (previewObjectUrl) {
      URL.revokeObjectURL(previewObjectUrl);
      previewObjectUrl = null;
    }
    previewAudio?.removeAttribute("src");
    previewVideo?.removeAttribute("src");
    previewAudio?.classList.remove("is-hidden");
    previewVideo?.classList.add("is-hidden");
    previewWrap?.classList.add("is-hidden");
  }

  function attachPreview(file) {
    clearPreview();
    if (!file) return;
    previewObjectUrl = URL.createObjectURL(file);
    if (file.type.startsWith("video/")) {
      previewAudio?.classList.add("is-hidden");
      previewVideo?.classList.remove("is-hidden");
      if (previewVideo) previewVideo.src = previewObjectUrl;
    } else {
      previewVideo?.classList.add("is-hidden");
      previewAudio?.classList.remove("is-hidden");
      if (previewAudio) previewAudio.src = previewObjectUrl;
    }
    previewWrap?.classList.remove("is-hidden");
  }

  function onFileChosen(file) {
    if (!file) {
      kpiEl?.classList.add("is-hidden");
      hideStatus();
      clearPreview();
      resultEl?.classList.add("is-hidden");
      return;
    }
    kpiEl?.classList.remove("is-hidden");
    if (kpiNameEl) kpiNameEl.textContent = file.name;
    if (kpiSizeEl) kpiSizeEl.textContent = fmtBytes(file.size);
    attachPreview(file);

    if (file.size > settings.max_upload_bytes) {
      setStatus(
        "err",
        `<strong>Слишком большой файл.</strong> Лимит: <span class="mono">${escapeHtml(settings.max_upload_human)}</span>.`,
      );
      if (submitEl) submitEl.disabled = true;
      return;
    }
    if (submitEl) submitEl.disabled = settings.transcription?.available === false;
    hideStatus();
  }

  fileEl.addEventListener("change", () => onFileChosen(fileEl.files?.[0] || null));
  setupDropzone(dropzone, fileEl, (files) => {
    if (files[0]) {
      assignFilesToInput(fileEl, files);
      onFileChosen(files[0]);
    }
  });

  resetEl?.addEventListener("click", () => {
    formEl.reset();
    kpiEl?.classList.add("is-hidden");
    hideStatus();
    showProgress(false);
    clearPreview();
    fileEl.value = "";
    resultEl?.classList.add("is-hidden");
    syncGeniusFields();
    if (submitEl) submitEl.disabled = settings.transcription?.available === false;
  });

  async function postTranscribeAsync(file, signal) {
    const est = estimateProcessingSec(file.size, "transcribe");
    const qs = new URLSearchParams({
      mode: $("tr-mode")?.value || "auto",
      language: $("tr-language")?.value || "auto",
      async_mode: "true",
    });
    const artist = $("tr-artist")?.value?.trim();
    const title = $("tr-title")?.value?.trim();
    if (artist) qs.set("artist", artist);
    if (title) qs.set("title", title);

    const fd = new FormData();
    fd.append("file", file, file.name);
    const startTime = performance.now();

    const { job_id } = await postJsonWithUpload(`/transcribe?${qs}`, fd, {
      signal,
      onUploadProgress: (e) => {
        if (!e.lengthComputable) {
          phaseEl.textContent = "Загрузка…";
          return;
        }
        const ratio = e.loaded / e.total;
        setCombinedProgress(setProgress, { uploadRatio: ratio });
        phaseEl.textContent = phaseWithEta(`Загрузка ${Math.round(ratio * 100)}%`, est * (1 - ratio) + est * 0.15);
      },
    });

    return new Promise((resolve, reject) => {
      const poll = startJobPoll(job_id, (j) => {
        setCombinedProgress(setProgress, {
          jobPercent: j.percent,
          indeterminate: !j.percent,
        });
        phaseEl.textContent = phaseWithEta(j.message || "Транскрипция", jobEtaSec(j, est));
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
          Promise.all([fetchJobTranscript(job_id, signal), fetchJobResult(job_id, signal)])
            .then(([transcript, fileResult]) =>
              resolve({
                transcript,
                ...fileResult,
                elapsedSec: (performance.now() - startTime) / 1000,
                mediaUrl: previewObjectUrl,
              }),
            )
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
      setStatus(
        "err",
        `<strong>Слишком большой файл.</strong> Лимит: <span class="mono">${escapeHtml(settings.max_upload_human)}</span>.`,
      );
      return;
    }

    persistFormFields("transcribe", TR_FIELDS);
    const ac = new AbortController();
    setAbortController(ac);

    if (submitEl) submitEl.disabled = true;
    if (resetEl) resetEl.disabled = true;
    submitEl?.setAttribute("aria-busy", "true");
    showProgress(true);
    setProgress(4);
    phaseEl.textContent = "Загрузка…";
    hideStatus();
    resultEl?.classList.add("is-hidden");

    try {
      const { transcript, blob, filename, elapsedSec, mediaUrl } = await postTranscribeAsync(f, ac.signal);
      setProgress(100);
      showTranscriptResult(resultEl, { transcript, blob, filename, elapsedSec, mediaUrl });
      bindResultDownload(resultEl, blob, filename);
      setStatus("ok", `<strong>Готово.</strong> ${transcript.segments?.length || 0} сегментов.`);
    } catch (err) {
      const msg = err?.message || "";
      const cancelled = msg === "Отменено" || err?.name === "AbortError";
      if (!cancelled) {
        setStatus("err", `<strong>Ошибка.</strong> <span class="mono">${escapeHtml(msg || "Ошибка")}</span>`);
      } else {
        setStatus(null, "<strong>Отменено.</strong>");
      }
    } finally {
      if (submitEl) submitEl.disabled = settings.transcription?.available === false;
      if (resetEl) resetEl.disabled = false;
      submitEl?.removeAttribute("aria-busy");
      showProgress(false);
    }
  });
}
