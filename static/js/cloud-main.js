import { loadSettings } from "./settings.js";
import { initImage } from "./image.js";

async function main() {
  await loadSettings();
  initImage();
}

main();
