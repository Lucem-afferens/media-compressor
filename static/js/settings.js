import { $, populateSelect } from "./shared.js";

export let settings = {
  max_upload_bytes: 2147483648,
  max_upload_human: "2.00 GB",
  ffmpeg_available: true,
  presets: [],
  codecs: [],
  scale_modes: [],
  image_optimization: {
    available: true,
    max_megapixels: 50,
    max_batch_files: 40,
    output_modes: [],
    png_strategies: [],
    upscale_modes: [],
    inpaint_remove: { available: false },
  },
  audio_optimization: { available: true, outputs: [] },
  transcription: { available: false, modes: [], languages: [] },
};

export async function loadSettings() {
  try {
    const res = await fetch("/api/settings", { headers: { Accept: "application/json" } });
    if (!res.ok) return settings;
    const j = await res.json();
    const imgDefaults = {
      available: true,
      max_megapixels: 50,
      max_batch_files: 40,
      inpaint_remove: { available: false },
    };
    const jo = j.image_optimization || {};
    settings = {
      ...settings,
      ...j,
      image_optimization: {
        ...imgDefaults,
        ...jo,
        inpaint_remove: { ...imgDefaults.inpaint_remove, ...(jo.inpaint_remove || {}) },
      },
      audio_optimization: { ...{ available: true, outputs: [] }, ...(j.audio_optimization || {}) },
      transcription: {
        ...{ available: false, modes: [], languages: [], tier: "degraded" },
        ...(j.transcription || {}),
      },
    };
    applySettingsToDom();
    return settings;
  } catch (_) {
    return settings;
  }
}

function applySettingsToDom() {
  const bf = $("banner-ffmpeg");
  if (bf) bf.classList.toggle("is-hidden", settings.ffmpeg_available !== false);

  const bp = $("banner-pillow");
  if (bp) bp.classList.toggle("is-hidden", settings.image_optimization.available !== false);

  const mp = $("img-mpix-hint");
  if (mp) mp.classList.add("is-hidden");

  const bh = $("img-batch-hint");
  if (bh && settings.image_optimization.max_batch_files) {
    bh.textContent = ` · до ${settings.image_optimization.max_batch_files} шт.`;
  }

  populateSelect($("codec"), settings.codecs);
  populateSelect($("preset"), (settings.presets || []).map((p) => ({ id: p, label: p })));
  populateSelect($("scale"), settings.scale_modes);
  populateSelect($("img-output"), settings.image_optimization.output_modes);
  populateSelect($("img-png-strategy"), settings.image_optimization.png_strategies);
  populateSelect($("img-upscale"), settings.image_optimization.upscale_modes);
  populateSelect($("aud-output"), settings.audio_optimization.outputs);

  const defaults = { codec: "h264", preset: "medium", scale: "none", "img-output": "auto", "img-upscale": "none", "aud-output": "mp3" };
  for (const [id, val] of Object.entries(defaults)) {
    const el = $(id);
    if (el && [...el.options].some((o) => o.value === val)) el.value = val;
  }

  const vSub = $("submit");
  if (vSub) vSub.disabled = settings.ffmpeg_available === false;

  const iSub = $("img-submit");
  if (iSub) iSub.disabled = settings.image_optimization.available === false;

  const aSub = $("aud-submit");
  if (aSub) aSub.disabled = settings.audio_optimization.available === false;

  const trSub = $("tr-submit");
  if (trSub) trSub.disabled = settings.transcription?.available === false;

  const bannerTr = $("banner-transcribe");
  if (bannerTr) bannerTr.classList.toggle("is-hidden", settings.transcription?.available !== false);

  const bannerTrDegraded = $("banner-transcribe-degraded");
  if (bannerTrDegraded) {
    bannerTrDegraded.classList.toggle(
      "is-hidden",
      !settings.transcription?.available || settings.transcription?.tier !== "degraded",
    );
  }

  const bannerGenius = $("banner-genius");
  if (bannerGenius) {
    bannerGenius.classList.toggle(
      "is-hidden",
      !settings.transcription?.available || settings.transcription?.genius_configured,
    );
  }

  const trHint = $("tr-duration-hint");
  if (trHint && settings.transcription?.max_duration_human) {
    trHint.textContent = `До ${settings.transcription.max_duration_human} · MP3, WAV, FLAC… · MP4/MOV/MKV`;
  }

  populateSelect($("tr-mode"), settings.transcription?.modes || []);
  populateSelect($("tr-language"), settings.transcription?.languages || []);

  const bit = $("banner-img-tools");
  if (bit) {
    const ip = settings.image_optimization.inpaint_remove?.available;
    bit.classList.toggle("is-hidden", !!ip);
  }

  const okInpaint = settings.image_optimization?.inpaint_remove?.available;
  ["img-inpaint-apply", "img-inpaint-load", "img-inpaint-clear"].forEach((id) => {
    const el = $(id);
    if (el) el.disabled = !okInpaint;
  });
}

export function applySettingsUi() {
  applySettingsToDom();
}
