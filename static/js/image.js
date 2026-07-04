import {
  $,
  fmtBytes,
  escapeHtml,
  showToast,
  createStatusHelpers,
  createProgressHelpers,
  showResultCard,
  bindResultDownload,
  postBlob,
  setupDropzone,
  restoreFormFields,
  persistFormFields,
  triggerDownload,
  parseFilenameFromResponse,
  estimateProcessingSec,
  setCombinedProgress,
  phaseWithEta,
  startProcessingCountdown,
} from "./shared.js";
import { settings } from "./settings.js";

const IMAGE_FIELDS = {
  "img-output": "output",
  "img-quality": "quality",
  "img-max-side": "maxSide",
  "img-png-strategy": "pngStrategy",
  "img-upscale": "upscale",
};

export function initImage() {
  const dropzone = $("img-dropzone");
  const fileEl = $("img-file");
  const formEl = $("img-form");
  const statusEl = $("img-status");
  const submitEl = $("img-submit");
  const resetEl = $("img-reset");
  const kpiEl = $("img-kpi");
  const kpiCountEl = $("img-kpiCount");
  const kpiTotalEl = $("img-kpiTotal");
  const fileListEl = $("img-file-list");
  const previewWrap = $("img-preview-wrap");
  const previewEl = $("img-preview");
  const progressEl = $("img-progress");
  const progressBar = $("img-progressBar");
  const phaseEl = $("img-phase");
  const cancelBtn = $("img-cancel");
  const resultEl = $("img-result");
  const outSel = $("img-output");
  const pngWrap = $("img-png-strategy-wrap");
  const webpWrap = $("img-webp-lossless-wrap");
  const inpaintFileSel = $("img-inpaint-file");

  if (!dropzone || !fileEl || !formEl || !fileListEl) return;

  const { setStatus, hideStatus } = createStatusHelpers(statusEl);
  const { setProgress, showProgress, setAbortController } = createProgressHelpers(
    progressEl,
    progressBar,
    phaseEl,
    cancelBtn,
  );

  const IMG_EXT = new Set(["jpg", "jpeg", "jfif", "png", "webp", "bmp", "tif", "tiff", "gif"]);
  let imgQueue = [];
  let previewObjectUrl = null;
  let activeAbort = null;

  restoreFormFields(formEl, "image", IMAGE_FIELDS);
  if ($("img-strip")) $("img-strip").checked = loadStripDefault();

  function loadStripDefault() {
    const prefs = JSON.parse(localStorage.getItem("media-compressor-prefs") || "{}");
    return prefs.image?.strip !== false;
  }

  function isImageFile(f) {
    if (!f?.name) return false;
    if (f.type?.startsWith("image/")) return true;
    const dot = f.name.lastIndexOf(".");
    if (dot < 0) return false;
    return IMG_EXT.has(f.name.slice(dot + 1).toLowerCase());
  }

  function fileKey(f) {
    return `${f.name}\0${f.size}\0${f.lastModified}`;
  }

  function maxBatch() {
    const n = settings.image_optimization?.max_batch_files;
    return typeof n === "number" && n > 0 ? n : 40;
  }

  function syncOutputUi() {
    const o = outSel.value;
    pngWrap.classList.toggle("is-hidden", o === "jpeg" || o === "webp");
    webpWrap.classList.toggle("is-hidden", o !== "webp");
  }

  outSel.addEventListener("change", syncOutputUi);
  syncOutputUi();

  function clearPreview() {
    if (previewObjectUrl) {
      URL.revokeObjectURL(previewObjectUrl);
      previewObjectUrl = null;
    }
    previewEl.removeAttribute("src");
    previewWrap.classList.add("is-hidden");
  }

  function attachPreviewFromQueue() {
    clearPreview();
    const file = imgQueue[0];
    if (!file || !isImageFile(file)) return;
    previewObjectUrl = URL.createObjectURL(file);
    previewEl.src = previewObjectUrl;
    previewWrap.classList.remove("is-hidden");
  }

  function updateInpaintSelect() {
    if (!inpaintFileSel) return;
    inpaintFileSel.innerHTML = imgQueue
      .map((f, i) => `<option value="${i}">${escapeHtml(f.name)}</option>`)
      .join("");
  }

  function renderQueue() {
    if (imgQueue.length === 0) {
      kpiEl.classList.add("is-hidden");
      fileListEl.classList.add("is-hidden");
      fileListEl.innerHTML = "";
      kpiCountEl.textContent = "0";
      kpiTotalEl.textContent = "—";
      clearPreview();
      updateInpaintSelect();
      return;
    }

    kpiEl.classList.remove("is-hidden");
    kpiCountEl.textContent = String(imgQueue.length);
    kpiTotalEl.textContent = fmtBytes(imgQueue.reduce((a, f) => a + f.size, 0));

    fileListEl.classList.remove("is-hidden");
    fileListEl.innerHTML = imgQueue
      .map(
        (f, i) =>
          `<li class="img-file-list__item" data-idx="${i}">` +
          `<span class="img-file-list__name mono" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</span>` +
          `<span class="img-file-list__meta">${escapeHtml(fmtBytes(f.size))}</span>` +
          `<button type="button" class="img-file-list__remove" data-rm="${i}" aria-label="Удалить ${escapeHtml(f.name)}">✕</button>` +
          `</li>`,
      )
      .join("");

    attachPreviewFromQueue();
    updateInpaintSelect();
    submitEl.disabled = settings.image_optimization.available === false;
    hideStatus();
  }

  function addFilesFromList(fileList) {
    if (!fileList?.length) return;
    const keys = new Set(imgQueue.map(fileKey));
    let skipped = 0;
    let tooBig = 0;
    let truncated = 0;
    const lim = maxBatch();
    const beforeLen = imgQueue.length;

    for (const f of Array.from(fileList)) {
      if (!isImageFile(f)) {
        skipped += 1;
        continue;
      }
      if (f.size > settings.max_upload_bytes) {
        tooBig += 1;
        continue;
      }
      const k = fileKey(f);
      if (keys.has(k)) continue;
      if (imgQueue.length >= lim) {
        truncated += 1;
        continue;
      }
      keys.add(k);
      imgQueue.push(f);
    }

    fileEl.value = "";
    renderQueue();

    if (truncated > 0) {
      showToast(`Добавлено ${imgQueue.length - beforeLen} файлов. ${truncated} пропущено — лимит ${lim}.`, "warn");
    }
    if (tooBig > 0) {
      setStatus("err", `<strong>Часть файлов пропущена:</strong> больше лимита <span class="mono">${escapeHtml(settings.max_upload_human)}</span> (${tooBig} шт.).`);
    } else if (skipped > 0 && imgQueue.length === 0) {
      setStatus("err", "<strong>Нет подходящих изображений.</strong> Проверьте формат файлов.");
    }
  }

  fileListEl.addEventListener("click", (e) => {
    const t = e.target;
    if (!(t instanceof HTMLElement)) return;
    const rm = t.getAttribute("data-rm");
    if (rm === null) return;
    imgQueue.splice(parseInt(rm, 10), 1);
    renderQueue();
    if (imgQueue.length === 0) hideStatus();
  });

  fileEl.addEventListener("change", () => {
    if (fileEl.files?.length) addFilesFromList(fileEl.files);
  });

  setupDropzone(dropzone, fileEl, (files) => addFilesFromList(files));

  resetEl.addEventListener("click", () => {
    formEl.reset();
    $("img-strip").checked = true;
    imgQueue = [];
    renderQueue();
    hideStatus();
    showProgress(false);
    fileEl.value = "";
    if (resultEl) resultEl.classList.add("is-hidden");
    syncOutputUi();
    submitEl.disabled = settings.image_optimization.available === false;
    resetInpaintEditor();
  });

  function buildQuery() {
    return new URLSearchParams({
      output: $("img-output").value,
      quality: $("img-quality").value,
      max_side: $("img-max-side").value,
      strip_metadata: $("img-strip").checked ? "true" : "false",
      png_strategy: $("img-png-strategy").value,
      webp_lossless: $("img-webp-lossless").checked ? "true" : "false",
      upscale: $("img-upscale")?.value || "none",
    });
  }

  function postWithProgress(url, fd, { totalBytes, fileCount, single }) {
    const kind = single ? "image" : "image-batch";
    const est = estimateProcessingSec(totalBytes, kind, { fileCount });
    let stopCountdown = null;

    const clearCountdown = () => {
      if (stopCountdown) {
        clearInterval(stopCountdown);
        stopCountdown = null;
      }
    };

    return postBlob(url, fd, {
      signal: activeAbort?.signal,
      onUploadProgress: (e) => {
        if (e.lengthComputable) {
          const ratio = e.loaded / e.total;
          setCombinedProgress(setProgress, { uploadRatio: ratio });
          phaseEl.textContent = phaseWithEta(
            `Загрузка ${Math.round(ratio * 100)}%`,
            est * (1 - ratio) + est * 0.2,
          );
        } else {
          phaseEl.textContent = "Загрузка…";
        }
      },
      onUploadComplete: () => {
        setCombinedProgress(setProgress, { indeterminate: true });
        stopCountdown = startProcessingCountdown(phaseEl, est * 0.9, "Оптимизация");
      },
    })
      .then((r) => {
        clearCountdown();
        return r;
      })
      .catch((err) => {
        clearCountdown();
        throw err;
      });
  }

  formEl.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!imgQueue.length) {
      setStatus("err", "<strong>Добавьте хотя бы один файл.</strong>");
      return;
    }
    const lim = maxBatch();
    if (imgQueue.length > lim) {
      setStatus("err", `<strong>Слишком много файлов.</strong> Максимум ${lim} за один запрос.`);
      return;
    }

    persistFormFields("image", IMAGE_FIELDS);
    saveImageStrip();

    const totalIn = imgQueue.reduce((a, f) => a + f.size, 0);
    const batch = imgQueue.slice();
    const single = batch.length === 1;

    activeAbort = new AbortController();
    setAbortController(activeAbort);

    submitEl.disabled = true;
    resetEl.disabled = true;
    submitEl.setAttribute("aria-busy", "true");
    showProgress(true);
    setProgress(4);
    phaseEl.textContent = "Подготовка…";
    hideStatus();
    if (resultEl) resultEl.classList.add("is-hidden");

    const startTime = performance.now();
    const qs = buildQuery();
    const fd = new FormData();
    if (single) {
      fd.append("file", batch[0], batch[0].name);
    } else {
      for (const f of batch) fd.append("files", f, f.name);
    }

    try {
      const url = single ? `/optimize-image?${qs}` : `/optimize-images?${qs}`;
      const { blob, xhr } = await postWithProgress(url, fd, {
        totalBytes: totalIn,
        fileCount: batch.length,
        single,
      });
      setProgress(100);
      const elapsedSec = (performance.now() - startTime) / 1000;
      const filename = parseFilenameFromResponse(xhr);

      if (single) {
        const f = batch[0];
        const inUrl = URL.createObjectURL(f);
        const outUrl = URL.createObjectURL(blob);
        const previewHtml =
          `<div class="result-preview result-preview--compare">` +
          `<div class="result-preview__col"><p class="result-preview__label">Исходник</p><img class="result-preview__media" src="${inUrl}" alt="До"/></div>` +
          `<div class="result-preview__col"><p class="result-preview__label">Результат</p><img class="result-preview__media" src="${outUrl}" alt="После"/></div>` +
          `</div>`;
        showResultCard(resultEl, { inputBytes: f.size, outputBytes: blob.size, elapsedSec, previewHtml, filename });
        bindResultDownload(resultEl, blob, filename);
        setStatus("ok", `<strong>Готово.</strong> Скачайте результат ниже.`);
      } else {
        showResultCard(resultEl, {
          inputBytes: totalIn,
          outputBytes: blob.size,
          elapsedSec,
          previewHtml: `<p class="result-preview__label">ZIP с ${batch.length} файлами</p>`,
          filename,
        });
        bindResultDownload(resultEl, blob, filename);
        setStatus("ok", `<strong>Готово.</strong> Архив с ${batch.length} файлами.`);
      }
    } catch (err) {
      const msg = err?.message || "";
      const cancelled = msg === "Отменено" || err?.name === "AbortError";
      if (!cancelled) {
        setStatus("err", `<strong>Ошибка.</strong> <span class="mono">${escapeHtml(msg)}</span>`);
      } else {
        setStatus(null, "<strong>Отменено.</strong>");
      }
    } finally {
      activeAbort = null;
      submitEl.disabled = settings.image_optimization.available === false;
      resetEl.disabled = false;
      submitEl.removeAttribute("aria-busy");
      showProgress(false);
    }
  });

  function saveImageStrip() {
    try {
      const cur = JSON.parse(localStorage.getItem("media-compressor-prefs") || "{}");
      cur.image = { ...cur.image, strip: $("img-strip").checked };
      localStorage.setItem("media-compressor-prefs", JSON.stringify(cur));
    } catch (_) {
      /* ignore */
    }
  }

  /* Inpaint editor */
  const cvView = $("img-inpaint-view");
  const cvOverlay = $("img-inpaint-overlay");
  const btnInpaintLoad = $("img-inpaint-load");
  const btnInpaintClear = $("img-inpaint-clear");
  const btnInpaintApply = $("img-inpaint-apply");
  const brushSizeEl = $("img-brush-size");
  const inpaintStage = $("img-inpaint-stage");
  const inpaintMethod = $("img-inpaint-method");

  let maskCanvas = null;
  let maskCtx = null;
  let inpaintWorkFile = null;
  let inpaintImgEl = null;

  function evToCanvas(ev, canvas) {
    const r = canvas.getBoundingClientRect();
    const sx = r.width > 0 ? canvas.width / r.width : 1;
    const sy = r.height > 0 ? canvas.height / r.height : 1;
    return { x: (ev.clientX - r.left) * sx, y: (ev.clientY - r.top) * sy };
  }

  function ensureMaskCanvas(w, h) {
    if (!maskCanvas || maskCanvas.width !== w || maskCanvas.height !== h) {
      maskCanvas = document.createElement("canvas");
      maskCanvas.width = w;
      maskCanvas.height = h;
      maskCtx = maskCanvas.getContext("2d");
      maskCtx.fillStyle = "#000";
      maskCtx.fillRect(0, 0, w, h);
    }
  }

  function redrawInpaintOverlay() {
    if (!cvView || !cvOverlay || !inpaintImgEl || !maskCtx || !maskCanvas) return;
    const w = cvView.width;
    const h = cvView.height;
    cvView.getContext("2d").clearRect(0, 0, w, h);
    cvView.getContext("2d").drawImage(inpaintImgEl, 0, 0, w, h);
    const octx = cvOverlay.getContext("2d");
    octx.clearRect(0, 0, w, h);
    const id = maskCtx.getImageData(0, 0, w, h);
    const pix = octx.createImageData(w, h);
    for (let i = 0; i < id.data.length; i += 4) {
      const lum = (id.data[i] + id.data[i + 1] + id.data[i + 2]) / 3;
      if (lum > 40) {
        pix.data[i] = 255;
        pix.data[i + 1] = 80;
        pix.data[i + 2] = 80;
        pix.data[i + 3] = 180;
      }
    }
    octx.putImageData(pix, 0, 0);
  }

  function brushAt(x, y, erase) {
    if (!maskCtx) return;
    const br = Math.max(2, parseInt(brushSizeEl?.value, 10) || 24);
    maskCtx.fillStyle = erase ? "#000" : "#fff";
    maskCtx.beginPath();
    maskCtx.arc(x, y, br / 2, 0, Math.PI * 2);
    maskCtx.fill();
  }

  function brushLine(x0, y0, x1, y1, erase) {
    const br = Math.max(2, parseInt(brushSizeEl?.value, 10) || 24);
    const dist = Math.hypot(x1 - x0, y1 - y0);
    const n = Math.max(1, Math.ceil(dist / Math.max(1, br / 5)));
    for (let i = 0; i <= n; i++) {
      const t = i / n;
      brushAt(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, erase);
    }
    redrawInpaintOverlay();
  }

  function resetInpaintEditor() {
    inpaintWorkFile = null;
    inpaintImgEl = null;
    maskCanvas = null;
    maskCtx = null;
    inpaintStage?.classList.add("is-hidden");
  }

  function layoutInpaintFromFile(file) {
    if (!cvView || !cvOverlay) return;
    const url = URL.createObjectURL(file);
    const im = new Image();
    im.onload = () => {
      URL.revokeObjectURL(url);
      let w = im.naturalWidth;
      let h = im.naturalHeight;
      const maxSide = 1600;
      const m = Math.max(w, h);
      if (m > maxSide) {
        const s = maxSide / m;
        w = Math.round(w * s);
        h = Math.round(h * s);
      }
      cvView.width = w;
      cvView.height = h;
      cvOverlay.width = w;
      cvOverlay.height = h;
      ensureMaskCanvas(w, h);
      inpaintImgEl = im;
      inpaintWorkFile = file;
      redrawInpaintOverlay();
      inpaintStage?.classList.remove("is-hidden");
      setStatus("ok", "<strong>Редактор:</strong> закрасьте область белым. Shift — ластик.");
    };
    im.onerror = () => {
      URL.revokeObjectURL(url);
      setStatus("err", "<strong>Не удалось открыть изображение.</strong>");
    };
    im.src = url;
  }

  btnInpaintLoad?.addEventListener("click", () => {
    const idx = parseInt(inpaintFileSel?.value || "0", 10);
    const f = imgQueue[idx];
    if (!f) {
      setStatus("err", "<strong>Добавьте в список хотя бы одно изображение.</strong>");
      return;
    }
    if (!settings.image_optimization?.inpaint_remove?.available) {
      setStatus("err", "<strong>OpenCV недоступен.</strong>");
      return;
    }
    layoutInpaintFromFile(f);
  });

  btnInpaintClear?.addEventListener("click", () => {
    if (maskCtx && maskCanvas) {
      maskCtx.fillStyle = "#000";
      maskCtx.fillRect(0, 0, maskCanvas.width, maskCanvas.height);
      redrawInpaintOverlay();
    }
  });

  let painting = false;
  let lastBrush = null;
  let eraseMode = false;

  cvOverlay?.addEventListener("pointerdown", (e) => {
    if (!maskCtx || !inpaintWorkFile) return;
    e.preventDefault();
    painting = true;
    eraseMode = e.shiftKey;
    try {
      cvOverlay.setPointerCapture(e.pointerId);
    } catch (_) {}
    const { x, y } = evToCanvas(e, cvOverlay);
    lastBrush = { x, y };
    brushAt(x, y, eraseMode);
    redrawInpaintOverlay();
  });
  cvOverlay?.addEventListener("pointermove", (e) => {
    if (!painting || !maskCtx) return;
    e.preventDefault();
    const { x, y } = evToCanvas(e, cvOverlay);
    if (lastBrush) brushLine(lastBrush.x, lastBrush.y, x, y, eraseMode);
    else {
      brushAt(x, y, eraseMode);
      redrawInpaintOverlay();
    }
    lastBrush = { x, y };
  });
  function endPaint(e) {
    if (!painting) return;
    painting = false;
    lastBrush = null;
    try {
      cvOverlay.releasePointerCapture(e.pointerId);
    } catch (_) {}
  }
  cvOverlay?.addEventListener("pointerup", endPaint);
  cvOverlay?.addEventListener("pointercancel", endPaint);

  btnInpaintApply?.addEventListener("click", () => {
    if (!inpaintWorkFile || !maskCanvas || !maskCtx) {
      setStatus("err", "<strong>Сначала загрузите изображение в редактор и закрасьте маску.</strong>");
      return;
    }
    const method = inpaintMethod?.value || "telea";
    const rawBr = parseInt(brushSizeEl?.value, 10);
    const radius = Math.max(3, Math.min(32, Math.round((Number.isFinite(rawBr) ? rawBr : 24) / 3)));
    const est = estimateProcessingSec(inpaintWorkFile.size, "inpaint");

    maskCanvas.toBlob((blob) => {
      if (!blob) {
        setStatus("err", "<strong>Не удалось сформировать маску.</strong>");
        return;
      }
      const qs = new URLSearchParams({ radius: String(radius), method });
      const fd = new FormData();
      fd.append("file", inpaintWorkFile, inpaintWorkFile.name);
      fd.append("mask", blob, "mask.png");

      activeAbort = new AbortController();
      setAbortController(activeAbort);
      showProgress(true);
      setProgress(2);
      hideStatus();
      btnInpaintApply.disabled = true;

      let stopCountdown = null;
      const clearCountdown = () => {
        if (stopCountdown) {
          clearInterval(stopCountdown);
          stopCountdown = null;
        }
      };

      postBlob(`/inpaint-remove?${qs}`, fd, {
        signal: activeAbort.signal,
        onUploadProgress: (e) => {
          if (e.lengthComputable) {
            const ratio = e.loaded / e.total;
            setCombinedProgress(setProgress, { uploadRatio: ratio });
            phaseEl.textContent = phaseWithEta(`Загрузка ${Math.round(ratio * 100)}%`, est * (1 - ratio));
          }
        },
        onUploadComplete: () => {
          setCombinedProgress(setProgress, { indeterminate: true });
          stopCountdown = startProcessingCountdown(phaseEl, est * 0.85, "Заплатка");
        },
      })
        .then(({ blob: outBlob, xhr }) => {
          setProgress(100);
          const filename = parseFilenameFromResponse(xhr);
          triggerDownload(outBlob, filename);
          setStatus("ok", "<strong>Готово.</strong> Скачан PNG после заплатки.");
        })
        .catch((err) => {
          const msg = err?.message || "";
          const cancelled = msg === "Отменено" || err?.name === "AbortError";
          if (!cancelled) {
            setStatus("err", `<strong>Ошибка.</strong> ${escapeHtml(msg)}`);
          } else {
            setStatus(null, "<strong>Отменено.</strong>");
          }
        })
        .finally(() => {
          clearCountdown();
          activeAbort = null;
          btnInpaintApply.disabled = !settings.image_optimization?.inpaint_remove?.available;
          showProgress(false);
        });
    }, "image/png");
  });
}
