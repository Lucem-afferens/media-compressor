import { loadSettings } from "./settings.js";
import { initTabs } from "./tabs.js";
import { initVideo } from "./video.js";
import { initImage } from "./image.js";
import { initAudio } from "./audio.js";
import { initTranscribe } from "./transcribe.js";

async function main() {
  await loadSettings();
  initTabs();
  initVideo();
  initImage();
  initAudio();
  initTranscribe();
}

main();
