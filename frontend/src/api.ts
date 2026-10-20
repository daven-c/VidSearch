// Typed client for the FastAPI backend. Set VITE_API_URL for deployed builds; dev uses the Vite proxy.
const BASE = import.meta.env.VITE_API_URL ?? "/api";

export interface VideoInfo {
	video_id: string;
	filename: string;
	duration: number;
	num_frames: number;
}

export interface Moment {
	start: number;
	end: number;
	best_t: number;
	score: number;
}

export interface SearchHit {
	video_id: string;
	filename: string;
	duration: number;
	score: number;
	moments: Moment[];
}

export interface SearchResponse {
	query: string;
	took_ms: number;
	hits: SearchHit[];
}

export interface Metrics {
	"R@1": number;
	"R@5": number;
	"R@10": number;
	MdR: number;
	MnR: number;
}

export interface BenchmarkResult {
	file: string;
	benchmark: string;
	model: string;
	vision_backend?: string;
	num_queries?: number;
	metrics?: Record<string, Metrics>;
	latency_ms?: Record<string, { p50: number; p95: number; mean: number }>;
	videos?: number;
	frames?: number;
	env: { device: string; platform: string; git_commit?: string; timestamp?: string };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
	// Fail visibly instead of hanging forever if the backend stops responding
	const res = await fetch(`${BASE}${path}`, { signal: AbortSignal.timeout(30_000), ...init });
	if (!res.ok) {
		const body = await res.json().catch(() => null);
		throw new Error(body?.detail ?? `${res.status} ${res.statusText}`);
	}
	return res.json();
}

export const api = {
	search: (q: string, k = 12) => request<SearchResponse>(`/search?${new URLSearchParams({ q, k: String(k) })}`),
	listVideos: () => request<VideoInfo[]>("/videos"),
	deleteVideo: (id: string) => request<{ deleted: string }>(`/videos/${id}`, { method: "DELETE" }),
	benchmarks: () => request<BenchmarkResult[]>("/benchmarks"),
	videoUrl: (id: string) => `${BASE}/videos/${id}/file`,
	thumbnailUrl: (id: string, t = 1) => `${BASE}/videos/${id}/thumbnail?t=${t.toFixed(1)}`,

	// XHR rather than fetch so upload progress can be reported; indexing happens after the bytes land
	uploadVideo: (file: File, onProgress: (fraction: number) => void) =>
		new Promise<VideoInfo>((resolve, reject) => {
			const xhr = new XMLHttpRequest();
			xhr.open("POST", `${BASE}/videos`);
			xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
			xhr.onload = () => {
				const body = JSON.parse(xhr.responseText || "null");
				if (xhr.status >= 200 && xhr.status < 300) resolve(body);
				else reject(new Error(body?.detail ?? `upload failed (${xhr.status})`));
			};
			xhr.onerror = () => reject(new Error("network error"));
			const form = new FormData();
			form.append("file", file);
			xhr.send(form);
		}),
};

export function formatTime(seconds: number): string {
	const s = Math.max(0, Math.floor(seconds));
	const m = Math.floor(s / 60);
	return `${m}:${String(s % 60).padStart(2, "0")}`;
}
