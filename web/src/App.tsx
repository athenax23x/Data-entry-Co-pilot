import { useEffect, useState } from "react";
import MerchantList from "./screens/MerchantList";
import NewMerchant from "./screens/NewMerchant";
import Workspace from "./screens/Workspace";

export type Route = { name: "list" } | { name: "new" } | { name: "merchant"; id: string };

export function parseHash(hash: string): Route {
  const m = /^#\/m\/(MCN-\d{8}-\d{3,})$/.exec(hash);
  if (m) return { name: "merchant", id: m[1] };
  return hash === "#/baru" ? { name: "new" } : { name: "list" };
}

export const go = (hash: string) => { window.location.hash = hash; };

export default function App() {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const on = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return (
    <div className="app">
      <header className="top">
        <a href="#/" className="brand">Merchant Notebook</a>
        <span className="local">Lokal · data tampil penuh di layar ini</span>
      </header>
      <main>
        {route.name === "list" && <MerchantList />}
        {route.name === "new" && <NewMerchant />}
        {route.name === "merchant" && <Workspace key={route.id} id={route.id} />}
      </main>
    </div>
  );
}
