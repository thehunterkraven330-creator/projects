// Adds the privacy texts iOS requires to the project that `npx cap add ios` generated. Without them the camera and
// microphone are refused (Go live shows a blank screen) and App Review rejects the app. Safe to run again.
// Usage (from lumin-native/):  node scripts/apply-ios.mjs [path-to-ios-folder]
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const target = process.argv[2] ? path.resolve(process.argv[2]) : path.join(root, 'ios');
const plistPath = path.join(target, 'App', 'App', 'Info.plist');
if (!fs.existsSync(plistPath)) {
  console.error(`✗ No iOS project at ${target}. Run "npx cap add ios" first.`);
  process.exit(1);
}

const TEXTS = {
  NSCameraUsageDescription: 'Lumin uses the camera to record product tests, go live and check deliveries.',
  NSMicrophoneUsageDescription: 'Lumin uses the microphone to record sound for product tests and live shopping.',
  NSPhotoLibraryUsageDescription: 'Lumin lets you pick photos and videos from your library to show a product.',
  NSPhotoLibraryAddUsageDescription: 'Lumin saves videos you download to your photo library.',
};

let plist = fs.readFileSync(plistPath, 'utf8');
const added = [];
for (const [key, text] of Object.entries(TEXTS)) {
  if (plist.includes(`<key>${key}</key>`)) continue;
  plist = plist.replace(/<\/dict>\s*<\/plist>\s*$/, `\t<key>${key}</key>\n\t<string>${text}</string>\n</dict>\n</plist>\n`);
  added.push(key);
}
if (added.length) fs.writeFileSync(plistPath, plist);
console.log(added.length ? `✓ Added to Info.plist: ${added.join(', ')}` : '✓ Info.plist already has the privacy texts');
