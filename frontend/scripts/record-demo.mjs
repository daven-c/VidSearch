// Records the README demo by driving the real app in Chrome.
//
//   1. Index the demo films:   see docs/DEMO.md
//   2. Run backend + frontend: the frontend at DEMO_URL must proxy to the demo backend
//   3. node scripts/record-demo.mjs        -> ../docs/demo.webm (converted to GIF/MP4 by docs/DEMO.md)
//
// Uses the installed Google Chrome (channel "chrome") because Playwright's bundled Chromium has no
// H.264 decoder. Playwright doesn't record the mouse pointer, so a fake cursor and a caption bar are
// injected into the page to make each step readable.

import { chromium } from "playwright";
import { mkdir, rename, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const URL = process.env.DEMO_URL ?? "http://localhost:5173";
const OUT_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../docs");
const SIZE = { width: 1280, height: 720 };

const QUERIES = [
	{ q: "a girl holding a baby dragon", caption: "Describe a scene in plain English to search 48 minutes of film" },
	{ q: "a giant rabbit in a forest", caption: "Results jump straight to the matching moment, not just the video" },
	{ q: "two old men in a strange machine", caption: "Every matched time range is marked on the timeline" },
];

const overlay = () => {
	const style = document.createElement("style");
	style.textContent = `
		#demo-cursor { position: fixed; z-index: 99999; width: 18px; height: 18px; margin: -9px 0 0 -9px;
			border-radius: 50%; background: rgba(255,255,255,.85); box-shadow: 0 0 0 2px rgba(20,184,166,.9);
			pointer-events: none; transition: transform .12s; left: -50px; top: -50px; }
		#demo-cursor.down { transform: scale(.7); }
		#demo-caption { position: fixed; z-index: 99998; left: 50%; bottom: 28px; transform: translateX(-50%);
			max-width: 80%; padding: 10px 18px; border-radius: 10px; background: rgba(15,23,42,.88); color: #fff;
			font: 500 17px/1.35 system-ui, sans-serif; text-align: center; opacity: 0; transition: opacity .3s;
			pointer-events: none; }`;
	const cursor = Object.assign(document.createElement("div"), { id: "demo-cursor" });
	const caption = Object.assign(document.createElement("div"), { id: "demo-caption" });
	const mount = () => document.body.append(style, cursor, caption);
	document.body ? mount() : addEventListener("DOMContentLoaded", mount);
	addEventListener("mousemove", (e) => { cursor.style.left = `${e.clientX}px`; cursor.style.top = `${e.clientY}px`; }, true);
	addEventListener("mousedown", () => cursor.classList.add("down"), true);
	addEventListener("mouseup", () => cursor.classList.remove("down"), true);
	window.__caption = (text) => {
		caption.textContent = text ?? "";
		caption.style.opacity = text ? "1" : "0";
	};
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function glideTo(page, locator) {
	const box = await locator.boundingBox();
	if (!box) throw new Error("element not visible");
	await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 25 });
}

// Click with the real mouse at the element's centre, like a person would, so overlays on top of
// the target (e.g. the play icon on result cards) receive the click and bubble it as usual.
async function click(page, locator) {
	await glideTo(page, locator);
	await sleep(250);
	await page.mouse.down();
	await sleep(80);
	await page.mouse.up();
}

const caption = (page, text) => page.evaluate((t) => window.__caption(t), text);

// Run each query once and fetch its thumbnails so the backend's thumbnail cache is warm; otherwise
// the first frames after each search show empty cards while long films are seeked and decoded.
async function warmUp() {
	const get = (p) => fetch(`${URL}/api${p}`).then((r) => {
		if (!r.ok) throw new Error(`${p}: ${r.status}`);
		return r;
	});
	const fmt = (t) => t.toFixed(1);
	for (const { q } of QUERIES) {
		const { hits } = await (await get(`/search?${new URLSearchParams({ q, k: "12" })}`)).json();
		await Promise.all(hits.map((h) => get(`/videos/${h.video_id}/thumbnail?t=${fmt(h.moments[0].best_t)}`)));
	}
	const videos = await (await get("/videos")).json();
	await Promise.all(videos.map((v) => get(`/videos/${v.video_id}/thumbnail?t=${fmt(Math.min(v.duration * 0.1, 60))}`)));
}

async function main() {
	await mkdir(OUT_DIR, { recursive: true });
	await warmUp();
	const browser = await chromium.launch({ channel: "chrome", args: ["--autoplay-policy=no-user-gesture-required"] });
	const context = await browser.newContext({
		viewport: SIZE,
		colorScheme: "dark",
		recordVideo: { dir: OUT_DIR, size: SIZE },
	});
	await context.addInitScript(overlay);
	const page = await context.newPage();
	const video = page.video();

	await page.goto(URL);
	await page.getByPlaceholder("Describe what happens in the scene…").waitFor();
	await page.mouse.move(640, 500);
	await caption(page, "VidSearch: natural-language search inside videos, running locally");
	await sleep(2500);

	const input = page.getByPlaceholder("Describe what happens in the scene…");
	for (const [i, { q, caption: text }] of QUERIES.entries()) {
		await caption(page, text);
		await click(page, input);
		await input.fill("");
		await input.pressSequentially(q, { delay: 55 });
		await sleep(300);
		await page.keyboard.press("Enter");

		// wait for this query's results and their thumbnails
		await page.getByText(/videos · \d+ ms/).waitFor();
		await page.waitForFunction(() => [...document.querySelectorAll("img")].every((im) => im.complete));
		await sleep(1600);

		// open the top hit: the player starts at the matched moment
		const top = page.locator("img").first();
		await click(page, top);
		const dialog = page.getByRole("dialog");
		await dialog.waitFor();
		await sleep(i === 2 ? 2500 : 4000);

		if (i === 2) {
			// jump between matched moments using the chips under the timeline
			const chips = dialog.getByRole("button", { name: /^#\d/ });
			if ((await chips.count()) > 1) {
				await click(page, chips.nth(1));
				await sleep(2500);
				await click(page, chips.nth(0));
				await sleep(2500);
			}
		}
		await page.keyboard.press("Escape");
		await dialog.waitFor({ state: "hidden" });
		await sleep(600);
	}

	await caption(page, "Indexed on the Apple Neural Engine: ~4x faster than the GPU path");
	await click(page, page.getByRole("tab", { name: /Library/ }));
	await sleep(3200);

	await caption(page, "Reproducible benchmarks: MSR-VTT 1k-A, R@1 39.8 vs 30.5 for CLIP");
	await click(page, page.getByRole("tab", { name: /Benchmarks/ }));
	await sleep(4500);
	await caption(page, null);
	await sleep(500);

	await context.close();
	await browser.close();
	const out = path.join(OUT_DIR, "demo.webm");
	await rm(out, { force: true });
	await rename(await video.path(), out);
	console.log(`recorded ${out}`);
}

main().catch((e) => {
	console.error(e);
	process.exit(1);
});
