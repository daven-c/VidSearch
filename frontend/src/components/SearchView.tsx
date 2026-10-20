import { useState } from "react";
import { Box, Button, HStack, Input, SimpleGrid, Spinner, Text } from "@chakra-ui/react";
import { LuSearch } from "react-icons/lu";
import { api, type SearchResponse } from "../api";
import { EmptyState } from "./ui/empty-state";
import ResultCard from "./ResultCard";

const EXAMPLES = ["a dog catching a frisbee", "someone cooking in a kitchen", "crowd cheering at a concert"];

const SearchView = ({ hasVideos }: { hasVideos: boolean }) => {
	const [query, setQuery] = useState("");
	const [result, setResult] = useState<SearchResponse | null>(null);
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);

	const run = async (q: string) => {
		if (!q.trim()) return;
		setQuery(q);
		setLoading(true);
		setError(null);
		try {
			setResult(await api.search(q.trim()));
		} catch (e) {
			setError((e as Error).message);
		} finally {
			setLoading(false);
		}
	};

	return (
		<Box>
			<form onSubmit={(e) => { e.preventDefault(); run(query); }}>
				<HStack>
					<Input size="lg" placeholder="Describe what happens in the scene…" value={query}
						onChange={(e) => setQuery(e.target.value)} autoFocus
					/>
					<Button size="lg" type="submit" colorPalette="teal" loading={loading}>
						<LuSearch /> Search
					</Button>
				</HStack>
			</form>

			{!result && !loading && (
				<HStack mt="3" gap="2" wrap="wrap">
					<Text textStyle="sm" color="fg.muted">Try:</Text>
					{EXAMPLES.map((ex) => (
						<Button key={ex} size="xs" variant="subtle" onClick={() => run(ex)}>{ex}</Button>
					))}
				</HStack>
			)}

			{error && <Text mt="4" color="fg.error">{error}</Text>}

			{loading && !result && <Spinner mt="8" mx="auto" display="block" />}

			{result && (
				<Box mt="6">
					<Text textStyle="sm" color="fg.muted" mb="3">
						{result.hits.length} videos · {result.took_ms.toFixed(0)} ms
					</Text>
					{result.hits.length === 0 ? (
						<EmptyState
							title={hasVideos ? "No matches" : "Your library is empty"}
							description={hasVideos ? "Try describing the scene differently." : "Upload a video in the Library tab first."}
						/>
					) : (
						<SimpleGrid columns={{ base: 1, sm: 2, lg: 3 }} gap="4">
							{result.hits.map((hit, i) => <ResultCard key={hit.video_id} hit={hit} rank={i + 1} />)}
						</SimpleGrid>
					)}
				</Box>
			)}
		</Box>
	);
};

export default SearchView;
