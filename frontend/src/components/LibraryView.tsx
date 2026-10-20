import { useMemo, useRef, useState } from "react";
import { Box, Button, Card, HStack, IconButton, Input, SimpleGrid, Stack, Text, VStack } from "@chakra-ui/react";
import { LuTrash2, LuUpload } from "react-icons/lu";
import { api, formatTime, type VideoInfo } from "../api";
import { ProgressBar, ProgressRoot } from "./ui/progress";
import { EmptyState } from "./ui/empty-state";
import { toaster } from "./ui/toaster";

interface Upload {
	name: string;
	progress: number; // 0..1 of bytes sent; indexing starts at 1
}

const PAGE = 48;

const LibraryView = ({ videos, onChange }: { videos: VideoInfo[]; onChange: () => void }) => {
	const inputRef = useRef<HTMLInputElement>(null);
	const [uploads, setUploads] = useState<Upload[]>([]);
	// Libraries can hold thousands of videos, so render a page at a time
	const [shown, setShown] = useState(PAGE);
	const [filter, setFilter] = useState("");
	const filtered = useMemo(() => {
		const f = filter.trim().toLowerCase();
		return f ? videos.filter((v) => v.filename.toLowerCase().includes(f)) : videos;
	}, [videos, filter]);
	const [dragging, setDragging] = useState(false);

	// Upload one at a time: the backend indexes synchronously, so parallel uploads only contend for the GPU
	const handleFiles = async (files: FileList | null) => {
		if (!files?.length) return;
		const list = Array.from(files);
		setUploads((u) => [...u, ...list.map((f) => ({ name: f.name, progress: 0 }))]);
		for (const file of list) {
			const update = (progress: number) =>
				setUploads((u) => u.map((x) => (x.name === file.name ? { ...x, progress } : x)));
			try {
				const info = await api.uploadVideo(file, update);
				toaster.create({ type: "success", title: `Indexed ${info.filename}`, description: `${info.num_frames} frames` });
				onChange();
			} catch (e) {
				toaster.create({ type: "error", title: `Failed: ${file.name}`, description: (e as Error).message });
			} finally {
				setUploads((u) => u.filter((x) => x.name !== file.name));
			}
		}
	};

	const remove = async (v: VideoInfo) => {
		await api.deleteVideo(v.video_id);
		onChange();
	};

	return (
		<Stack gap="6">
			<VStack as="label" borderWidth="2px" borderStyle="dashed" rounded="lg" py="10" gap="2" cursor="pointer"
				borderColor={dragging ? "teal.solid" : "border"} bg={dragging ? "teal.subtle" : undefined}
				onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
				onDragLeave={() => setDragging(false)}
				onDrop={(e) => { e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer.files); }}
			>
				<LuUpload size="28" />
				<Text fontWeight="medium">Drop videos here or click to upload</Text>
				<Text textStyle="sm" color="fg.muted">mp4, mov, mkv, webm · indexed locally with SigLIP 2</Text>
				<input ref={inputRef} type="file" accept="video/*" multiple hidden
					onChange={(e) => { handleFiles(e.target.files); e.target.value = ""; }}
				/>
			</VStack>

			{uploads.map((u) => (
				<Box key={u.name}>
					<HStack justify="space-between" mb="1">
						<Text textStyle="sm" truncate>{u.name}</Text>
						<Text textStyle="sm" color="fg.muted">
							{u.progress < 1 ? `Uploading ${Math.round(u.progress * 100)}%` : "Indexing frames…"}
						</Text>
					</HStack>
					<ProgressRoot value={u.progress < 1 ? u.progress * 100 : null} colorPalette="teal" size="sm">
						<ProgressBar />
					</ProgressRoot>
				</Box>
			))}

			{videos.length === 0 && uploads.length === 0 ? (
				<EmptyState title="No videos yet" description="Uploaded videos are split into frames, embedded, and stored in a local LanceDB index." />
			) : (
				<Stack gap="4">
				<HStack justify="space-between">
					<Input maxW="sm" size="sm" placeholder="Filter by filename" value={filter}
						onChange={(e) => { setFilter(e.target.value); setShown(PAGE); }}
					/>
					<Text textStyle="sm" color="fg.muted">
						{Math.min(shown, filtered.length)} of {filtered.length.toLocaleString()} videos
					</Text>
				</HStack>
				<SimpleGrid columns={{ base: 1, sm: 2, lg: 4 }} gap="4">
					{filtered.slice(0, shown).map((v) => (
						<Card.Root key={v.video_id} size="sm" overflow="hidden">
							<Box bg="black">
								<img src={api.thumbnailUrl(v.video_id, Math.min(v.duration * 0.1, 60))} alt="" loading="lazy"
									style={{ width: "100%", aspectRatio: "16 / 9", objectFit: "cover", display: "block" }}
								/>
							</Box>
							<Card.Body>
								<HStack justify="space-between">
									<Box minW="0">
										<Text fontWeight="medium" truncate title={v.filename}>{v.filename}</Text>
										<Text textStyle="xs" color="fg.muted">
											{formatTime(v.duration)} · {v.num_frames} frames
										</Text>
									</Box>
									<IconButton aria-label="Delete video" variant="ghost" size="sm" onClick={() => remove(v)}>
										<LuTrash2 />
									</IconButton>
								</HStack>
							</Card.Body>
						</Card.Root>
					))}
				</SimpleGrid>
				{shown < filtered.length && (
					<Button variant="outline" alignSelf="center" onClick={() => setShown((s) => s + PAGE)}>
						Show more
					</Button>
				)}
				</Stack>
			)}
		</Stack>
	);
};

export default LibraryView;
