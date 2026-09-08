import Console from "./pages/Console";
import Projects from "./pages/Projects";
import { useRoute } from "./router";

export default function App() {
  const pathname = useRoute();

  if (pathname === "/projects") return <Projects />;
  return <Console />;
}
