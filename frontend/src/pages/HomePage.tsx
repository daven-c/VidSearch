import { useCallback, useEffect, useState } from "react";
import { Badge, Container, Flex, Heading, HStack, Tabs, Text } from "@chakra-ui/react";
import { LuChartBar, LuLibrary, LuSearch } from "react-icons/lu";
import { api, type VideoInfo } from "../api";
import { ColorModeButton } from "../components/ui/color-mode";
import SearchView from "../components/SearchView";
import LibraryView from "../components/LibraryView";
import BenchmarksView from "../components/BenchmarksView";

const HomePage = () => {
	const [videos, setVideos] = useState<VideoInfo[]>([]);
	const [backendUp, setBackendUp] = useState(true);

	const refresh = useCallback(() => {
		api.listVideos()
			.then((v) => { setVideos(v); setBackendUp(true); })
			.catch(() => setBackendUp(false));
	}, []);

	useEffect(refresh, [refresh]);

	return (
		<Container maxW="6xl" py="8">
			<Flex justify="space-between" align="center" mb="6">
				<HStack gap="3">
					<Heading size="2xl" letterSpacing="tight">VidSearch</Heading>
					<Badge colorPalette="teal" variant="subtle">SigLIP 2 · LanceDB</Badge>
				</HStack>
				<ColorModeButton />
			</Flex>
			<Text color="fg.muted" mb="6">
				Search inside your videos with natural language and jump straight to the matching moment.
			</Text>

			{!backendUp && (
				<Text color="fg.error" mb="4">
					Can't reach the backend. Start it with <code>cd backend && uv run fastapi dev app/main.py</code>.
				</Text>
			)}

			<Tabs.Root defaultValue="search" variant="line" lazyMount>
				<Tabs.List mb="6">
					<Tabs.Trigger value="search"><LuSearch /> Search</Tabs.Trigger>
					<Tabs.Trigger value="library"><LuLibrary /> Library <Badge size="sm">{videos.length}</Badge></Tabs.Trigger>
					<Tabs.Trigger value="benchmarks"><LuChartBar /> Benchmarks</Tabs.Trigger>
				</Tabs.List>
				<Tabs.Content value="search"><SearchView hasVideos={videos.length > 0} /></Tabs.Content>
				<Tabs.Content value="library"><LibraryView videos={videos} onChange={refresh} /></Tabs.Content>
				<Tabs.Content value="benchmarks"><BenchmarksView /></Tabs.Content>
			</Tabs.Root>
		</Container>
	);
};

export default HomePage;
