import Console from "./pages/Console";
import Projects from "./pages/Projects";
import { useRoute } from "./router";

export default function App() {
  const pathname = useRoute();

  if (pathname === "/day/14") return <Console />;
  return <Projects />;
}
