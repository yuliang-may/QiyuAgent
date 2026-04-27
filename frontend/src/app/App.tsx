import { useEffect } from "react";

import { useAppStore } from "../features/app/store";
import { Providers } from "./providers";
import { AppRouter } from "./router";

export function App() {
  const initializeAuth = useAppStore((state) => state.initializeAuth);

  useEffect(() => {
    void initializeAuth();
  }, [initializeAuth]);

  return (
    <Providers>
      <AppRouter />
    </Providers>
  );
}
