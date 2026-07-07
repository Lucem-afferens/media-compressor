import { $, loadPrefs, savePrefs } from "./shared.js";

const TAB_ORDER = ["video", "image", "audio", "transcribe"];

export function initTabs() {
  let tabIndex = 0;
  const tabVideo = $("tab-video");
  const tabImage = $("tab-image");
  const tabAudio = $("tab-audio");
  const tabTranscribe = $("tab-transcribe");
  const panelVideo = $("panel-video");
  const panelImage = $("panel-image");
  const panelAudio = $("panel-audio");
  const panelTranscribe = $("panel-transcribe");
  const tablist = tabVideo?.parentElement;
  if (!tabVideo || !tabImage || !tabAudio || !tabTranscribe || !panelVideo || !panelImage || !panelAudio || !panelTranscribe)
    return;

  const tabs = [tabVideo, tabImage, tabAudio, tabTranscribe];
  const panels = [panelVideo, panelImage, panelAudio, panelTranscribe];

  function selectTab(which, persist = true) {
    const idx = TAB_ORDER.indexOf(which);
    if (idx < 0) return;
    tabIndex = idx;
    tabs.forEach((tab, i) => {
      const on = i === idx;
      tab.setAttribute("aria-selected", String(on));
      tab.tabIndex = on ? 0 : -1;
    });
    panels.forEach((panel, i) => {
      panel.hidden = i !== idx;
    });
    if (persist) savePrefs({ activeTab: which });
  }

  tabVideo.addEventListener("click", () => selectTab("video"));
  tabImage.addEventListener("click", () => selectTab("image"));
  tabAudio.addEventListener("click", () => selectTab("audio"));
  tabTranscribe.addEventListener("click", () => selectTab("transcribe"));

  if (tablist) {
    tablist.addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight" || e.key === "ArrowDown") {
        e.preventDefault();
        selectTab(TAB_ORDER[(tabIndex + 1) % TAB_ORDER.length]);
      }
      if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
        e.preventDefault();
        selectTab(TAB_ORDER[(tabIndex - 1 + TAB_ORDER.length) % TAB_ORDER.length]);
      }
      if (e.key === "Home") {
        e.preventDefault();
        selectTab("video");
      }
      if (e.key === "End") {
        e.preventDefault();
        selectTab("transcribe");
      }
    });
  }

  const saved = loadPrefs().activeTab;
  if (saved && TAB_ORDER.includes(saved)) {
    selectTab(saved, false);
  }
}
