"use client";

import { useState } from "react";
import {
	Box,
	Button,
	FormControl,
	FormLabel,
	Input,
	VStack,
	Heading,
	Text,
	Container,
	useToast,
} from "@chakra-ui/react";

export default function LoginPage() {
	const [email, setEmail] = useState("");
	const [password, setPassword] = useState("");
	const toast = useToast();

	const handleSubmit = async (e: React.FormEvent) => {
		e.preventDefault();

		if (!email || !password) {
			toast({
				title: "Error",
				description: "Please fill in all fields",
				status: "error",
				duration: 3000,
				isClosable: true,
			});
			return;
		}

		// Here you would typically call your authentication API
		console.log("Login attempt with:", { email, password });

		// For demonstration purposes, we'll just show a success message
		toast({
			title: "Login Successful",
			description: "This is a demo message",
			status: "success",
			duration: 3000,
			isClosable: true,
		});
	};

	return (
		<Box bg="gray.100" minH="100vh" py={12}>
			<Container maxW="md">
				<Box bg="white" p={8} rounded="md" shadow="md">
					<VStack spacing={4} align="flex-start">
						<Heading>Login</Heading>
						<Text>
							Enter your credentials to access your account
						</Text>
						<form onSubmit={handleSubmit} style={{ width: "100%" }}>
							<VStack spacing={4} align="flex-start" width="100%">
								<FormControl isRequired>
									<FormLabel htmlFor="email">Email</FormLabel>
									<Input
										id="email"
										type="email"
										placeholder="your@email.com"
										value={email}
										onChange={(e) =>
											setEmail(e.target.value)
										}
									/>
								</FormControl>
								<FormControl isRequired>
									<FormLabel htmlFor="password">
										Password
									</FormLabel>
									<Input
										id="password"
										type="password"
										value={password}
										onChange={(e) =>
											setPassword(e.target.value)
										}
									/>
								</FormControl>
								<Button
									type="submit"
									colorScheme="blue"
									width="full"
								>
									Login
								</Button>
							</VStack>
						</form>
					</VStack>
				</Box>
			</Container>
		</Box>
	);
}
