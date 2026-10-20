import { useState } from "react";
import { Badge, Box, Card, HStack, Text } from "@chakra-ui/react";
import { LuPlay } from "react-icons/lu";
import { api, formatTime, type SearchHit } from "../api";
import VideoPlayerDialog from "./VideoPlayerDialog";

// A search hit: poster frame at the best match, plus a chip per matched moment that opens the player there.
const ResultCard = ({ hit, rank }: { hit: SearchHit; rank: number }) => {
	const [startAt, setStartAt] = useState<number | null>(null);
	const best = hit.moments[0];

	return (
		<>
			<Card.Root overflow="hidden" size="sm">
				<Box position="relative" bg="black" cursor="pointer" className="group"
					onClick={() => setStartAt(best.start)}
				>
					<img src={api.thumbnailUrl(hit.video_id, best.best_t)} alt="" loading="lazy"
						style={{ width: "100%", aspectRatio: "16 / 9", objectFit: "cover", display: "block" }}
					/>
					<Box position="absolute" inset="0" display="flex" alignItems="center" justifyContent="center"
						bg="blackAlpha.400" opacity="0" _groupHover={{ opacity: 1 }} transition="opacity 0.15s"
					>
						<LuPlay size="40" color="white" />
					</Box>
					<Badge position="absolute" top="2" left="2" variant="solid" colorPalette="gray">#{rank}</Badge>
					<Badge position="absolute" bottom="2" right="2" variant="solid" colorPalette="teal">
						{formatTime(best.best_t)}
					</Badge>
				</Box>
				<Card.Body gap="2">
					<HStack justify="space-between">
						<Text fontWeight="medium" truncate title={hit.filename}>{hit.filename}</Text>
						<Text textStyle="xs" color="fg.muted" fontFamily="mono" flexShrink={0}>
							{hit.score.toFixed(3)}
						</Text>
					</HStack>
					<HStack gap="1.5" wrap="wrap">
						{hit.moments.map((m) => (
							<Badge key={m.start} as="button" variant="outline" cursor="pointer"
								onClick={() => setStartAt(m.start)}
							>
								{formatTime(m.start)}–{formatTime(m.end)}
							</Badge>
						))}
					</HStack>
				</Card.Body>
			</Card.Root>

			<VideoPlayerDialog
				videoId={hit.video_id}
				filename={hit.filename}
				duration={hit.duration}
				moments={hit.moments}
				startAt={startAt ?? 0}
				open={startAt !== null}
				onClose={() => setStartAt(null)}
			/>
		</>
	);
};

export default ResultCard;
