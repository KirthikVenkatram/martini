import { useEffect, useState } from "react";

const _listeners = new Set<() => void>();

export function navigate(path: string): void {
  if (path === window.location.pathname) return;
  window.history.pushState({}, "", path);
  _listeners.forEach((listener) => listener());
}

export function useRoute(): string {
  const [pathname, setPathname] = useState(window.location.pathname);

  useEffect(() => {
    const onChange = () => setPathname(window.location.pathname);
    _listeners.add(onChange);
    window.addEventListener("popstate", onChange);
    return () => {
      _listeners.delete(onChange);
      window.removeEventListener("popstate", onChange);
    };
  }, []);

  return pathname;
}
