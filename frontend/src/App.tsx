import path from "path";
import HomePage from "./pages/HomePage";
import { Toaster } from "./components/ui/toaster";

function App() {
	console.log("test");

	return (
		<>
			<HomePage />
			<Toaster />
		</>
	);
}

export default App;
