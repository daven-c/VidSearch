import { useEffect, useState } from "react";
import { Box, Code, Heading, Stack, Table, Text } from "@chakra-ui/react";
import { api, type BenchmarkResult } from "../api";
import { EmptyState } from "./ui/empty-state";

const PROTOCOL_LABELS: Record<string, string> = {
	t2v_mean_pool: "Text → video (mean-pooled frames)",
	t2v_max_frame: "Text → video (best frame)",
	v2t_mean_pool: "Video → text (mean-pooled frames)",
};

// Renders eval/results/*.json as committed in the repo, with the command that reproduces each number.
const BenchmarksView = () => {
	const [results, setResults] = useState<BenchmarkResult[] | null>(null);
	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		api.benchmarks().then(setResults).catch((e) => setError(e.message));
	}, []);

	if (error) return <Text color="fg.error">{error}</Text>;
	if (!results) return null;
	if (results.length === 0)
		return <EmptyState title="No results yet" description="Run `uv run python -m eval.msrvtt` in backend/." />;

	const retrieval = results.filter((r) => r.metrics);
	const latency = results.filter((r) => r.latency_ms);

	return (
		<Stack gap="10">
			{retrieval.map((r) => (
				<Box key={r.file}>
					<Heading size="md">{r.benchmark}</Heading>
					<Text textStyle="sm" color="fg.muted" mt="1">
						{r.model} · {r.num_queries} queries · {r.env.device} · commit {r.env.git_commit}
					</Text>
					<Table.Root size="sm" mt="3" variant="outline">
						<Table.Header>
							<Table.Row>
								<Table.ColumnHeader>Protocol</Table.ColumnHeader>
								{["R@1", "R@5", "R@10", "MdR", "MnR"].map((h) => (
									<Table.ColumnHeader key={h} textAlign="end">{h}</Table.ColumnHeader>
								))}
							</Table.Row>
						</Table.Header>
						<Table.Body>
							{Object.entries(r.metrics!).map(([name, m]) => (
								<Table.Row key={name}>
									<Table.Cell>{PROTOCOL_LABELS[name] ?? name}</Table.Cell>
									<Table.Cell textAlign="end" fontWeight="semibold">{m["R@1"].toFixed(1)}</Table.Cell>
									<Table.Cell textAlign="end">{m["R@5"].toFixed(1)}</Table.Cell>
									<Table.Cell textAlign="end">{m["R@10"].toFixed(1)}</Table.Cell>
									<Table.Cell textAlign="end">{m.MdR.toFixed(0)}</Table.Cell>
									<Table.Cell textAlign="end">{m.MnR.toFixed(1)}</Table.Cell>
								</Table.Row>
							))}
						</Table.Body>
					</Table.Root>
					<Text textStyle="xs" color="fg.muted" mt="2">
						Reproduce: <Code size="sm">cd backend && uv run python -m eval.msrvtt</Code> → <Code size="sm">eval/results/{r.file}</Code>
					</Text>
				</Box>
			))}

			{latency.map((r) => (
				<Box key={r.file}>
					<Heading size="md">Search latency</Heading>
					<Text textStyle="sm" color="fg.muted" mt="1">
						{r.videos} videos / {r.frames} frames · {r.env.device}
					</Text>
					<Table.Root size="sm" mt="3" variant="outline">
						<Table.Header>
							<Table.Row>
								<Table.ColumnHeader>Stage</Table.ColumnHeader>
								<Table.ColumnHeader textAlign="end">p50 (ms)</Table.ColumnHeader>
								<Table.ColumnHeader textAlign="end">p95 (ms)</Table.ColumnHeader>
							</Table.Row>
						</Table.Header>
						<Table.Body>
							{Object.entries(r.latency_ms!).map(([stage, v]) => (
								<Table.Row key={stage}>
									<Table.Cell>{stage.replace(/_/g, " ")}</Table.Cell>
									<Table.Cell textAlign="end">{v.p50.toFixed(1)}</Table.Cell>
									<Table.Cell textAlign="end">{v.p95.toFixed(1)}</Table.Cell>
								</Table.Row>
							))}
						</Table.Body>
					</Table.Root>
					<Text textStyle="xs" color="fg.muted" mt="2">
						Reproduce: <Code size="sm">cd backend && uv run python -m eval.latency</Code>
					</Text>
				</Box>
			))}
		</Stack>
	);
};

export default BenchmarksView;
