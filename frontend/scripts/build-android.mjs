import { execFileSync } from "node:child_process";

const apiUrl = process.env.VITE_API_URL?.trim();
const npmCli = process.env.npm_execpath;

if (!apiUrl) {
  console.error("Configura VITE_API_URL con la URL HTTPS pública de la API antes de preparar Android.");
  process.exit(1);
}

if (!npmCli) {
  console.error("Ejecuta este comando con npm run android:sync.");
  process.exit(1);
}

let parsedUrl;
try {
  parsedUrl = new URL(apiUrl);
} catch {
  console.error("VITE_API_URL debe ser una URL válida, por ejemplo https://athletic-analysis.onrender.com.");
  process.exit(1);
}

if (parsedUrl.protocol !== "https:" || parsedUrl.pathname !== "/" || parsedUrl.search || parsedUrl.hash) {
  console.error("VITE_API_URL debe ser el origen HTTPS público de la API, sin rutas, parámetros ni fragmentos.");
  process.exit(1);
}

execFileSync(process.execPath, [npmCli, "run", "build"], { stdio: "inherit", env: process.env });
execFileSync(process.execPath, [npmCli, "exec", "--", "cap", "sync", "android"], {
  stdio: "inherit",
  env: process.env,
});
