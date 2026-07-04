import { $, loadPrefs, savePrefs } from "./shared.js";

const TAB_ORDER = ["video", "image", "audio"];

export function initTabs() {
  let tabIndex = 0;
  const tabVideo = $("tab-video");
  const tabImage = $("tab-image");
  const tabAudio = $("tab-audio");
  const panelVideo = $("panel-video");
  const panelImage = $("panel-image");
  const panelAudio = $("panel-audio");
  const tablist = tabVideo?.parentElement;
  if (!tabVideo || !tabImage || !tabAudio || !panelVideo || !panelImage || !panelAudio) return;

  const tabs = [tabVideo, tabImage, tabAudio];
  const panels = [panelVideo, panelImage, panelAudio];

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
        selectTab("audio");
      }
    });
  }

  const saved = loadPrefs().activeTab;
  if (saved && TAB_ORDER.includes(saved)) {
    selectTab(saved, false);
  }
}
