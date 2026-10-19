import { useEffect, useRef, useState } from "react";
import { Box, Flex, HStack, Text } from "@chakra-ui/react";
import {
	DialogBody,
	DialogCloseTrigger,
	DialogContent,
	DialogHeader,
	DialogRoot,
	DialogTitle,
} from "./ui/dialog";
import { api, formatTime, type Moment } from "../api";

interface Props {
	videoId: string;
	filename: string;
	duration: number;
	moments: Moment[];
	startAt: number;
	open: boolean;
	onClose: () => void;
}

// Plays a video starting at a matched moment and marks every matched range on a timeline under it.
const VideoPlayerDialog = ({ videoId, filename, duration, moments, startAt, open, onClose }: Props) => {
	const videoRef = useRef<HTMLVideoElement>(null);
	const [current, setCurrent] = useState(startAt);
	const total = duration || 1;

	useEffect(() => {
		const v = videoRef.current;
		if (open && v) {
			v.currentTime = startAt;
			v.play().catch(() => {});
		}
	}, [open, startAt]);

	const seek = (t: number) => {
		if (videoRef.current) videoRef.current.currentTime = t;
	};

	return (
		<DialogRoot open={open} onOpenChange={(e) => !e.open && onClose()} size="xl" placement="center" lazyMount>
			<DialogContent>
				<DialogHeader>
					<DialogTitle truncate>{filename}</DialogTitle>
				</DialogHeader>
				<DialogBody pb="6">
					<Box bg="black" rounded="md" overflow="hidden">
						<video
							ref={videoRef}
							src={api.videoUrl(videoId)}
							controls
							style={{ width: "100%", maxHeight: "60vh" }}
							onLoadedMetadata={(e) => (e.currentTarget.currentTime = startAt)}
							onTimeUpdate={(e) => setCurrent(e.currentTarget.currentTime)}
						/>
					</Box>

					<Box position="relative" h="3" mt="4" bg="bg.muted" rounded="full" cursor="pointer"
						onClick={(e) => {
							const r = e.currentTarget.getBoundingClientRect();
							seek(((e.clientX - r.left) / r.width) * total);
						}}
					>
						{moments.map((m) => (
							<Box key={m.start} position="absolute" top="0" h="full" bg="teal.solid" rounded="full"
								left={`${(m.start / total) * 100}%`}
								width={`${Math.max(1, ((m.end - m.start) / total) * 100)}%`}
							/>
						))}
						<Box position="absolute" top="-1" h="5" w="0.5" bg="fg" left={`${(current / total) * 100}%`} />
					</Box>

					<HStack mt="3" gap="2" wrap="wrap">
						<Text textStyle="sm" color="fg.muted">Matches:</Text>
						{moments.map((m, i) => (
							<Flex key={m.start} as="button" onClick={() => seek(m.start)} px="2" py="0.5" rounded="md"
								borderWidth="1px" textStyle="sm" _hover={{ bg: "bg.muted" }}
							>
								#{i + 1} {formatTime(m.start)}–{formatTime(m.end)}
							</Flex>
						))}
					</HStack>
				</DialogBody>
				<DialogCloseTrigger />
			</DialogContent>
		</DialogRoot>
	);
};

export default VideoPlayerDialog;
